from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import protocol as P


class RobotError(Exception):
    """Base class for SDK errors."""


class RobotTimeout(RobotError):
    """The host did not answer in time. Is the sim or robot host running, and is ROBOT_HOST right?"""


class BaseDisabledError(RobotError):
    """A drive command was sent while the base is switched off (arm-only mode)."""


@dataclass
class Observation:
    """One snapshot of the robot. Units: degrees, m/s, deg/s, gripper 0-100."""

    seq: int
    t: float  # robot time in seconds (simulation time in the sim)
    state: dict[str, float]  # LeKiwi keys, e.g. "arm_shoulder_pan.pos", "x.vel"
    odom: tuple[float, float, float]  # x m, y m, heading deg, integrated from wheel speeds
    base_enabled: bool
    estop: bool
    motion_enabled: bool
    image_seq: int = 0  # increases each time the camera delivers a new frame
    info: dict = field(repr=False, default_factory=dict)  # full header from the host
    _jpeg: dict[str, bytes] = field(repr=False, default_factory=dict)
    _decoded: dict[str, np.ndarray] = field(repr=False, default_factory=dict)

    @property
    def joints(self) -> dict[str, float]:
        """Arm joint angles in degrees, keyed by short name (gripper is 0-100)."""
        return {k[len("arm_") : -len(".pos")]: v for k, v in self.state.items() if k.endswith(".pos")}

    @property
    def gripper(self) -> float:
        return self.state.get(P.GRIPPER_KEY, 0.0)

    @property
    def base_velocity(self) -> tuple[float, float, float]:
        """Measured (vx m/s, vy m/s, wz deg/s) in the robot frame."""
        return tuple(self.state.get(k, 0.0) for k in P.BASE_KEYS)  # type: ignore[return-value]

    @property
    def cameras(self) -> list[str]:
        return list(self._jpeg)

    def jpeg(self, name: str | None = None) -> bytes:
        """The camera frame as JPEG bytes, exactly as sent by the host (no re-encoding)."""
        name = name or self._default_camera()
        return self._jpeg[name]

    def image(self, name: str | None = None, rgb: bool = False) -> np.ndarray:
        """The camera frame as an HxWx3 uint8 array.

        Channel order is BGR (OpenCV's convention) unless rgb=True.
        """
        import cv2

        name = name or self._default_camera()
        if name not in self._decoded:
            buf = np.frombuffer(self._jpeg[name], dtype=np.uint8)
            self._decoded[name] = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        img = self._decoded[name]
        return img[:, :, ::-1] if rgb else img

    def _default_camera(self) -> str:
        if not self._jpeg:
            raise RobotError("this observation has no camera frame")
        return next(iter(self._jpeg))

    @classmethod
    def from_wire(cls, header: dict, images: dict[str, bytes]) -> Observation:
        odom = header.get("odom", {})
        return cls(
            seq=int(header["seq"]),
            t=float(header["t"]),
            state={k: float(v) for k, v in header.get("state", {}).items()},
            odom=(odom.get("x", 0.0), odom.get("y", 0.0), odom.get("theta", 0.0)),
            base_enabled=bool(header.get("base_enabled", True)),
            estop=bool(header.get("estop", False)),
            motion_enabled=bool(header.get("motion_enabled", True)),
            image_seq=int(header.get("img_seq", 0)),
            info=header,
            _jpeg=images,
        )
