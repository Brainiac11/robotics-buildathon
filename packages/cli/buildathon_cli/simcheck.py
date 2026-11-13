"""`robot sim-check`: run an app in a private, deterministic simulation and judge it.

What it checks (it is a crash-and-limits gate, not a judge of whether the task was solved):
  1. the app connects to the robot
  2. it runs for the requested simulated time without crashing
  3. it never asks for something outside the robot's limits
  4. it stops within 5 seconds when told to
"""

from __future__ import annotations

import json
import os
import random
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from buildathon import Robot, RobotError

from .apps import App

# Asking for these means the app has a bug; the host clamps them, but the gate fails.
FAILING_EVENTS = {
    "joint_limit": "asked for a joint angle outside its limits (see robot.limits)",
    "base_speed": "asked for a base speed above the limit (see robot.limits)",
    "invalid_value": "sent a non-numeric or unknown action value",
    "base_disabled": "sent drive commands while the base is off (arm-only mode)",
}
STALL_WALL_S = 20.0
SETTLE_STEPS = 45  # about 1.5 simulated seconds


def _last_line(path: Path) -> str:
    try:
        lines = [line.strip() for line in path.read_text(errors="replace").splitlines() if line.strip()]
    except OSError:
        return ""
    return lines[-1][:160] if lines else ""


def _distances(truth: dict) -> dict[str, float]:
    """Straight-line distance on the floor from the robot's centre to each scene object."""
    if "x" not in truth:
        return {}
    return {
        name: round(((pos[0] - truth["x"]) ** 2 + (pos[1] - truth["y"]) ** 2) ** 0.5, 3)
        for name, pos in truth.get("objects", {}).items()
    }


def _free_port_block() -> int:
    """Three free consecutive ports.

    Picked at random from 20000-29999, below the range operating systems hand out for outgoing
    connections: a port taken from that range can be grabbed by any client socket (including
    our own) between this check and the simulator binding it.
    """
    for _ in range(200):
        port = random.randrange(20000, 29997)
        socks = []
        try:
            for p in (port, port + 1, port + 2):
                s = socket.socket()
                socks.append(s)
                s.bind(("0.0.0.0", p))
            return port
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()
    raise RuntimeError("could not find three free consecutive ports")


def sim_check(
    app: App,
    *,
    duration: float | None = None,
    scene: str | None = None,
    no_base: bool = False,
    seed: int = 0,
    keep_log: bool = True,
    _attempt: int = 1,
) -> int:
    if app.interactive:
        print(
            f"SKIP: {app.name} is marked interactive in app.yaml (it needs a person at the keyboard), "
            "so it cannot be gated automatically."
        )
        return 0
    duration = duration or app.duration_s
    scene = scene or app.scene
    arm_only = no_base or not app.needs_base
    out_dir = Path(".simcheck")
    out_dir.mkdir(exist_ok=True)
    log_path = out_dir / f"{app.name}.log"
    port = _free_port_block()

    print(
        f"sim-check {app.name}: scene={scene} base={'off (arm-only)' if arm_only else 'on'} "
        f"duration={duration:.0f}s simulated, seed={seed}"
    )

    host_cmd = [
        sys.executable,
        "-m",
        "buildathon_host",
        "--backend",
        "sim",
        "--lockstep",
        "--scene",
        scene,
        "--port",
        str(port),
        "--dashboard-port",
        "0",
    ]
    host_cmd.append("--no-base" if arm_only else "--base")
    if app.camera:
        host_cmd += ["--camera-mount", app.camera]
    host_log = (out_dir / f"{app.name}.host.log").open("w")
    host = subprocess.Popen(host_cmd, stdout=host_log, stderr=subprocess.STDOUT)
    proc = None
    problems: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    app_wall_s = 0.0
    hello_before = 0
    status: dict = {}
    sim_time = 0.0
    stopped_cleanly = True
    exit_code: int | None = None
    try:
        monitor = Robot(f"localhost:{port}", timeout=2.0)
        deadline = time.monotonic() + 60
        while True:
            if host.poll() is not None:
                host_log.flush()
                if _attempt < 3 and "already in use" in Path(host_log.name).read_text(errors="replace"):
                    # Two gates picked the same ports at the same moment: try again with others.
                    return sim_check(app, duration=duration, scene=scene, no_base=no_base, seed=seed, _attempt=_attempt + 1)
                print(f"FAIL: the simulator did not start. See {host_log.name}")
                return 2
            try:
                monitor._rpc({"op": "hello"}, timeout=1.0)
                break
            except RobotError:
                if time.monotonic() > deadline:
                    print(f"FAIL: the simulator did not answer. See {host_log.name}")
                    return 2
        monitor._rpc({"op": "reset", "seed": seed})
        hello_before = monitor._rpc({"op": "status"})[0]["stats"].get("clients_hello", 0)

        env = dict(os.environ, ROBOT_HOST=f"localhost:{port}", PYTHONUNBUFFERED="1", ROBOT_SIM_CHECK="1")
        with log_path.open("w") as app_log:
            proc = subprocess.Popen(app.command(), cwd=app.path, env=env, stdout=app_log, stderr=subprocess.STDOUT)
            app_started = time.monotonic()
            last_progress = time.monotonic()
            last_t = -1.0
            while True:
                reply, _ = monitor._rpc({"op": "status"})
                status, stats = reply["status"], reply["stats"]
                sim_time = status.get("t", 0.0)
                if sim_time > last_t:
                    last_t, last_progress = sim_time, time.monotonic()
                if proc.poll() is not None:
                    exit_code = proc.returncode
                    app_wall_s = time.monotonic() - app_started
                    break
                if sim_time >= duration:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                        stopped_cleanly = False
                    break
                if time.monotonic() - last_progress > STALL_WALL_S:
                    proc.kill()
                    proc.wait()
                    problems.append(
                        f"stalled: simulated time stopped advancing at {sim_time:.1f}s. The app is blocked, "
                        "or waits with time.sleep() instead of robot.sleep()/robot.observe()"
                    )
                    break
                time.sleep(0.1)
        # The simulation only advances when stepped. Let it run on for a moment with no app,
        # so the recorded final state is the robot at rest, not mid-motion.
        for _ in range(SETTLE_STEPS):
            monitor._rpc({"op": "step", "action": {}})
        reply, _ = monitor._rpc({"op": "status"})
        status, stats = reply["status"], reply["stats"]
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
        host.terminate()
        try:
            host.wait(timeout=5)
        except subprocess.TimeoutExpired:
            host.kill()
        host_log.close()

    events = status.get("events", {})
    if stats.get("clients_hello", 0) <= hello_before:
        problems.append("never connected: the app did not call Robot.connect()")
    if exit_code not in (None, 0):
        last = _last_line(log_path)
        problems.append(
            f"exited with error code {exit_code} after {sim_time:.1f}s simulated"
            + (f"; its last output was: {last!r}" if last else "")
            + f" (full output: {log_path})"
        )
    moving = [k for k in ("x.vel", "y.vel", "theta.vel") if abs(status.get("state", {}).get(k, 0.0)) > 0.02]
    if moving:
        problems.append("the base was still moving 1.5s after the app ended")
    if not stopped_cleanly:
        problems.append("did not stop within 5s when told to; use `with Robot.connect() as robot:` or run(Behavior)")
    for name, meaning in FAILING_EVENTS.items():
        if events.get(name):
            problems.append(f"{meaning} [{events[name]}x]")
    if events.get("watchdog"):
        warnings.append(
            f"the base was left driving without fresh commands {events['watchdog']}x; "
            "the watchdog stopped it. Use robot.sleep() while driving, and robot.stop() when done"
        )
    if exit_code == 0 and app_wall_s > 2.0 and sim_time < 0.25 * app_wall_s:
        warnings.append(
            f"the app ran for {app_wall_s:.0f}s but the simulation advanced only {sim_time:.1f}s, so the robot did "
            "almost nothing here. If the app waits with time.sleep(), use robot.sleep() instead: simulated time "
            "only moves when the app calls the SDK. (Fine if your app is just slow to compute.)"
        )
    if exit_code == 0 and sim_time < duration:
        notes.append(f"the app finished by itself after {sim_time:.1f}s simulated, which is fine if it was done")
    if stats.get("commands", 0) == 0 and not problems:
        warnings.append("the app sent no commands")

    passed = not problems
    report = {
        "app": app.name,
        "code_hash": app.code_hash(),
        "passed": passed,
        "scene": scene,
        "base_enabled": not arm_only,
        "seed": seed,
        "simulated_s": round(sim_time, 2),
        "commands": stats.get("commands", 0),
        "events": events,
        "problems": problems,
        "warnings": warnings,
        "notes": notes,
        "final_state": status.get("state", {}),
        "final_truth": status.get("truth", {}),
        "final_distance_to_objects_m": _distances(status.get("truth", {})),
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    report_path = out_dir / f"{app.name}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")

    for n in notes:
        print(f"  note: {n}")
    if report["final_distance_to_objects_m"]:
        nearest = ", ".join(
            f"{k} {v:.2f} m" for k, v in sorted(report["final_distance_to_objects_m"].items(), key=lambda kv: kv[1])
        )
        print(f"  robot ended at rest; distance from its centre to: {nearest}")
    for w in warnings:
        print(f"  warning: {w}")
    for p in problems:
        print(f"  problem: {p}")
    print(
        f"{'PASS' if passed else 'FAIL'}: {app.name} ({sim_time:.1f}s simulated, {stats.get('commands', 0)} commands) "
        f"-> {report_path}"
    )
    if not passed:
        print(f"  app output: {log_path}")
    return 0 if passed else 1
