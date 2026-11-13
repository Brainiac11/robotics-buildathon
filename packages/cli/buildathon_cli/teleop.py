"""`robot teleop`: drive the base and jog the arm from the keyboard.

Works against the simulator and the real robot. On a host that needs an organizer (the real
robot, or `robot sim --rehearse`) it holds the heartbeat and runs the session itself, so the
robot can only move while this program is running: closing it, or losing the connection,
stops the robot.

The base moves only while a key is held. Arm keys nudge one joint a few degrees per press.
"""

from __future__ import annotations

import sys
import threading
import time

from buildathon import Robot, RobotError
from buildathon import protocol as P

HELP = """
  BASE (hold the key)          ARM (tap or hold)                 OTHER
    w / s   forward / back       z / c   shoulder pan  left/right   space   stop the base now
    a / d   left / right         r / f   shoulder lift up/down      + / -   base speed up / down
    q / e   turn left / right    t / g   elbow         up/down      [ / ]   arm step smaller / larger
                                 y / h   wrist flex    up/down      p       E-STOP (latches)
                                 u / j   wrist roll                 x       quit
                                 o / l   gripper open / close
"""

# key -> (vx, vy, wz) direction
BASE_KEYS = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 1, 0), "d": (0, -1, 0), "q": (0, 0, 1), "e": (0, 0, -1)}
# key -> (joint, direction). Directions follow the simulator: see docs/robot.md.
ARM_KEYS = {
    "z": ("shoulder_pan", -1), "c": ("shoulder_pan", 1),
    "r": ("shoulder_lift", -1), "f": ("shoulder_lift", 1),
    "t": ("elbow_flex", -1), "g": ("elbow_flex", 1),
    "y": ("wrist_flex", -1), "h": ("wrist_flex", 1),
    "u": ("wrist_roll", -1), "j": ("wrist_roll", 1),
    "o": ("gripper", 1), "l": ("gripper", -1),
}  # fmt: skip
LABELS = {
    "shoulder_pan": "pan",
    "shoulder_lift": "lift",
    "elbow_flex": "elbow",
    "wrist_flex": "wflex",
    "wrist_roll": "wroll",
    "gripper": "grip",
}
RELEASE_S = 0.5  # the base stops this long after the last base key (terminals repeat keys with a delay)


class Teleop:
    """Turns key presses into robot commands. No terminal handling here, so it can be tested."""

    def __init__(self, robot: Robot, linear: float = 0.10, angular: float = 30.0, step_deg: float = 3.0):
        self.robot = robot
        lim = robot.limits
        self.max_linear = float(lim.get("max_linear_m_s", 0.3))
        self.max_angular = float(lim.get("max_angular_deg_s", 90.0))
        self.linear = min(linear, self.max_linear)
        self.angular = min(angular, self.max_angular)
        self.step_deg = step_deg
        self.targets: dict[str, float] = {}  # arm targets, filled from the measured pose when first used
        self.direction = (0, 0, 0)
        self.last_base_key = -1.0
        self.driving = False
        self.message = ""
        self.quit = False

    def _range(self, joint: str) -> tuple[float, float]:
        if joint == P.GRIPPER:
            lo, hi = self.robot.limits.get("gripper_pct", [0.0, 100.0])
        else:
            lo, hi = self.robot.limits.get("joints_deg", {}).get(joint, [-180.0, 180.0])
        return float(lo), float(hi)

    def handle_key(self, key: str, obs, now: float) -> None:
        key = key.lower() if len(key) == 1 else key
        if key in BASE_KEYS:
            if not self.robot.base_enabled:
                self.message = "base is switched off (arm-only mode)"
                return
            self.direction, self.last_base_key = BASE_KEYS[key], now
        elif key in ARM_KEYS:
            joint, sign = ARM_KEYS[key]
            lo, hi = self._range(joint)
            step = 10.0 if joint == P.GRIPPER else self.step_deg
            # Start from where the joint really is, so the first tap never causes a jump.
            current = self.targets.get(joint, min(hi, max(lo, obs.joints.get(joint, 0.0))))
            self.targets[joint] = min(hi, max(lo, current + sign * step))
            self.robot.arm.set_joints({joint: self.targets[joint]})
            self.message = f"{joint} -> {self.targets[joint]:.0f}"
        elif key == " ":
            self.direction, self.last_base_key = (0, 0, 0), -1.0
            self.robot.stop()
            self.driving = False
            self.message = "base stopped"
        elif key in "+=":
            self.linear = min(self.max_linear, self.linear + 0.02)
            self.angular = min(self.max_angular, self.angular + 5)
        elif key in "-_":
            self.linear = max(0.02, self.linear - 0.02)
            self.angular = max(5, self.angular - 5)
        elif key == "[":
            self.step_deg = max(1.0, self.step_deg - 1)
        elif key == "]":
            self.step_deg = min(10.0, self.step_deg + 1)
        elif key == "p":
            self.robot.estop()
            self.message = "E-STOP latched; clear it with `robot clear-estop`"
        elif key in ("x", "\x03", "\x1b"):
            self.quit = True

    def tick(self, now: float) -> None:
        """Call once per loop: keeps the base moving while a key is held, stops it on release."""
        if now - self.last_base_key <= RELEASE_S and any(self.direction) and self.robot.base_enabled:
            dx, dy, dw = self.direction
            self.robot.drive(vx=dx * self.linear, vy=dy * self.linear, wz=dw * self.angular)
            self.driving = True
        elif self.driving:
            self.robot.stop()
            self.driving = False

    def status_line(self, obs) -> str:
        joints = " ".join(f"{LABELS.get(name, name)} {angle:6.1f}" for name, angle in obs.joints.items())
        vx, vy, wz = obs.base_velocity
        blocked = "" if obs.motion_enabled else f"  BLOCKED: {', '.join(obs.info.get('inhibit', []))}"
        base = f"base {vx:+.2f} {vy:+.2f} {wz:+4.0f}" if obs.base_enabled else "base OFF"
        return f"{joints} | {base} | speed {self.linear:.2f} m/s step {self.step_deg:.0f}deg{blocked}  {self.message}"


class Organizer:
    """Holds the heartbeat and the session on hosts that need them (real robot, --rehearse)."""

    def __init__(self, host: str | None, token: str, safe_mode: bool | None):
        self.host, self.token = host, token
        self.client = Robot(host, timeout=2.0)  # its own socket: used from the heartbeat thread only
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._beat, daemon=True)
        self.error = ""
        self.safe_mode = safe_mode

    def _call(self, request: dict) -> dict:
        return self.client._rpc({**request, "token": self.token})[0]

    def start(self, max_runtime_s: float | None = None) -> str:
        """Start beating and open a session. Returns the session id for the controlling client."""
        self._call({"op": "heartbeat"})  # fails here, clearly, if the token is wrong
        if self.safe_mode is not None:
            self._call({"op": "set_safe_mode", "enabled": self.safe_mode})
        session = self._call({"op": "session_start", "max_runtime_s": max_runtime_s})["session"]
        self._thread.start()
        return session

    def renew(self) -> str:
        return Robot(self.host, timeout=2.0)._rpc({"op": "session_start", "token": self.token})[0]["session"]

    def _beat(self) -> None:
        while not self._stop.is_set():
            try:
                self._call({"op": "heartbeat"})
                self.error = ""
            except RobotError as exc:
                self.error = str(exc)
            self._stop.wait(0.25)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        try:
            Robot(self.host, timeout=2.0)._rpc({"op": "session_stop", "token": self.token})
        except RobotError:
            pass


def _keys():
    """Yield key presses without waiting for Enter; '' when no key is waiting."""
    if sys.platform == "win32":
        import msvcrt

        while True:
            yield msvcrt.getwch() if msvcrt.kbhit() else ""
    else:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0)
                yield sys.stdin.read(1) if ready else ""
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def run_teleop(host: str | None, token: str, *, linear: float, angular: float, full_speed: bool) -> int:
    if not sys.stdin.isatty():
        raise SystemExit("robot teleop needs an interactive terminal")
    probe = Robot(host, timeout=3.0)
    try:
        info, _ = probe._rpc({"op": "hello"})
    except RobotError:
        raise SystemExit(
            f"No robot host answered at {probe.hostname}. Start the simulator (`robot sim`) or the robot host first."
        ) from None

    organizer = None
    session = None
    needs_organizer = info.get("heartbeat_required") or info.get("session_required")
    if needs_organizer:
        if not token:
            raise SystemExit("This host needs the organizer token: set BUILDATHON_ORGANIZER_TOKEN or pass --token.")
        safe = None if info.get("mode") != "real" else (not full_speed)
        organizer = Organizer(host, token, safe)
        try:
            session = organizer.start()
        except RobotError as exc:
            raise SystemExit(f"The host refused: {exc}") from None

    print(HELP)
    if info.get("mode") == "real":
        print("  REAL ROBOT" + ("" if full_speed else " in safe mode (half speed)") + ". It stops when this program exits.")
    try:
        with Robot.connect(host, session=session) as robot:
            teleop = Teleop(robot, linear=linear, angular=angular)
            last_print = 0.0
            for key in _keys():
                now = time.monotonic()
                obs = robot.observe()
                if key:
                    teleop.handle_key(key, obs, now)
                    if teleop.quit:
                        break
                teleop.tick(now)
                if organizer and "session_time_limit" in obs.info.get("inhibit", []):
                    robot.session = organizer.renew()  # a person is at the keys: keep the session going
                    teleop.message = "session renewed"
                if now - last_print > 0.15:
                    last_print = now
                    extra = f"  heartbeat: {organizer.error}" if organizer and organizer.error else ""
                    sys.stdout.write("\r\x1b[K" + (teleop.status_line(obs) + extra)[:200])
                    sys.stdout.flush()
    finally:
        if organizer:
            organizer.stop()
        print("\nteleop ended; the robot is stopped" + (" and its session closed" if organizer else ""))
    return 0
