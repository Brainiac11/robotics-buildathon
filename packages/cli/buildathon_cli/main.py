"""The `robot` command. Run `robot --help`."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from buildathon import Robot, RobotError, RobotTimeout

from .apps import find_app
from .simcheck import sim_check


def _token(args) -> str:
    """Organizer token: --token, then $BUILDATHON_ORGANIZER_TOKEN, then the .robot-token file
    that scripts/start-robot-host.sh writes in the repo root."""
    token = getattr(args, "token", None) or os.environ.get("BUILDATHON_ORGANIZER_TOKEN", "")
    if not token:
        for folder in (Path.cwd(), *Path.cwd().parents):
            if (folder / ".robot-token").is_file():
                return (folder / ".robot-token").read_text().strip()
    return token


def _client(args) -> Robot:
    """A connection for one-off requests (no command socket, no receiver thread)."""
    robot = Robot(getattr(args, "host", None), timeout=3.0)
    return robot


def _request(args, request: dict) -> dict:
    robot = _client(args)
    try:
        reply, _ = robot._rpc(request)
        return reply
    except RobotTimeout:
        raise SystemExit(
            f"No robot host answered at {robot.hostname}:{robot._port_rpc}. "
            "Start the simulator with `robot sim`, or pass --host / set ROBOT_HOST."
        ) from None
    except RobotError as exc:
        raise SystemExit(f"Refused: {exc}") from None


# ---------------------------------------------------------------------- commands


def cmd_sim(args) -> int:
    cmd = [sys.executable, "-m", "buildathon_host", "--backend", "sim", "--scene", args.scene]
    if args.no_base:
        cmd.append("--no-base")
    if args.base:
        cmd.append("--base")
    if args.lockstep:
        cmd.append("--lockstep")
    if args.safe_mode:
        cmd.append("--safe-mode")
    if args.rehearse:
        cmd.append("--rehearse")
    if args.port:
        cmd += ["--port", str(args.port)]
    if args.dashboard_port is not None:
        cmd += ["--dashboard-port", str(args.dashboard_port)]
    if args.camera_mount:
        cmd += ["--camera-mount", args.camera_mount]
    if os.name == "posix":
        os.execv(sys.executable, cmd)  # become the simulator, so Ctrl-C and `kill` reach it directly
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 0


def cmd_stop_sim(args) -> int:
    _request(args, {"op": "shutdown"})
    print("simulator stopped")
    return 0


def cmd_run(args) -> int:
    app = find_app(args.app)
    env = dict(os.environ)
    if args.host:
        env["ROBOT_HOST"] = args.host
    env.setdefault("PYTHONUNBUFFERED", "1")

    tracer = None
    if args.trace:
        tracer = Tracer(args.host or os.environ.get("ROBOT_HOST"), Path(args.trace))
        tracer.start()

    proc = subprocess.Popen(app.command(), cwd=app.path, env=env)
    try:
        proc.wait(timeout=args.duration)
    except subprocess.TimeoutExpired:
        print(f"[robot] {args.duration:.0f}s reached, stopping the app")
        _terminate(proc)
    except KeyboardInterrupt:
        _terminate(proc)
    if tracer:
        tracer.stop()
        print(f"[robot] trace written to {tracer.out}/ ({tracer.count} samples)")
    return 0 if proc.returncode in (0, -signal.SIGTERM) else (proc.returncode or 0)


def _terminate(proc: subprocess.Popen, grace: float = 5.0) -> bool:
    """Ask the app to stop; kill it if it does not. Returns True if it stopped by itself."""
    if proc.poll() is not None:
        return True
    proc.terminate()
    try:
        proc.wait(timeout=grace)
        return True
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return False


class Tracer:
    """Records what the robot did while an app ran: state as JSON lines, camera frames as JPEG."""

    def __init__(self, host: str | None, out: Path, state_hz: float = 5.0, frame_every_s: float = 1.0):
        self.host, self.out = host, out
        self.state_period, self.frame_period = 1.0 / state_hz, frame_every_s
        self.count = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _loop(self) -> None:
        try:
            robot = Robot(self.host, timeout=3.0)
            next_state = next_frame = 0.0
            with (self.out / "trace.jsonl").open("w") as log:
                while not self._stop.is_set():
                    try:
                        obs = robot.snapshot()
                    except RobotError:
                        time.sleep(0.2)
                        continue
                    if obs.t >= next_state:
                        next_state = obs.t + self.state_period
                        record = {
                            k: obs.info.get(k)
                            for k in ("seq", "t", "state", "command", "odom", "motion_enabled", "inhibit", "events", "truth")
                        }
                        log.write(json.dumps(record) + "\n")
                        log.flush()
                        self.count += 1
                    if obs.t >= next_frame and obs.cameras:
                        next_frame = obs.t + self.frame_period
                        (self.out / f"frame_{obs.t:07.2f}s.jpg").write_bytes(obs.jpeg())
                    time.sleep(0.05)
        except Exception as exc:  # tracing must never break the run
            print(f"[robot] trace stopped: {exc}")


def cmd_teleop(args) -> int:
    from .teleop import run_teleop

    return run_teleop(args.host, _token(args), linear=args.speed, angular=args.turn_speed, full_speed=args.full_speed)


def cmd_slot(args) -> int:
    from .slot import run_slot

    return run_slot(
        find_app(args.app),
        host=args.host,
        token=_token(args),
        full_speed=args.full_speed,
        allow_base=args.base,
        skip_check=args.skip_check,
        max_runtime=args.max_runtime,
        note=args.note,
    )


def cmd_trace(args) -> int:
    """Record state and camera frames from a running robot or simulator, without controlling it."""
    tracer = Tracer(args.host or os.environ.get("ROBOT_HOST"), Path(args.out), frame_every_s=args.frame_every)
    try:
        Robot(args.host, timeout=3.0)._rpc({"op": "status"})
    except RobotTimeout:
        raise SystemExit("No robot host answered. Start `robot sim`, or pass --host / set ROBOT_HOST.") from None
    tracer.start()
    print(f"recording to {tracer.out}/ ... Ctrl-C to stop" + (f" (or after {args.duration:.0f}s)" if args.duration else ""))
    try:
        end = time.monotonic() + args.duration if args.duration else None
        while end is None or time.monotonic() < end:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    tracer.stop()
    print(f"trace written to {tracer.out}/ ({tracer.count} samples)")
    return 0


def cmd_sim_check(args) -> int:
    return sim_check(
        find_app(args.app),
        duration=args.duration,
        scene=args.scene,
        no_base=args.no_base,
        seed=args.seed,
        keep_log=True,
    )


def cmd_snapshot(args) -> int:
    robot = _client(args)
    try:
        reply, images = robot._rpc({"op": "observe", "overview": True})
    except RobotTimeout:
        raise SystemExit("No robot host answered. Start the simulator with `robot sim`.") from None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "state.json").write_text(json.dumps(reply["obs"], indent=2))
    written = ["state.json"]
    for name, jpeg in images.items():
        (out / f"{name}.jpg").write_bytes(jpeg)
        written.append(f"{name}.jpg")
    print(f"wrote {', '.join(written)} to {out}/")
    return 0


def cmd_status(args) -> int:
    reply = _request(args, {"op": "status"})
    s = reply["status"]
    if args.json:
        print(json.dumps(reply, indent=2))
        return 0
    print(f"mode: {s['mode']}{' (lockstep)' if s['lockstep'] else ''}   t={s['t']:.1f}s   speed={s['rtf']:.2f}x")
    print(f"motion: {'enabled' if s['motion_enabled'] else 'BLOCKED: ' + ', '.join(s['inhibit'])}")
    print(
        f"base: {'on' if s['base_enabled'] else 'OFF (arm-only)' if s['base_present'] else 'not fitted'}"
        f"   safe mode: {'on' if s['safe_mode'] else 'off'}"
    )
    for key, value in s["state"].items():
        print(f"  {key:24s} {value:9.2f}")
    print(f"  odom: x={s['odom']['x']:.3f} m  y={s['odom']['y']:.3f} m  heading={s['odom']['theta']:.1f} deg")
    print(f"safety events: {s['events'] or 'none'}")
    return 0


def cmd_estop(args) -> int:
    _request(args, {"op": "estop"})
    print("E-stop latched. Clear it with `robot clear-estop` (on the real robot only organizers can).")
    return 0


def cmd_clear_estop(args) -> int:
    _request(args, {"op": "clear_estop", "token": _token(args)})
    print("E-stop cleared.")
    return 0


def cmd_enable(args) -> int:
    """Hold the robot enabled by sending the organizer heartbeat until Ctrl-C."""
    robot = _client(args)
    print("Holding the robot enabled. Press Ctrl-C to drop the heartbeat (the robot stops).")
    try:
        while True:
            try:
                robot._rpc({"op": "heartbeat", "token": _token(args)}, timeout=1.0)
            except RobotTimeout:
                print("host unreachable, retrying...")
            except RobotError as exc:
                raise SystemExit(f"Refused: {exc}") from None
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nHeartbeat dropped.")
    return 0


def cmd_base(args) -> int:
    reply = _request(args, {"op": "set_base", "enabled": args.state == "on", "token": _token(args)})
    print(f"base is now {'on' if reply['base_enabled'] else 'off (arm-only)'}")
    return 0


def cmd_safe_mode(args) -> int:
    reply = _request(args, {"op": "set_safe_mode", "enabled": args.state == "on", "token": _token(args)})
    print(f"safe mode is now {'on' if reply['safe_mode'] else 'off'}")
    return 0


def cmd_session(args) -> int:
    if args.action == "start":
        req = {"op": "session_start", "token": _token(args), "max_runtime_s": args.max_runtime}
        if args.id:
            req["session"] = args.id
        reply = _request(args, req)
        print(f"session {reply['session']} started ({reply['max_runtime_s']:.0f}s limit)")
        print(f"give the app:  ROBOT_SESSION={reply['session']}")
    else:
        _request(args, {"op": "session_stop", "token": _token(args)})
        print("session ended")
    return 0


def cmd_deploy(args) -> int:
    from .deploy import deploy, ssh_target_from

    return deploy(
        find_app(args.app),
        ssh_target=ssh_target_from(args),
        host=args.host,
        token=_token(args),
        no_base=args.no_base,
        skip_check=args.skip_check,
        full_speed=args.full_speed,
        max_runtime=args.max_runtime,
        follow=not args.no_follow,
    )


def cmd_stop_app(args) -> int:
    from .deploy import ssh_target_from, stop_app

    target = ssh_target_from(args)
    stop_app(target, args.host or target.split("@")[-1], _token(args))
    print("app stopped, session ended")
    return 0


def cmd_reset(args) -> int:
    _request(args, {"op": "reset", "seed": args.seed})
    print("simulation reset")
    return 0


# ---------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="robot", description="Build-a-thon robot tool.")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    def host_arg(p):
        p.add_argument("--host", help="robot host, e.g. localhost or 192.168.8.10 (default: $ROBOT_HOST or localhost)")

    def token_arg(p):
        p.add_argument("--token", help="organizer token (default: $BUILDATHON_ORGANIZER_TOKEN)")

    p = sub.add_parser("sim", help="start the simulator (dashboard at http://localhost:8080)")
    p.add_argument("--scene", default="table", help="scene from config/scenes/: table, pick, empty, targets")
    p.add_argument("--base", action="store_true", help="enable the wheeled base (the default is arm-only)")
    p.add_argument("--no-base", action="store_true", help="arm-only mode: the base cannot be driven (the default)")
    p.add_argument("--lockstep", action="store_true", help="advance only when the app steps (deterministic)")
    p.add_argument("--safe-mode", action="store_true", help="reduced speed limits, as on a first real run")
    p.add_argument(
        "--rehearse",
        action="store_true",
        help="behave like the real robot: needs `robot enable` and `robot session start` before anything moves",
    )
    p.add_argument("--camera-mount", choices=["workspace", "wrist", "base_front"], help="which camera apps see")
    p.add_argument("--port", type=int, help="first of THREE consecutive ports (default 5560, so 5560-5562)")
    p.add_argument("--dashboard-port", type=int, help="dashboard port (default 8080; 0 = no dashboard)")
    p.set_defaults(fn=cmd_sim)

    p = sub.add_parser("stop-sim", help="stop a running simulator (the one at --host / $ROBOT_HOST)")
    host_arg(p)
    p.set_defaults(fn=cmd_stop_sim)

    p = sub.add_parser("run", help="run an app against the sim or robot")
    p.add_argument("app", help="app directory (with main.py) or a .py file")
    host_arg(p)
    p.add_argument("--duration", type=float, help="stop the app after this many seconds (wall-clock time)")
    p.add_argument("--trace", metavar="DIR", help="record state (JSON lines) and camera frames to DIR")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("teleop", help="drive the base and jog the arm from the keyboard (sim or robot)")
    host_arg(p), token_arg(p)
    p.add_argument("--speed", type=float, default=0.10, help="starting base speed in m/s (default 0.10)")
    p.add_argument("--turn-speed", type=float, default=30.0, help="starting turn rate in deg/s (default 30)")
    p.add_argument("--full-speed", action="store_true", help="real robot: normal limits instead of safe mode")
    p.set_defaults(fn=cmd_teleop)

    p = sub.add_parser("trace", help="record state and camera frames from a running robot or sim (watch only)")
    host_arg(p)
    p.add_argument("--out", default="traces/latest", help="directory to write to")
    p.add_argument("--duration", type=float, help="stop after this many seconds (default: until Ctrl-C)")
    p.add_argument("--frame-every", type=float, default=1.0, help="seconds between saved camera frames")
    p.set_defaults(fn=cmd_trace)

    p = sub.add_parser("sim-check", help="the gate: run an app in a private, deterministic sim and judge it")
    p.add_argument("app")
    p.add_argument("--duration", type=float, help="simulated seconds to run (default: app.yaml or 20)")
    p.add_argument("--scene", help="scene (default: app.yaml or empty)")
    p.add_argument("--no-base", action="store_true", help="check in arm-only mode")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_sim_check)

    p = sub.add_parser("snapshot", help="save the current camera frame and state to files")
    host_arg(p)
    p.add_argument("--out", default="snapshots")
    p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("status", help="print the robot's state")
    host_arg(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("estop", help="stop the robot now (anyone may do this)")
    host_arg(p)
    p.set_defaults(fn=cmd_estop)

    p = sub.add_parser("reset", help="reset the simulation")
    host_arg(p)
    p.add_argument("--seed", type=int)
    p.set_defaults(fn=cmd_reset)

    p = sub.add_parser("clear-estop", help="[organizer] clear a latched e-stop")
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_clear_estop)

    p = sub.add_parser("enable", help="[organizer] hold the real robot enabled (heartbeat) until Ctrl-C")
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_enable)

    p = sub.add_parser("base", help="[organizer] switch the wheeled base on or off (off = arm-only)")
    p.add_argument("state", choices=["on", "off"])
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_base)

    p = sub.add_parser("safe-mode", help="[organizer] switch reduced speed limits on or off")
    p.add_argument("state", choices=["on", "off"])
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_safe_mode)

    p = sub.add_parser("session", help="[organizer] start or end a control session")
    p.add_argument("action", choices=["start", "stop"])
    p.add_argument("--id", help="session id (default: random)")
    p.add_argument("--max-runtime", type=float, help="seconds before the session ends by itself")
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_session)

    p = sub.add_parser("slot", help="[supervisor] run a team's app on the real arm from this laptop: gate, run, log")
    p.add_argument("app", help="the team's directory, e.g. teams/rockets")
    p.add_argument("--full-speed", action="store_true", help="normal limits (default: safe mode, half speed)")
    p.add_argument("--base", action="store_true", help="allow the wheels, if the app asks for them (default: off)")
    p.add_argument("--skip-check", action="store_true", help="do not re-run the gate")
    p.add_argument("--max-runtime", type=float, default=180.0, help="seconds before the run is stopped (default 180)")
    p.add_argument("--note", help="log note (otherwise you are asked at the end)")
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_slot)

    p = sub.add_parser("deploy", help="[organizer] gate an app, copy it to the robot and start it")
    p.add_argument("app")
    p.add_argument("--ssh", help="the Pi's ssh address, e.g. pi@192.168.8.10 (default: $ROBOT_SSH)")
    p.add_argument("--no-base", action="store_true", help="deploy in arm-only mode: wheels stay off")
    p.add_argument("--skip-check", action="store_true", help="deploy without the sim-check gate")
    p.add_argument("--full-speed", action="store_true", help="normal limits instead of safe mode")
    p.add_argument("--max-runtime", type=float, default=180.0, help="seconds before the session ends")
    p.add_argument("--no-follow", action="store_true", help="do not stream the app's output")
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_deploy)

    p = sub.add_parser("stop-app", help="[organizer] stop the app running on the robot")
    p.add_argument("--ssh", help="the Pi's ssh address (default: $ROBOT_SSH)")
    host_arg(p), token_arg(p)
    p.set_defaults(fn=cmd_stop_app)
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        raise SystemExit(args.fn(args))
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
