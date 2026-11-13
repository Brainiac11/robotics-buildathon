"""A physics-free stand-in: joints and base follow commands exactly. For tests and smoke checks."""

from __future__ import annotations

import math
import time

import cv2
import numpy as np
from buildathon import protocol as P

from .base import Backend


class MockBackend(Backend):
    mode = "mock"

    def __init__(self, config, realtime: bool = True, **_):
        self.config = config
        self.realtime = realtime
        self._t = 0.0
        self._state = dict.fromkeys(P.ALL_KEYS, 0.0)
        self._pose = [0.0, 0.0, 0.0]
        self._frame = 0

    def connect(self) -> None:
        self._t0 = time.monotonic()

    def now(self) -> float:
        return time.monotonic() - self._t0 if self.realtime else self._t

    def read(self) -> dict[str, float]:
        return dict(self._state)

    def write(self, action: dict[str, float]) -> None:
        self._state.update(action)
        if not self.config.base.present:
            for k in P.BASE_KEYS:
                self._state[k] = 0.0

    def step(self, dt: float) -> None:
        self._t += dt
        vx, vy, wz = (self._state[k] for k in P.BASE_KEYS)
        th = math.radians(self._pose[2])
        self._pose[0] += (vx * math.cos(th) - vy * math.sin(th)) * dt
        self._pose[1] += (vx * math.sin(th) + vy * math.cos(th)) * dt
        self._pose[2] += wz * dt

    def capture(self) -> dict[str, bytes]:
        cam = self.config.camera
        self._frame += 1
        img = np.full((cam.height, cam.width, 3), 40, np.uint8)
        cv2.putText(img, f"mock frame {self._frame}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, cam.jpeg_quality])
        return {cam.name: buf.tobytes()}

    def reset(self, seed: int | None = None) -> None:
        self._state = dict.fromkeys(P.ALL_KEYS, 0.0)
        self._pose = [0.0, 0.0, 0.0]
        self._t = 0.0

    def extras(self) -> dict:
        return {"truth": {"x": self._pose[0], "y": self._pose[1], "theta": self._pose[2]}}
