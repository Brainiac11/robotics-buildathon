"""MuJoCo simulation of the vehicle: the official SO-101 model on a base generated from robot.yaml.

The base is a planar body (two slides and a yaw hinge) driven by velocity actuators. Wheels are
drawn at their configured positions but do not carry the robot: this keeps the sim fast, stable
and CPU-friendly. Wheel-contact physics can replace it later without changing the interface.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import mujoco
import numpy as np
import yaml
from buildathon import protocol as P

from ..kinematics import BaseKinematics
from .base import Backend

ARM_MODEL_JOINTS = P.ARM_JOINTS + (P.GRIPPER,)
MAX_PHYSICS_DT = 0.005  # the SO-101 model is tuned for 5 ms


def load_scene(root: Path, name: str) -> dict:
    path = root / "config" / "scenes" / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in (root / "config" / "scenes").glob("*.yaml"))
        raise FileNotFoundError(f"no scene {name!r}; available scenes: {', '.join(available)}")
    scene = yaml.safe_load(path.read_text()) or {}
    scene.setdefault("name", name)
    scene.setdefault("objects", [])
    return scene


def build_xml(config, scene: dict, timestep: float) -> str:
    """Generate the MJCF for the whole world from robot.yaml and a scene file."""
    base, cam = config.base, config.camera
    r, R = base.wheel_radius_m, base.base_radius_m
    plate_z, plate_h = r + 0.03, 0.015
    top_z = plate_z + plate_h
    so101 = (config.root / "sim" / "assets" / "so101" / "so101.xml").as_posix()

    wheels = []
    if base.present:
        for i, pos_deg in enumerate(base.wheel_positions_deg):
            a = math.radians(pos_deg)
            cx, cy = math.cos(a), math.sin(a)
            wheels.append(
                f'<geom name="wheel{i}" type="cylinder" size="{r} 0.01" '
                f'fromto="{(R - 0.012) * cx:.4f} {(R - 0.012) * cy:.4f} {r} {(R + 0.012) * cx:.4f} {(R + 0.012) * cy:.4f} {r}" '
                f'rgba="0.1 0.1 0.1 1" contype="0" conaffinity="0" mass="0.1"/>'
            )

    mount = (cam.mounts or {}).get("base_front") or {}
    cpos = mount.get("pos_m", [0.16, 0.0, 0.13])
    pitch = math.radians(float(mount.get("pitch_down_deg", 20)))
    base_cam = (
        f'<camera name="base_front" pos="{cpos[0]} {cpos[1]} {cpos[2]}" '
        f'xyaxes="0 -1 0 {math.sin(pitch):.4f} 0 {math.cos(pitch):.4f}" fovy="{cam.fovy_deg}"/>'
    )

    ws = (cam.mounts or {}).get("workspace") or {}
    wpos = np.array(ws.get("pos_m", [0.80, 0.0, 0.50]), dtype=float)
    forward = np.array(ws.get("look_at_m", [0.25, 0.0, 0.05]), dtype=float) - wpos
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    workspace_cam = (
        f'<camera name="workspace" pos="{wpos[0]} {wpos[1]} {wpos[2]}" mode="fixed" fovy="{cam.fovy_deg}" '
        f'xyaxes="{right[0]:.4f} {right[1]:.4f} {right[2]:.4f} {up[0]:.4f} {up[1]:.4f} {up[2]:.4f}"/>'
    )

    objects = []
    for obj in scene["objects"]:
        # size_m is the full size (edge lengths); MuJoCo wants half-sizes.
        size = " ".join(str(float(s) / 2) for s in obj.get("size_m", [0.04, 0.04, 0.04]))
        pos = " ".join(str(p) for p in obj["pos_m"])
        rgba = " ".join(str(c) for c in obj.get("rgba", [0.8, 0.2, 0.2, 1]))
        kind = obj.get("type", "box")
        joint = "<freejoint/>" if obj.get("movable", True) else ""
        mass = f'mass="{obj.get("mass_kg", 0.02)}"' if obj.get("movable", True) else ""
        objects.append(
            f'<body name="{obj["name"]}" pos="{pos}">{joint}'
            f'<geom name="{obj["name"]}" type="{kind}" size="{size}" rgba="{rgba}" {mass} '
            f'friction="1.0 0.02 0.001" condim="4"/></body>'
        )

    start = scene.get("robot_start", {})
    return f"""
<mujoco model="so101_vehicle">
  <compiler angle="radian" autolimits="true"/>
  <option integrator="implicitfast" timestep="{timestep:.6f}" cone="elliptic" impratio="10"/>
  <size memory="64M"/>
  <asset>
    <model name="so101" file="{so101}"/>
    <texture type="skybox" builtin="gradient" rgb1="0.75 0.82 0.9" rgb2="0.95 0.95 0.95" width="256" height="1536"/>
    <texture name="floor" type="2d" builtin="checker" rgb1="0.62 0.62 0.6" rgb2="0.52 0.52 0.5" width="512" height="512"/>
    <material name="floor" texture="floor" texrepeat="10 10" reflectance="0"/>
  </asset>
  <visual>
    <global offwidth="1280" offheight="960"/>
    <headlight ambient="0.45 0.45 0.45" diffuse="0.5 0.5 0.5" specular="0 0 0"/>
    <quality shadowsize="2048"/>
  </visual>
  <worldbody>
    <light pos="0 0 3" dir="0.2 0.1 -1" directional="true" diffuse="0.5 0.5 0.5"/>
    <geom name="floor" type="plane" size="6 6 0.1" material="floor" friction="1.0 0.02 0.001"/>
    <camera name="overview" pos="-0.9 -1.1 0.95" xyaxes="0.77 -0.63 0 0.33 0.4 0.85" mode="fixed" fovy="55"/>
    {workspace_cam}
    <camera name="overview_track" pos="-0.9 -1.1 0.95" mode="targetbody" target="chassis" fovy="45"/>
    <body name="chassis" pos="{start.get("x", 0.0)} {start.get("y", 0.0)} 0">
      <joint name="base_x" type="slide" axis="1 0 0"/>
      <joint name="base_y" type="slide" axis="0 1 0"/>
      <joint name="base_yaw" type="hinge" axis="0 0 1"/>
      <geom name="chassis" type="cylinder" size="{R + 0.02:.4f} {plate_h}" pos="0 0 {plate_z:.4f}" mass="2.5" rgba="0.18 0.2 0.26 1"/>
      <geom name="chassis_front" type="box" size="0.012 0.03 0.004" pos="{R:.4f} 0 {top_z + 0.004:.4f}" rgba="0.95 0.5 0.1 1" contype="0" conaffinity="0" mass="0.001"/>
      {" ".join(wheels)}
      {base_cam}
      <body name="arm_mount" pos="0 0 {top_z:.4f}">
        <attach model="so101" body="base" prefix="arm_"/>
      </body>
    </body>
    {" ".join(objects)}
  </worldbody>
  <actuator>
    <velocity name="base_x" joint="base_x" kv="300" forcerange="-40 40"/>
    <velocity name="base_y" joint="base_y" kv="300" forcerange="-40 40"/>
    <velocity name="base_yaw" joint="base_yaw" kv="30" forcerange="-8 8"/>
  </actuator>
</mujoco>
"""


class MujocoBackend(Backend):
    mode = "sim"

    def __init__(self, config, realtime: bool = True, scene: str = "empty", render: bool = True, **_):
        self.config = config
        self.realtime = realtime
        self.scene_name = scene
        self.render = render
        self.kin = BaseKinematics.from_config(config.base)
        self._renderer: mujoco.Renderer | None = None
        self._body_cmd = (0.0, 0.0, 0.0)

    # ------------------------------------------------------------------ lifecycle

    def connect(self) -> None:
        cfg = self.config
        self.scene = load_scene(cfg.root, self.scene_name)
        self.substeps = max(1, math.ceil(cfg.dt / MAX_PHYSICS_DT))
        self.model = mujoco.MjModel.from_xml_string(build_xml(cfg, self.scene, cfg.dt / self.substeps))
        self.data = mujoco.MjData(self.model)
        m = self.model
        self._qadr = {j: int(m.joint(f"arm_{j}").qposadr[0]) for j in ARM_MODEL_JOINTS}
        self._act = {j: m.actuator(f"arm_{j}").id for j in ARM_MODEL_JOINTS}
        self._grip_range = tuple(float(v) for v in m.actuator("arm_gripper").ctrlrange)
        self._base_q = [int(m.joint(n).qposadr[0]) for n in ("base_x", "base_y", "base_yaw")]
        self._base_v = [int(m.joint(n).dofadr[0]) for n in ("base_x", "base_y", "base_yaw")]
        self._base_act = [m.actuator(n).id for n in ("base_x", "base_y", "base_yaw")]
        self._cam = {"wrist": "arm_wrist_cam", "base_front": "base_front"}.get(cfg.camera.mount, "workspace")
        m.cam_fovy[m.camera(self._cam).id] = cfg.camera.fovy_deg
        self._objects = {o["name"]: o for o in self.scene["objects"] if o.get("movable", True)}
        self.reset(self.scene.get("seed"))
        if self.render:
            self._renderer = mujoco.Renderer(m, cfg.camera.height, cfg.camera.width)

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def reset(self, seed: int | None = None) -> None:
        if seed is None:
            seed = self.scene.get("seed")  # the scene's own default: what start-up and the gate use
        m, d = self.model, self.data
        mujoco.mj_resetData(m, d)
        home = self.config.named_poses.get("home", {})
        for joint in P.ARM_JOINTS:
            rad = math.radians(float(home.get(joint, 0.0)))
            d.qpos[self._qadr[joint]] = rad
            d.ctrl[self._act[joint]] = rad
        d.ctrl[self._act[P.GRIPPER]] = self._grip_range[0]
        d.qpos[self._qadr[P.GRIPPER]] = self._grip_range[0]
        start = self.scene.get("robot_start", {})
        d.qpos[self._base_q[2]] = math.radians(float(start.get("theta_deg", 0.0)))
        jitter = float(self.scene.get("randomize", {}).get("pos_jitter_m", 0.0))
        if jitter and seed is not None:
            rng = np.random.default_rng(seed)
            for name in self._objects:
                adr = int(m.joint(m.body(name).jntadr[0]).qposadr[0])
                d.qpos[adr : adr + 2] += rng.uniform(-jitter, jitter, 2)
        self._body_cmd = (0.0, 0.0, 0.0)
        mujoco.mj_forward(m, d)

    # ------------------------------------------------------------------ state

    def now(self) -> float:
        return float(self.data.time)

    @property
    def _yaw(self) -> float:
        return float(self.data.qpos[self._base_q[2]])

    def read(self) -> dict[str, float]:
        d = self.data
        state = {f"arm_{j}.pos": math.degrees(float(d.qpos[self._qadr[j]])) for j in P.ARM_JOINTS}
        lo, hi = self._grip_range
        # Clamped to 0-100 like LeRobot's normalised reading on the real gripper.
        state[P.GRIPPER_KEY] = min(100.0, max(0.0, float(100.0 * (d.qpos[self._qadr[P.GRIPPER]] - lo) / (hi - lo))))
        if self.config.base.present:
            wx, wy, w = (float(d.qvel[i]) for i in self._base_v)
            c, s = math.cos(self._yaw), math.sin(self._yaw)
            body = (c * wx + s * wy, -s * wx + c * wy, math.degrees(w))
            # Report what the wheel encoders would: body -> wheel speeds -> body.
            vx, vy, wz = self.kin.wheel_degps_to_body(self.kin.body_to_wheel_degps(*body))
        else:
            vx = vy = wz = 0.0
        state.update({"x.vel": vx, "y.vel": vy, "theta.vel": wz})
        return state

    def write(self, action: dict[str, float]) -> None:
        d = self.data
        for joint in P.ARM_JOINTS:
            d.ctrl[self._act[joint]] = math.radians(action[f"arm_{joint}.pos"])
        lo, hi = self._grip_range
        d.ctrl[self._act[P.GRIPPER]] = lo + (hi - lo) * action[P.GRIPPER_KEY] / 100.0
        if self.config.base.present:
            # Through the wheel model, so wheel-speed saturation behaves like the real base.
            wheels = self.kin.body_to_wheel_degps(action["x.vel"], action["y.vel"], action["theta.vel"])
            self._body_cmd = self.kin.wheel_degps_to_body(wheels)
        else:
            self._body_cmd = (0.0, 0.0, 0.0)

    def step(self, dt: float) -> None:
        d = self.data
        vx, vy, wz = self._body_cmd
        for _ in range(self.substeps):
            c, s = math.cos(self._yaw), math.sin(self._yaw)
            d.ctrl[self._base_act[0]] = c * vx - s * vy
            d.ctrl[self._base_act[1]] = s * vx + c * vy
            d.ctrl[self._base_act[2]] = math.radians(wz)
            mujoco.mj_step(self.model, d)

    def stop_base(self) -> None:
        self._body_cmd = (0.0, 0.0, 0.0)

    # ------------------------------------------------------------------ cameras

    def _render(self, camera: str, quality: int) -> bytes:
        self._renderer.update_scene(self.data, camera=camera)
        rgb = self._renderer.render()
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()

    def capture(self) -> dict[str, bytes]:
        if self._renderer is None:
            return {}
        return {self.config.camera.name: self._render(self._cam, self.config.camera.jpeg_quality)}

    def overview(self) -> bytes | None:
        if self._renderer is None:
            return None
        return self._render("overview_track", 75)

    def extras(self) -> dict:
        d = self.data
        truth = {
            "x": float(d.qpos[self._base_q[0]]) + float(self.scene.get("robot_start", {}).get("x", 0.0)),
            "y": float(d.qpos[self._base_q[1]]) + float(self.scene.get("robot_start", {}).get("y", 0.0)),
            "theta": math.degrees(self._yaw),
            "objects": {name: [round(float(v), 4) for v in d.body(name).xpos] for name in self._objects},
        }
        return {"truth": truth, "scene": self.scene["name"]}
