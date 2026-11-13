"""The real robot, through LeRobot v0.7.0's drivers.

NOT YET RUN ON HARDWARE. Written against the lerobot v0.7.0 source; validate it step by step
with docs/hardware-bringup.md before trusting it.

* base.present: true  -> LeRobot's `LeKiwi` (arm IDs 1-6 + wheels 7-9 on one bus), with the
  wheel kinematics replaced by the geometry in robot.yaml.
* base.present: false -> LeRobot's `SO101Follower` (arm only).

All motor I/O goes through LeRobot's own `send_action` / `get_observation`, so register
encoding and calibration handling stay upstream's.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
from buildathon import protocol as P

from ..kinematics import BaseKinematics
from .base import Backend

log = logging.getLogger("buildathon.real")

WHEELS = ("base_left_wheel", "base_back_wheel", "base_right_wheel")
MAX_CONSECUTIVE_BUS_ERRORS = 10
WRIST_ROLL_WRAP_MARGIN_DEG = 20


def _camera_configs(cam) -> dict:
    """LeRobot camera config for the one USB camera, or {} if it is not plugged in."""
    from lerobot.cameras.configs import Cv2Rotation
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig

    device = Path(cam.device)
    if not cam.device or not device.exists():
        log.warning("camera device %r not found: starting WITHOUT a camera. Run the doctor tool to find it.", cam.device)
        return {}
    rotation = {
        0: Cv2Rotation.NO_ROTATION,
        90: Cv2Rotation.ROTATE_90,
        180: Cv2Rotation.ROTATE_180,
        270: Cv2Rotation.ROTATE_270,
        -90: Cv2Rotation.ROTATE_270,
    }[int(cam.rotation_deg)]
    return {
        cam.name: OpenCVCameraConfig(
            index_or_path=device,
            fps=30,
            width=cam.width,
            height=cam.height,
            fourcc=cam.fourcc or None,
            rotation=rotation,
        )
    }


def make_robot(config, with_camera: bool = True):
    """Build the LeRobot robot object for this configuration (not yet connected)."""
    real = config.real
    cameras = _camera_configs(config.camera) if with_camera else {}
    calibration_dir = Path(real.calibration_dir)
    if config.base.present:
        from lerobot.robots.lekiwi import LeKiwi, LeKiwiConfig

        kin = BaseKinematics.from_config(config.base)

        class KiwiBase(LeKiwi):
            """LeKiwi with wheel kinematics from robot.yaml instead of hard-coded constants."""

            name = "lekiwi"  # same name as stock LeKiwi, so `lerobot-calibrate` files are shared

            def _body_to_wheel_raw(self, x, y, theta, **_):
                return dict(zip(WHEELS, kin.body_to_wheel_raw(x, y, theta)))

            def _wheel_raw_to_body(self, left_wheel_speed, back_wheel_speed, right_wheel_speed, **_):
                vx, vy, wz = kin.wheel_raw_to_body([left_wheel_speed, back_wheel_speed, right_wheel_speed])
                return {"x.vel": vx, "y.vel": vy, "theta.vel": wz}

        return KiwiBase(LeKiwiConfig(port=real.serial_port, id=real.robot_id, cameras=cameras, calibration_dir=calibration_dir))

    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    return SO101Follower(
        SO101FollowerConfig(
            port=real.serial_port, id=f"{real.robot_id}_arm_only", cameras=cameras, calibration_dir=calibration_dir
        )
    )


class RealBackend(Backend):
    mode = "real"
    realtime = True

    def __init__(self, config, **_):
        self.config = config
        self.has_base = config.base.present
        self.robot = None
        self._last_state = dict.fromkeys(P.ALL_KEYS, 0.0)
        self._bus_errors = 0
        self._consecutive_errors = 0
        self._health: dict = {}
        self._health_t = 0.0
        self._base_torque_on = True

    # ------------------------------------------------------------------ lifecycle

    def preflight(self) -> dict[str, float]:
        """Checks made BEFORE torque is enabled. Reads only; raises RuntimeError with what to fix.

        Returns the measured arm pose in degrees.
        """
        if self.robot is None:
            self.robot = make_robot(self.config)
        robot, bus = self.robot, self.robot.bus
        prefix = "arm_" if self.has_base else ""
        bus.connect()  # the port and a handshake: reads only
        try:
            if not robot.calibration or not robot.is_calibrated:
                raise RuntimeError(
                    f"no calibration matching the motors at {robot.calibration_fpath}. "
                    "Run the calibrate tool first: see docs/hardware-bringup.md"
                )
            names = [f"{prefix}{j}" for j in (*P.ARM_JOINTS, P.GRIPPER)]
            pose = {n.removeprefix("arm_"): float(v) for n, v in bus.sync_read("Present_Position", names, num_retry=3).items()}
            volts = min(bus.sync_read("Present_Voltage", normalize=False, num_retry=3).values()) / 10.0
        finally:
            bus.disconnect(disable_torque=False)  # close the port; torque untouched

        log.info("pre-flight: arm at %s, servo supply %.1f V", {k: round(v, 1) for k, v in pose.items()}, volts)
        roll = pose["wrist_roll"]
        if abs(roll) > 180 - WRIST_ROLL_WRAP_MARGIN_DEG:
            raise RuntimeError(
                f"wrist roll reads {roll:.0f} degrees, within {WRIST_ROLL_WRAP_MARGIN_DEG} degrees of where its encoder "
                "wraps from +180 to -180. If it crossed that point under power it would spin almost a full turn. "
                "Turn the wrist by hand to roughly the middle of its travel (near 0) and start again."
            )
        min_v = self.config.safety.min_servo_voltage
        if min_v > 0 and volts < min_v:
            raise RuntimeError(f"servo supply is {volts:.1f} V, below the configured minimum of {min_v:.1f} V")
        for joint, angle in pose.items():
            if joint == P.GRIPPER:
                continue
            lo, hi = self.config.limits.joints_deg[joint]
            if not lo <= angle <= hi:
                log.warning(
                    "pre-flight: %s is at %.0f, outside its limit [%.0f, %.0f]. It will hold there, and move "
                    "inside the limit the first time it is commanded.", joint, angle, lo, hi,
                )  # fmt: skip
        return pose

    def connect(self) -> None:
        self.robot = make_robot(self.config)
        self.preflight()
        # From here torque comes on. LeRobot's connect() switches torque off to configure the
        # motors, then on: the arm then holds whatever pose it is in.
        self.robot.connect(calibrate=False)
        self.stop_base()
        self.set_base_enabled(self.config.base.enabled)
        self._last_state = self._read_state()
        log.info("real robot connected on %s (%s)", self.config.real.serial_port, "arm + base" if self.has_base else "arm only")

    def close(self) -> None:
        if self.robot is not None and self.robot.is_connected:
            try:
                self.robot.disconnect()  # stops the base and releases torque
            except Exception:
                log.exception("error while disconnecting")

    def now(self) -> float:
        return time.monotonic()

    # ------------------------------------------------------------------ state

    def _key(self, key: str) -> str:
        """Our key -> the LeRobot key (SO101Follower has no 'arm_' prefix)."""
        return key if self.has_base else key.removeprefix("arm_")

    def _read_state(self) -> dict[str, float]:
        obs = self.robot.get_observation()
        state = {k: float(obs[self._key(k)]) for k in P.POS_KEYS}
        for k in P.BASE_KEYS:
            state[k] = float(obs.get(k, 0.0)) if self.has_base else 0.0
        self._frame = obs.get(self.config.camera.name)
        return state

    def _guard(self, fn, what: str):
        """Tolerate an occasional corrupted packet; give up after several in a row."""
        try:
            result = fn()
            self._consecutive_errors = 0
            return result
        except (ConnectionError, RuntimeError) as exc:
            self._bus_errors += 1
            self._consecutive_errors += 1
            log.warning("bus error during %s (%d in a row): %s", what, self._consecutive_errors, exc)
            if self._consecutive_errors >= MAX_CONSECUTIVE_BUS_ERRORS:
                raise
            return None

    def read(self) -> dict[str, float]:
        state = self._guard(self._read_state, "read")
        if state is not None:
            self._last_state = state
        self._read_health()
        return dict(self._last_state)

    def write(self, action: dict[str, float]) -> None:
        out = {self._key(k): float(action[k]) for k in P.POS_KEYS}
        if self.has_base:
            out.update({k: float(action[k]) for k in P.BASE_KEYS})
        self._guard(lambda: self.robot.send_action(out), "write")

    def stop_base(self) -> None:
        if self.has_base and self.robot is not None:
            try:
                self.robot.stop_base()
            except Exception:
                log.exception("stop_base failed")

    def set_base_enabled(self, enabled: bool) -> None:
        """Arm-only mode: wheels are either locked (torque on, zero speed) or free (torque off)."""
        if not self.has_base:
            return
        want_torque = enabled or self.config.base.disabled_behavior != "free"
        if want_torque == self._base_torque_on:
            return
        bus = self.robot.bus
        self.stop_base()
        (bus.enable_torque if want_torque else bus.disable_torque)(list(WHEELS))
        self._base_torque_on = want_torque

    # ------------------------------------------------------------------ camera and health

    def capture(self) -> dict[str, bytes]:
        frame = getattr(self, "_frame", None)
        if frame is None:
            return {}
        ok, buf = cv2.imencode(
            ".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, self.config.camera.jpeg_quality]
        )
        return {self.config.camera.name: buf.tobytes()} if ok else {}

    def _read_health(self) -> None:
        if time.monotonic() - self._health_t < 1.0:
            return
        self._health_t = time.monotonic()
        try:
            bus = self.robot.bus
            volts = bus.sync_read("Present_Voltage", normalize=False)
            temps = bus.sync_read("Present_Temperature", normalize=False)
            self._health = {
                "voltage_min": min(volts.values()) / 10.0,  # register unit is 0.1 V
                "temperature_max": max(temps.values()),
                "bus_errors": self._bus_errors,
            }
        except Exception as exc:  # health is best-effort; never stop control for it
            self._health = {"bus_errors": self._bus_errors, "health_error": str(exc)}

    def extras(self) -> dict:
        return {"health": self._health}
