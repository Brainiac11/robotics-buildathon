"""Load config/robot.yaml into typed settings. Environment variables override single values."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from buildathon import protocol as P


def find_repo_root(start: Path | None = None) -> Path:
    env = os.environ.get("BUILDATHON_ROOT")
    if env:
        return Path(env)
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "config" / "robot.yaml").exists():
            return d
    # Fall back to the checkout this file lives in (packages/host/buildathon_host/config.py).
    return Path(__file__).resolve().parents[3]


@dataclass
class BaseConfig:
    present: bool = True
    enabled: bool = True
    disabled_behavior: str = "lock"
    wheel_radius_m: float = 0.05
    base_radius_m: float = 0.125
    wheel_positions_deg: list[float] = field(default_factory=lambda: [60.0, 180.0, -60.0])
    roller_angle_deg: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    wheel_direction: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    max_wheel_raw: int = 3000


@dataclass
class Limits:
    max_linear_m_s: float = 0.30
    max_angular_deg_s: float = 90.0
    max_linear_accel_m_s2: float = 0.6
    max_angular_accel_deg_s2: float = 180.0
    max_joint_speed_deg_s: float = 120.0
    max_gripper_speed_pct_s: float = 200.0
    joints_deg: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "shoulder_pan": (-100.0, 100.0),
            "shoulder_lift": (-95.0, 95.0),
            "elbow_flex": (-92.0, 92.0),
            "wrist_flex": (-90.0, 90.0),
            "wrist_roll": (-150.0, 150.0),
        }
    )
    gripper_pct: tuple[float, float] = (0.0, 100.0)
    safe_mode_scale: float = 0.5

    def position_range(self, key: str) -> tuple[float, float]:
        """Allowed range for a '.pos' key."""
        if key == P.GRIPPER_KEY:
            return self.gripper_pct
        return self.joints_deg[key[len("arm_") : -len(".pos")]]

    def scaled(self, scale: float) -> Limits:
        """A copy with every speed and acceleration limit multiplied by `scale`."""
        return Limits(
            max_linear_m_s=self.max_linear_m_s * scale,
            max_angular_deg_s=self.max_angular_deg_s * scale,
            max_linear_accel_m_s2=self.max_linear_accel_m_s2 * scale,
            max_angular_accel_deg_s2=self.max_angular_accel_deg_s2 * scale,
            max_joint_speed_deg_s=self.max_joint_speed_deg_s * scale,
            max_gripper_speed_pct_s=self.max_gripper_speed_pct_s * scale,
            joints_deg=dict(self.joints_deg),
            gripper_pct=self.gripper_pct,
            safe_mode_scale=self.safe_mode_scale,
        )

    def public(self) -> dict:
        return {
            "max_linear_m_s": self.max_linear_m_s,
            "max_angular_deg_s": self.max_angular_deg_s,
            "max_joint_speed_deg_s": self.max_joint_speed_deg_s,
            "joints_deg": {k: list(v) for k, v in self.joints_deg.items()},
            "gripper_pct": list(self.gripper_pct),
        }


@dataclass
class Safety:
    watchdog_timeout_s: float = 0.5
    heartbeat_required: bool | str = "auto"
    heartbeat_timeout_s: float = 1.0
    session_required: bool | str = "auto"
    max_runtime_s: float = 300.0
    park_on_shutdown: bool = False
    min_servo_voltage: float = 0.0


@dataclass
class Camera:
    name: str = "camera"
    mount: str = "workspace"
    width: int = 640
    height: int = 480
    fps: float = 15.0
    jpeg_quality: int = 80
    fovy_deg: float = 44.0
    device: str = ""
    fourcc: str = "MJPG"
    rotation_deg: int = 0
    mounts: dict = field(default_factory=dict)


@dataclass
class Network:
    port_obs: int = P.DEFAULT_PORT_OBS
    port_cmd: int = P.DEFAULT_PORT_CMD
    port_rpc: int = P.DEFAULT_PORT_RPC
    port_dashboard: int = P.DEFAULT_PORT_DASHBOARD


@dataclass
class Real:
    serial_port: str = "/dev/buildathon-bus"
    robot_id: str = "buildathon"
    calibration_dir: str = "/data/calibration"


@dataclass
class Config:
    root: Path
    name: str = "so101-vehicle"
    base: BaseConfig = field(default_factory=BaseConfig)
    limits: Limits = field(default_factory=Limits)
    safety: Safety = field(default_factory=Safety)
    camera: Camera = field(default_factory=Camera)
    network: Network = field(default_factory=Network)
    real: Real = field(default_factory=Real)
    rate_hz: float = 30.0
    named_poses: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def dt(self) -> float:
        return 1.0 / self.rate_hz

    @property
    def base_active(self) -> bool:
        """Driving is allowed only when the wheels exist and the base is enabled."""
        return self.base.present and self.base.enabled


def _fill(obj, data: dict | None):
    for key, value in (data or {}).items():
        if not hasattr(obj, key):
            raise ValueError(f"unknown setting {key!r} in robot.yaml section {type(obj).__name__}")
        setattr(obj, key, value)
    return obj


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_config(path: str | Path | None = None) -> Config:
    root = find_repo_root()
    path = Path(path) if path else root / "config" / "robot.yaml"
    data = yaml.safe_load(path.read_text()) or {}
    cfg = Config(root=root)
    cfg.name = (data.get("robot") or {}).get("name", cfg.name)
    _fill(cfg.base, data.get("base"))
    lim = data.get("limits") or {}
    _fill(cfg.limits, lim.get("base"))
    arm = dict(lim.get("arm") or {})
    joints = arm.pop("joints_deg", None)
    gripper = arm.pop("gripper_pct", None)
    _fill(cfg.limits, arm)
    if joints:
        cfg.limits.joints_deg = {k: (float(v[0]), float(v[1])) for k, v in joints.items()}
    if gripper:
        cfg.limits.gripper_pct = (float(gripper[0]), float(gripper[1]))
    if "safe_mode_scale" in lim:
        cfg.limits.safe_mode_scale = float(lim["safe_mode_scale"])
    _fill(cfg.safety, data.get("safety"))
    _fill(cfg.camera, data.get("camera"))
    _fill(cfg.network, data.get("network"))
    _fill(cfg.real, data.get("real"))
    cfg.rate_hz = float((data.get("control") or {}).get("rate_hz", cfg.rate_hz))
    cfg.named_poses = (data.get("arm") or {}).get("named_poses_deg", {}) or {}

    missing = set(P.ARM_JOINTS) - set(cfg.limits.joints_deg)
    if missing:
        raise ValueError(f"robot.yaml limits.arm.joints_deg is missing: {', '.join(sorted(missing))}")
    if len(cfg.base.wheel_positions_deg) != 3:
        raise ValueError("robot.yaml base.wheel_positions_deg needs exactly 3 values (left, back, right)")

    # Environment overrides (used by `robot sim --no-base`, compose files and the deploy script).
    enabled = _env_bool("BUILDATHON_BASE_ENABLED")
    if enabled is not None:
        cfg.base.enabled = enabled
    present = _env_bool("BUILDATHON_BASE_PRESENT")
    if present is not None:
        cfg.base.present = present
    mount = os.environ.get("BUILDATHON_CAMERA_MOUNT")
    if mount:
        cfg.camera.mount = mount
    return cfg
