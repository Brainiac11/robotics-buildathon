"""The participant-facing robot client. Works unchanged against the sim and the real robot."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from collections.abc import Mapping

import zmq

from . import protocol as P
from .types import BaseDisabledError, Observation, RobotError, RobotTimeout


class Robot:
    """Connect with `Robot.connect()`; the host comes from the ROBOT_HOST environment variable.

        with Robot.connect() as robot:
            obs = robot.observe()
            robot.drive(vx=0.1)          # m/s forward
            robot.sleep(2.0)
            robot.stop()

    Units: metres, m/s, degrees, deg/s, gripper 0-100. Frame: +x forward, +y left.
    """

    def __init__(self, host: str | None = None, session: str | None = None, timeout: float = 5.0):
        host = host or os.environ.get("ROBOT_HOST")
        self.hostname, self._port_obs, self._port_cmd, self._port_rpc = P.parse_host(host)
        self.session = session or os.environ.get("ROBOT_SESSION", "")
        self.timeout = timeout
        self._ctx = zmq.Context.instance()
        self._rpc_sock: zmq.Socket | None = None
        self._cmd_sock: zmq.Socket | None = None
        self._rx_thread: threading.Thread | None = None
        self._rx_stop = threading.Event()
        self._cond = threading.Condition()
        self._latest: Observation | None = None
        self._last_seq = -1
        self._cmd_seq = 0
        self._pending: dict[str, float] = {}  # lockstep: action applied on the next step
        self._base_cmd: dict[str, float] | None = None  # last drive command, refreshed by sleep()
        self._closed = False
        self._warned_blocked = False
        self._last_images: dict[str, bytes] = {}
        self.info: dict = {}
        self.arm = Arm(self)
        self.gripper = Gripper(self)

    # ------------------------------------------------------------------ connection

    @classmethod
    def connect(
        cls,
        host: str | None = None,
        *,
        session: str | None = None,
        timeout: float = 5.0,
        handle_signals: bool = True,
    ) -> Robot:
        robot = cls(host, session, timeout)
        robot._open(handle_signals)
        return robot

    def _open(self, handle_signals: bool) -> None:
        try:
            self.info, _ = self._rpc({"op": "hello", "v": P.PROTOCOL_VERSION})
        except RobotTimeout:
            raise RobotTimeout(
                f"no robot host answered at {self.hostname}:{self._port_obs} within {self.timeout:.0f}s. "
                "Start the simulator with `robot sim`, or check ROBOT_HOST."
            ) from None
        if self.info.get("v") != P.PROTOCOL_VERSION:
            raise RobotError(
                f"protocol mismatch: host speaks v{self.info.get('v')}, this SDK v{P.PROTOCOL_VERSION}. "
                "Update the repo (git pull) on both sides."
            )
        try:
            self.snapshot()  # prime the camera frame so the first observation already has one
        except RobotError:
            pass
        self._cmd_sock = self._ctx.socket(zmq.PUSH)
        self._cmd_sock.setsockopt(zmq.LINGER, 0)
        self._cmd_sock.setsockopt(zmq.SNDHWM, 4)
        self._cmd_sock.connect(f"tcp://{self.hostname}:{self._port_cmd}")
        if not self.lockstep:
            self._rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._rx_thread.start()
        if handle_signals and threading.current_thread() is threading.main_thread():
            # Turn SIGTERM into a normal exit so `with Robot.connect()` stops the robot.
            signal.signal(signal.SIGTERM, _raise_exit)

    @property
    def lockstep(self) -> bool:
        """True when the simulator only advances as this client steps it (used by sim-check)."""
        return bool(self.info.get("lockstep"))

    @property
    def mode(self) -> str:
        """'sim', 'real' or 'mock'."""
        return self.info.get("mode", "")

    @property
    def base_enabled(self) -> bool:
        """False in arm-only mode; drive commands then raise BaseDisabledError."""
        if self._latest is not None:
            return self._latest.base_enabled
        return bool(self.info.get("base_enabled", True))

    @property
    def limits(self) -> dict:
        return self.info.get("limits", {})

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.stop()
        except Exception:
            pass
        self._closed = True
        self._rx_stop.set()
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=1.0)
        for sock in (self._cmd_sock, self._rpc_sock):
            if sock is not None:
                sock.close(linger=100)

    def __enter__(self) -> Robot:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ observing

    def observe(self, timeout: float | None = None) -> Observation:
        """Return the next observation, newer than the last one returned.

        Real time: blocks until the host publishes a new one (about 30 per second).
        Lockstep: advances the simulation by one control step.
        """
        timeout = self.timeout if timeout is None else timeout
        if self.lockstep:
            action, self._pending = self._pending, {}
            reply, images = self._rpc({"op": "step", "action": action, "session": self.session})
            obs = self._make_obs(reply["obs"], images)
            self._latest = obs
            self._last_seq = obs.seq
            return obs
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._latest is None or self._latest.seq == self._last_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RobotTimeout(f"no observation from {self.hostname} for {timeout:.1f}s")
                self._cond.wait(remaining)
            self._last_seq = self._latest.seq
            return self._latest

    def sleep(self, seconds: float) -> Observation:
        """Wait for `seconds` of robot time, keeping the current drive command alive.

        Use this instead of time.sleep(): it works in lockstep simulation, and it refreshes the
        base velocity so the watchdog does not stop the robot mid-move.
        """
        obs = self._latest or self.observe()
        end = obs.t + seconds
        while obs.t < end:
            if self._base_cmd:
                self._send(self._base_cmd)
            obs = self.observe()
        return obs

    def _make_obs(self, header: dict, images: dict[str, bytes]) -> Observation:
        # The host only attaches a camera frame when there is a new one (camera fps is lower
        # than the state rate), so carry the latest frame forward.
        if images:
            self._last_images = images
        return Observation.from_wire(header, self._last_images)

    def _receive_loop(self) -> None:
        sock = self._ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVHWM, 4)
        sock.setsockopt(zmq.SUBSCRIBE, P.OBS_TOPIC)
        sock.connect(f"tcp://{self.hostname}:{self._port_obs}")
        try:
            while not self._rx_stop.is_set():
                if not sock.poll(100):
                    continue
                obs = self._make_obs(*P.decode_obs(sock.recv_multipart()))
                while sock.poll(0):  # catch up: keep only the newest state
                    obs = self._make_obs(*P.decode_obs(sock.recv_multipart()))
                with self._cond:
                    self._latest = obs
                    self._cond.notify_all()
        finally:
            sock.close()

    # ------------------------------------------------------------------ commanding

    def send_action(self, action: Mapping[str, float]) -> None:
        """Send raw targets using LeKiwi keys, e.g. {"arm_elbow_flex.pos": 30, "x.vel": 0.1}.

        Keys you leave out keep their previous target. Base velocities expire after the
        watchdog timeout (0.5 s) unless sent again; `sleep()` does that for you.
        """
        clean: dict[str, float] = {}
        for key, value in action.items():
            if key not in P.ALL_KEYS:
                raise ValueError(f"unknown action key {key!r}; valid keys: {', '.join(P.ALL_KEYS)}")
            value = float(value)
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"action {key!r} is not a finite number")
            clean[key] = value
        base = {k: v for k, v in clean.items() if k in P.BASE_KEYS}
        if base:
            if any(v != 0.0 for v in base.values()) and not self.base_enabled:
                raise BaseDisabledError(
                    "the base is switched off (arm-only mode), so drive commands are not accepted. "
                    "Check robot.base_enabled before driving."
                )
            self._base_cmd = base if any(v != 0.0 for v in base.values()) else None
        self._send(clean)

    def _warn_if_blocked(self, action: dict[str, float]) -> None:
        """Say so, once, when commands are being ignored. Otherwise an app looks broken for no reason."""
        latest = self._latest
        if latest is None or latest.motion_enabled:
            self._warned_blocked = False
        elif not self._warned_blocked and any(k in P.POS_KEYS or v != 0.0 for k, v in action.items()):
            self._warned_blocked = True
            reasons = ", ".join(latest.info.get("inhibit", [])) or "unknown reason"
            print(
                f"[buildathon] the robot is not moving: motion is blocked ({reasons}). "
                "Commands are ignored until that is cleared. Check obs.motion_enabled.",
                file=sys.stderr,
            )

    def _send(self, action: dict[str, float]) -> None:
        self._warn_if_blocked(action)
        if self.lockstep:
            self._pending.update(action)
            return
        self._cmd_seq += 1
        msg = {"v": P.PROTOCOL_VERSION, "session": self.session, "seq": self._cmd_seq, "action": action}
        try:
            self._cmd_sock.send(P.dumps(msg), zmq.NOBLOCK)  # type: ignore[union-attr]
        except zmq.Again:
            pass  # host unreachable; its watchdog stops the robot

    def drive(self, vx: float = 0.0, vy: float = 0.0, wz: float = 0.0) -> None:
        """Set the base velocity: vx forward and vy left in m/s, wz counter-clockwise in deg/s."""
        self.send_action({"x.vel": vx, "y.vel": vy, "theta.vel": wz})

    def stop(self) -> None:
        """Stop the base. The arm holds its position."""
        self._base_cmd = None
        self._send({"x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0})
        if self.lockstep:
            self.observe()  # flush the stop into the simulation

    def estop(self) -> None:
        """Latch the emergency stop on the host. An organizer has to clear it."""
        self._rpc({"op": "estop"})

    def status(self) -> dict:
        return self._rpc({"op": "status"})[0]

    def snapshot(self) -> Observation:
        """The host's latest observation, without advancing a lockstep simulation."""
        reply, images = self._rpc({"op": "observe"})
        return self._make_obs(reply["obs"], images)

    # ------------------------------------------------------------------ requests

    def _rpc(self, request: dict, timeout: float | None = None) -> tuple[dict, dict[str, bytes]]:
        timeout = self.timeout if timeout is None else timeout
        if self._rpc_sock is None:
            self._rpc_sock = self._ctx.socket(zmq.REQ)
            self._rpc_sock.setsockopt(zmq.LINGER, 0)
            self._rpc_sock.connect(f"tcp://{self.hostname}:{self._port_rpc}")
        sock = self._rpc_sock
        sock.send(P.dumps(request))
        if not sock.poll(int(timeout * 1000)):
            sock.close()  # a REQ socket cannot be reused after a missed reply
            self._rpc_sock = None
            raise RobotTimeout(f"host did not answer {request.get('op')!r} within {timeout:.1f}s")
        frames = sock.recv_multipart()
        reply = P.loads(frames[0])
        if not reply.get("ok", False):
            raise RobotError(reply.get("error", "request refused by the host"))
        images = dict(zip(reply.get("cams", []), frames[1:]))
        return reply, images


class Arm:
    """Joint-space control of the SO-101 arm. Angles in degrees."""

    def __init__(self, robot: Robot):
        self._robot = robot

    @property
    def poses(self) -> dict[str, dict[str, float]]:
        """Named poses defined in config/robot.yaml."""
        return self._robot.info.get("named_poses", {})

    def set_joints(self, joints: Mapping[str, float] | None = None, **kw: float) -> None:
        """Set joint targets, e.g. set_joints(shoulder_pan=20, elbow_flex=45).

        Returns immediately; the host moves each joint at a limited speed.
        """
        targets = {**(joints or {}), **kw}
        self._robot.send_action({P.joint_key(j): v for j, v in targets.items()})

    def pose(self, name: str) -> None:
        """Command a named pose, e.g. arm.pose('home')."""
        if name not in self.poses:
            raise KeyError(f"unknown pose {name!r}; available: {', '.join(self.poses) or 'none'}")
        self.set_joints(self.poses[name])

    def move_to(
        self,
        joints: Mapping[str, float] | str | None = None,
        tolerance: float = 3.0,
        timeout: float = 8.0,
        **kw: float,
    ) -> bool:
        """Like set_joints (or pose, if given a name), but wait until the arm gets there.

        Returns True on arrival, False if `timeout` seconds of robot time pass first.
        """
        if isinstance(joints, str):
            if joints not in self.poses:
                raise KeyError(f"unknown pose {joints!r}; available: {', '.join(self.poses) or 'none'}")
            targets = dict(self.poses[joints])
        else:
            targets = {**(joints or {}), **kw}
        keyed = {P.joint_key(j): float(v) for j, v in targets.items()}
        robot = self._robot
        robot.send_action(keyed)
        obs = robot.observe()
        end = obs.t + timeout
        while obs.t < end:
            if all(abs(obs.state.get(k, 0.0) - v) <= tolerance for k, v in keyed.items()):
                return True
            if robot._base_cmd:
                robot._send(robot._base_cmd)
            robot._send(keyed)
            obs = robot.observe()
        return False


class Gripper:
    """The gripper: 0 is closed, 100 is fully open."""

    def __init__(self, robot: Robot):
        self._robot = robot

    def set(self, percent: float, wait: bool = False, timeout: float = 3.0) -> bool:
        """Command the jaws. With wait=True, block until they arrive or stop moving.

        Returns True if they reached `percent` (within 3), False if they stopped short, which
        after close() means something is held between them, or if `timeout` passed.
        Without wait it returns True at once: allow about a second for full travel.
        """
        robot = self._robot
        robot.send_action({P.GRIPPER_KEY: percent})
        if not wait:
            return True
        obs = robot.observe()
        start, end = obs.t, obs.t + timeout
        last, still_since = obs.gripper, obs.t
        while obs.t < end:
            if abs(obs.gripper - percent) <= 3.0:
                return True
            if abs(obs.gripper - last) > 0.5:
                last, still_since = obs.gripper, obs.t
            elif obs.t - start > 0.4 and obs.t - still_since > 0.4:
                return False  # the jaws have stopped short of the target
            if robot._base_cmd:
                robot._send(robot._base_cmd)
            obs = robot.observe()
        return False

    def open(self, wait: bool = False) -> bool:
        return self.set(100.0, wait=wait)

    def close(self, wait: bool = False) -> bool:
        return self.set(0.0, wait=wait)


def _raise_exit(signum, frame):
    raise SystemExit(0)
