"""The robot host: serves the SDK protocol and enforces safety, for any backend."""

from __future__ import annotations

import logging
import math
import os
import queue
import secrets
import threading
import time
from collections import deque

import zmq
from buildathon import protocol as P

from .backends.base import Backend
from .config import Config
from .safety import SafetyFilter

log = logging.getLogger("buildathon.host")

ORGANIZER_OPS = {
    "clear_estop",
    "heartbeat",
    "session_start",
    "session_stop",
    "set_base",
    "set_safe_mode",
}


class Host:
    def __init__(
        self,
        config: Config,
        backend: Backend,
        *,
        lockstep: bool = False,
        dashboard: bool = True,
        organizer_token: str = "",
        safe_mode: bool = False,
        heartbeat_required: bool | None = None,
        session_required: bool | None = None,
    ):
        self.config = config
        self.backend = backend
        self.lockstep = lockstep
        self.dashboard_enabled = dashboard
        real = backend.mode == "real"
        self.heartbeat_required = self._resolve(heartbeat_required, config.safety.heartbeat_required, real)
        self.session_required = self._resolve(session_required, config.safety.session_required, real)
        self.organizer_token = organizer_token
        if real and not self.organizer_token:
            self.organizer_token = secrets.token_urlsafe(9)
            log.warning("no BUILDATHON_ORGANIZER_TOKEN set; generated one for this run: %s", self.organizer_token)

        self.safe_mode = safe_mode
        self.safety = SafetyFilter(self._limits(), config.dt, config.safety.watchdog_timeout_s, full_limits=config.limits)
        self.base_enabled = config.base.enabled
        self.estop = False
        self.session: str | None = None
        self.session_deadline = math.inf
        self.session_end_reason = ""
        self.heartbeat_t = -math.inf
        self.seq = 0
        self.img_seq = 0
        self.odom = [0.0, 0.0, 0.0]
        self.stats = {"commands": 0, "rejected": 0, "overruns": 0, "clients_hello": 0}
        self.rtf = 1.0
        self._rtf_window: deque[tuple[float, float]] = deque(maxlen=60)
        self._running = False
        self._extras: dict = {}
        self._last_tick_wall = time.monotonic()
        self._images: dict[str, bytes] = {}
        self._header: dict = {}
        self._overview: bytes | None = None
        self._overview_wanted_until = 0.0
        self._snap = threading.Condition()
        self._control: queue.Queue = queue.Queue()  # requests from the dashboard thread
        self._capture_every = max(1, round(config.rate_hz / max(config.camera.fps, 0.1)))
        self._ctx = zmq.Context.instance()

    @staticmethod
    def _resolve(override: bool | None, setting, real: bool) -> bool:
        if override is not None:
            return override
        return real if setting == "auto" else bool(setting)

    def _limits(self):
        lim = self.config.limits
        return lim.scaled(lim.safe_mode_scale) if self.safe_mode else lim

    # ------------------------------------------------------------------ state helpers

    @property
    def base_active(self) -> bool:
        return self.config.base.present and self.base_enabled

    def _inhibit_reasons(self, now: float) -> list[str]:
        reasons = []
        if self.estop:
            reasons.append("estop")
        if self.heartbeat_required and time.monotonic() - self.heartbeat_t > self.config.safety.heartbeat_timeout_s:
            reasons.append("no_organizer_heartbeat")
        if self.session_required and self.session is None:
            reasons.append(self.session_end_reason or "no_active_session")
        min_v = self.config.safety.min_servo_voltage
        volts = self._extras.get("health", {}).get("voltage_min")
        if min_v > 0 and volts is not None and volts < min_v:
            reasons.append("low_servo_voltage")
        if self.session is not None and now > self.session_deadline:
            self._end_session("session_time_limit")
            reasons.append("session_time_limit")
        return reasons

    def _end_session(self, reason: str) -> None:
        if self.session is not None:
            log.info("session %s ended: %s", self.session, reason)
        self.session = None
        self.session_deadline = math.inf
        self.session_end_reason = reason

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        net = self.config.network
        # Bind the ports first: if another host already has them, fail fast with a clear message.
        try:
            self._pub = self._ctx.socket(zmq.PUB)
            self._pub.setsockopt(zmq.SNDHWM, 4)
            self._pub.setsockopt(zmq.LINGER, 0)
            self._pub.bind(f"tcp://*:{net.port_obs}")
            self._pull = self._ctx.socket(zmq.PULL)
            self._pull.setsockopt(zmq.RCVHWM, 16)
            self._pull.setsockopt(zmq.LINGER, 0)
            self._pull.bind(f"tcp://*:{net.port_cmd}")
            self._rep = self._ctx.socket(zmq.REP)
            self._rep.setsockopt(zmq.LINGER, 0)
            self._rep.bind(f"tcp://*:{net.port_rpc}")
        except zmq.ZMQError as exc:
            if exc.errno != zmq.EADDRINUSE:
                raise
            raise SystemExit(self._ports_busy(f"{net.port_obs}-{net.port_rpc}")) from None
        self._poller = zmq.Poller()
        self._poller.register(self._rep, zmq.POLLIN)
        self.backend.connect()
        self.safety.reset(self.backend.read())
        if self.dashboard_enabled and net.port_dashboard:
            from .dashboard import start_dashboard

            try:
                start_dashboard(self, net.port_dashboard)
            except OSError:
                self.backend.close()
                raise SystemExit(self._ports_busy(str(net.port_dashboard) + " (dashboard)")) from None
        self._tick()  # publish a first observation so clients see state at once
        if self.backend.mode == "real" and not self.lockstep:
            threading.Thread(target=self._loop_watchdog, daemon=True, name="loop-watchdog").start()
        log.info(
            "host up: backend=%s lockstep=%s base=%s ports=%d/%d/%d dashboard=%s",
            self.backend.mode,
            self.lockstep,
            "on" if self.base_active else "OFF (arm-only)",
            net.port_obs,
            net.port_cmd,
            net.port_rpc,
            f"http://localhost:{net.port_dashboard}" if self.dashboard_enabled and net.port_dashboard else "off",
        )

    def run(self) -> None:
        self.start()
        self._running = True
        dt = self.config.dt
        next_tick = time.monotonic() + dt
        try:
            while self._running:
                if self.lockstep:
                    timeout_ms = 50
                else:
                    timeout_ms = max(0, int((next_tick - time.monotonic()) * 1000))
                if self._poller.poll(timeout_ms):
                    self._serve_rpc()
                self._serve_control()
                if not self.lockstep and time.monotonic() >= next_tick:
                    self._tick()
                    next_tick += dt
                    if time.monotonic() - next_tick > dt:  # fell behind: skip, do not burst
                        self.stats["overruns"] += 1
                        next_tick = time.monotonic() + dt
        finally:
            self.shutdown()

    @staticmethod
    def _ports_busy(which: str) -> str:
        return (
            f"Port {which} is already in use: another simulator or robot host is running on this machine.\n"
            "Stop it with `robot stop-sim`, or start this one on other ports, for example:\n"
            "  robot sim --port 5660 --dashboard-port 8081      (then: export ROBOT_HOST=localhost:5660)\n"
            "--port takes three consecutive ports (5660, 5661, 5662 here)."
        )

    def stop(self) -> None:
        self._running = False

    def _loop_watchdog(self, limit_s: float = 1.5) -> None:
        """Real robot only: if the control loop hangs (e.g. a blocked serial read), exit hard.

        The wheels keep their last speed while the loop is stuck. Exiting lets the container
        entrypoint zero them and Docker restart the host.
        """
        while True:
            time.sleep(0.25)
            if self._running and time.monotonic() - self._last_tick_wall > limit_s:
                log.critical("control loop stalled for more than %.1fs: exiting so the wheels get stopped", limit_s)
                os._exit(70)

    def _park(self, timeout_s: float = 4.0) -> None:
        """Real robot only: fold the arm to its home pose before torque is released."""
        home = self.config.named_poses.get("home")
        if self.backend.mode != "real" or not home or self.estop or not self.config.safety.park_on_shutdown:
            return
        log.info("parking the arm before shutdown")
        now = self.backend.now()
        self.safety.accept({P.joint_key(j): v for j, v in home.items()}, now, False)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and self.safety.arm_cmd != self.safety.arm_goal:
            self.backend.write(self.safety.tick(self.backend.now(), base_active=False, motion_ok=True))
            time.sleep(self.config.dt)
        time.sleep(0.5)  # let the servos arrive

    def shutdown(self) -> None:
        self._running = False
        try:
            self.backend.stop_base()
            self._park()
        except Exception:
            log.exception("error while stopping")
        finally:
            self.backend.close()
            for sock in (self._pub, self._pull, self._rep):
                sock.close(linger=0)
            log.info("host stopped")

    # ------------------------------------------------------------------ the control tick

    def _accept(self, msg: dict, now: float) -> bool:
        action = msg.get("action") if isinstance(msg, dict) else None
        if not isinstance(action, dict):
            self.stats["rejected"] += 1
            return False
        if self.session_required and (self.session is None or msg.get("session") != self.session):
            self.stats["rejected"] += 1
            return False
        clean = {k: v for k, v in action.items() if k in P.ALL_KEYS and isinstance(v, (int, float))}
        if len(clean) != len(action):
            self.safety.events["invalid_value"] += 1
        self.safety.accept(clean, now, self.base_active)
        if clean:
            self.stats["commands"] += 1
        return True

    def _tick(self, stepped_msg: dict | None = None) -> tuple[dict, dict[str, bytes]]:
        b = self.backend
        now = b.now()
        if stepped_msg is not None:
            self._accept(stepped_msg, now)
        else:
            while True:
                try:
                    raw = self._pull.recv(zmq.NOBLOCK)
                except zmq.Again:
                    break
                try:
                    self._accept(P.loads(raw), now)
                except Exception:  # nothing a client sends may stop the control loop
                    self.stats["rejected"] += 1

        reasons = self._inhibit_reasons(now)
        action = self.safety.tick(now, base_active=self.base_active, motion_ok=not reasons)
        b.write(action)
        b.step(self.config.dt)
        state = b.read()

        vx, vy, wz = (state[k] for k in P.BASE_KEYS)
        th = math.radians(self.odom[2])
        dt = self.config.dt
        self.odom[0] += (vx * math.cos(th) - vy * math.sin(th)) * dt
        self.odom[1] += (vx * math.sin(th) + vy * math.cos(th)) * dt
        self.odom[2] += wz * dt

        new_images: dict[str, bytes] = {}
        if self.seq % self._capture_every == 0:
            new_images = b.capture()
            if new_images:
                self.img_seq += 1
        overview = None
        if self.seq % 6 == 0 and time.monotonic() < self._overview_wanted_until:
            overview = b.overview()

        self.seq += 1
        self._extras = b.extras()
        self._last_tick_wall = time.monotonic()
        t = b.now()
        self._rtf_window.append((time.monotonic(), t))
        if len(self._rtf_window) > 10:
            (w0, s0), (w1, s1) = self._rtf_window[0], self._rtf_window[-1]
            self.rtf = (s1 - s0) / (w1 - w0) if w1 > w0 else 1.0
        header = {
            "v": P.PROTOCOL_VERSION,
            "seq": self.seq,
            "t": round(t, 6),
            "mode": b.mode,
            "lockstep": self.lockstep,
            "state": {k: round(float(v), 4) for k, v in state.items()},
            "command": {k: round(float(v), 4) for k, v in action.items()},
            "odom": {"x": round(self.odom[0], 4), "y": round(self.odom[1], 4), "theta": round(self.odom[2], 3)},
            "base_enabled": self.base_active,
            "base_present": self.config.base.present,
            "estop": self.estop,
            "motion_enabled": not reasons,
            "inhibit": reasons,
            "safe_mode": self.safe_mode,
            "session": bool(self.session),
            "img_seq": self.img_seq,
            "events": dict(self.safety.events),
            "rtf": round(self.rtf, 3),
            **self._extras,
        }
        self._pub.send_multipart(P.encode_obs(header, new_images))
        with self._snap:
            self._header = header
            if new_images:
                self._images = new_images
            if overview:
                self._overview = overview
            self._snap.notify_all()
        return header, new_images

    # ------------------------------------------------------------------ requests

    def _serve_rpc(self) -> None:
        while True:
            try:
                raw = self._rep.recv(zmq.NOBLOCK)
            except zmq.Again:
                return
            try:
                reply, images = self.handle(P.loads(raw))
            except Exception as exc:  # a bad request must never take the host down
                log.exception("request failed")
                reply, images = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, {}
            reply["cams"] = list(images)
            self._rep.send_multipart([P.dumps(reply), *images.values()])

    def _serve_control(self) -> None:
        while True:
            try:
                request, answer = self._control.get_nowait()
            except queue.Empty:
                return
            try:
                reply, _ = self.handle(request)
            except Exception as exc:
                reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            answer.put(reply)

    def call_from_thread(self, request: dict, timeout: float = 2.0) -> dict:
        """Run a request on the host loop from another thread (used by the dashboard)."""
        answer: queue.Queue = queue.Queue(maxsize=1)
        self._control.put((request, answer))
        try:
            return answer.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "error": "host loop did not answer"}

    def handle(self, req: dict) -> tuple[dict, dict[str, bytes]]:
        if not isinstance(req, dict):
            return {"ok": False, "error": "a request must be a JSON object with an 'op' field"}, {}
        op = req.get("op")
        if op in ("set_base", "set_safe_mode") and not isinstance(req.get("enabled"), bool):
            return {"ok": False, "error": f'{op!r} needs "enabled": true or false'}, {}
        if op in ORGANIZER_OPS and self.organizer_token and req.get("token") != self.organizer_token:
            return {"ok": False, "error": f"{op!r} needs the organizer token"}, {}

        if op == "hello":
            self.stats["clients_hello"] += 1
            cfg = self.config
            return {
                "ok": True,
                "v": P.PROTOCOL_VERSION,
                "robot": cfg.name,
                "mode": self.backend.mode,
                "lockstep": self.lockstep,
                "dt": cfg.dt,
                "rate_hz": cfg.rate_hz,
                "base_enabled": self.base_active,
                "base_present": cfg.base.present,
                "cameras": [cfg.camera.name],
                "camera": {
                    "name": cfg.camera.name,
                    "mount": cfg.camera.mount,
                    "width": cfg.camera.width,
                    "height": cfg.camera.height,
                    "fps": cfg.camera.fps,
                },
                "limits": self._limits().public(),
                "named_poses": cfg.named_poses,
                "watchdog_timeout_s": cfg.safety.watchdog_timeout_s,
                "session_required": self.session_required,
                "heartbeat_required": self.heartbeat_required,
                "safe_mode": self.safe_mode,
            }, {}
        if op == "status":
            return {"ok": True, "status": self._header, "stats": self.stats}, {}
        if op == "observe":
            images = dict(self._images)
            if req.get("overview"):
                overview = self.backend.overview()
                if overview:
                    images["overview"] = overview
            return {"ok": True, "obs": self._header}, images
        if op == "step":
            if not self.lockstep:
                return {"ok": False, "error": "this host runs in real time; 'step' needs --lockstep"}, {}
            header, images = self._tick({"action": req.get("action") or {}, "session": req.get("session")})
            return {"ok": True, "obs": header}, images
        if op == "reset":
            if self.backend.mode == "real":
                return {"ok": False, "error": "reset is only available in simulation"}, {}
            self.backend.reset(req.get("seed"))
            self.safety.reset(self.backend.read())
            self.safety.events.clear()
            self.odom = [0.0, 0.0, 0.0]
            self._rtf_window.clear()  # simulated time jumped back: do not report a negative speed
            self.rtf = 1.0
            return {"ok": True}, {}
        if op == "shutdown":
            if self.backend.mode == "real":
                return {"ok": False, "error": "the real robot's host is stopped on the Pi, not over the network"}, {}
            log.info("shutdown requested")
            self._running = False
            return {"ok": True}, {}
        if op == "estop":
            if not self.estop:
                log.warning("E-STOP latched")
            self.estop = True
            self.backend.stop_base()
            return {"ok": True}, {}
        if op == "clear_estop":
            self.estop = False
            log.info("e-stop cleared")
            return {"ok": True}, {}
        if op == "heartbeat":
            self.heartbeat_t = time.monotonic()
            return {"ok": True}, {}
        if op == "session_start":
            limit = min(float(req.get("max_runtime_s") or math.inf), self.config.safety.max_runtime_s)
            self.session = str(req.get("session") or secrets.token_urlsafe(6))
            self.session_deadline = self.backend.now() + limit
            self.session_end_reason = ""
            self.safety.events.clear()
            log.info("session %s started, %.0fs limit", self.session, limit)
            return {"ok": True, "session": self.session, "max_runtime_s": limit}, {}
        if op == "session_stop":
            self._end_session("stopped_by_organizer")
            return {"ok": True}, {}
        if op == "set_base":
            enabled = bool(req.get("enabled"))
            if enabled and not self.config.base.present:
                return {"ok": False, "error": "robot.yaml says base.present is false; there are no wheels"}, {}
            self.base_enabled = enabled
            self.backend.set_base_enabled(enabled)
            log.info("base %s", "enabled" if enabled else "disabled (arm-only)")
            return {"ok": True, "base_enabled": self.base_active}, {}
        if op == "set_safe_mode":
            self.safe_mode = bool(req.get("enabled"))
            self.safety.set_limits(self._limits())
            return {"ok": True, "safe_mode": self.safe_mode}, {}
        return {"ok": False, "error": f"unknown op {op!r}"}, {}

    # ------------------------------------------------------------------ for the dashboard thread

    def snapshot(self) -> tuple[dict, dict[str, bytes], bytes | None]:
        with self._snap:
            return self._header, dict(self._images), self._overview

    def want_overview(self) -> None:
        self._overview_wanted_until = time.monotonic() + 2.0

    def wait_tick(self, timeout: float = 1.0) -> None:
        with self._snap:
            self._snap.wait(timeout)
