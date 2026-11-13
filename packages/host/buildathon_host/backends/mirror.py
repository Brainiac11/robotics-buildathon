"""Mirror: the simulated robot copies joint readings arriving on standard input.

Fed by `tools/read_joints.py` (the real robot, read-only). Commands from apps are ignored.
Use it to compare the real arm with the simulated one while moving the real arm by hand.
"""

from __future__ import annotations

import json
import math
import os
import signal
import sys
import threading
import time

import mujoco
from buildathon import protocol as P

from .mujoco_sim import MujocoBackend


class MirrorBackend(MujocoBackend):
    mode = "mirror"

    def connect(self) -> None:
        super().connect()
        self._latest = dict.fromkeys(P.ALL_KEYS, 0.0)
        self._wheels_raw: list[int] = []
        self._last_line_t = 0.0
        self._lines = 0
        threading.Thread(target=self._read_stdin, daemon=True, name="mirror-stdin").start()

    def _read_stdin(self) -> None:
        for line in sys.stdin:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            self._wheels_raw = data.pop("wheels_raw", [])
            self._latest.update({k: float(v) for k, v in data.items() if k in P.ALL_KEYS})
            self._last_line_t = time.monotonic()
            self._lines += 1
        # The reader has gone (stopped, or the serial port was taken by the robot host): a mirror
        # showing a frozen pose would mislead, so shut down.
        os.kill(os.getpid(), signal.SIGTERM)

    def write(self, action: dict[str, float]) -> None:
        pass  # a mirror only watches

    def step(self, dt: float) -> None:
        d, s = self.data, self._latest
        for joint in P.ARM_JOINTS:
            d.qpos[self._qadr[joint]] = math.radians(s[f"arm_{joint}.pos"])
        lo, hi = self._grip_range
        d.qpos[self._qadr[P.GRIPPER]] = lo + (hi - lo) * s[P.GRIPPER_KEY] / 100.0
        # Move the simulated base the way the wheel readings say the real one is moving.
        yaw = float(d.qpos[self._base_q[2]])
        vx, vy, wz = (s[k] for k in P.BASE_KEYS)
        d.qpos[self._base_q[0]] += (vx * math.cos(yaw) - vy * math.sin(yaw)) * dt
        d.qpos[self._base_q[1]] += (vx * math.sin(yaw) + vy * math.cos(yaw)) * dt
        d.qpos[self._base_q[2]] += math.radians(wz) * dt
        d.qvel[:] = 0
        d.time += dt
        mujoco.mj_forward(self.model, d)

    def read(self) -> dict[str, float]:
        return dict(self._latest)

    def overview(self) -> bytes | None:
        """A close view that stays with the robot, from the front-left."""
        if self._renderer is None:
            return None
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [float(self.data.qpos[self._base_q[0]]) + 0.05, float(self.data.qpos[self._base_q[1]]), 0.2]
        cam.distance, cam.azimuth, cam.elevation = 0.95, 135, -22
        return self._render(cam, 80)

    def extras(self) -> dict:
        age = time.monotonic() - self._last_line_t if self._lines else None
        return {
            "scene": self.scene["name"],
            "mirror": {"readings": self._lines, "age_s": None if age is None else round(age, 2), "wheels_raw": self._wheels_raw},
        }
