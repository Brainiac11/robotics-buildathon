"""Three-wheel base kinematics, driven by measured geometry instead of hard-coded constants.

With the default geometry this reproduces LeRobot's LeKiwi matrix exactly
(`LeKiwi._body_to_wheel_raw` in lerobot v0.7.0). It also covers mecanum-style wheels through
`roller_angle_deg`.

Model, per wheel i:
    p_i  position of the contact point, at angle `wheel_positions_deg[i]` on a circle of radius R
    u_i  rolling direction: tangential, counter-clockwise (p_i rotated +90 degrees)
    n_i  traction direction: u_i rotated by the roller angle (0 for an omni wheel)
The contact point moves at v + w x p_i. The wheel only controls the component along n_i:
    wheel_surface_speed_i = (n_i . (v + w x p_i)) / (n_i . u_i)
"""

from __future__ import annotations

import numpy as np

STEPS_PER_DEG = 4096.0 / 360.0  # STS3215 encoder resolution


class BaseKinematics:
    def __init__(
        self,
        wheel_radius_m: float,
        base_radius_m: float,
        wheel_positions_deg,
        roller_angle_deg=(0.0, 0.0, 0.0),
        wheel_direction=(1.0, 1.0, 1.0),
        max_wheel_raw: int = 3000,
    ):
        self.wheel_radius = float(wheel_radius_m)
        self.max_wheel_raw = int(max_wheel_raw)
        self.direction = np.asarray(wheel_direction, dtype=float)
        rows = []
        for pos_deg, roller_deg in zip(wheel_positions_deg, roller_angle_deg):
            a = np.radians(pos_deg)
            p = base_radius_m * np.array([np.cos(a), np.sin(a)])
            u = np.array([-np.sin(a), np.cos(a)])
            g = np.radians(roller_deg)
            n = np.array([u[0] * np.cos(g) - u[1] * np.sin(g), u[0] * np.sin(g) + u[1] * np.cos(g)])
            gain = float(n @ u)
            if abs(gain) < 1e-6:
                raise ValueError("roller_angle_deg of 90 means the wheel cannot drive; check robot.yaml")
            rows.append([n[0] / gain, n[1] / gain, (p[0] * n[1] - p[1] * n[0]) / gain])
        self.matrix = np.array(rows)  # body (vx, vy, w rad/s) -> wheel surface speed (m/s)
        self.condition = float(np.linalg.cond(self.matrix))
        if not np.isfinite(self.condition) or self.condition > 1e6:
            raise ValueError(
                "this wheel layout cannot move in every direction (kinematics matrix is singular). "
                "Check base.wheel_positions_deg and base.roller_angle_deg in robot.yaml."
            )
        self.inverse = np.linalg.inv(self.matrix)

    def body_to_wheel_degps(self, vx: float, vy: float, wz_deg: float) -> np.ndarray:
        """Body velocity -> wheel angular speeds (deg/s), scaled down together if one saturates."""
        surface = self.matrix @ np.array([vx, vy, np.radians(wz_deg)])
        degps = np.degrees(surface / self.wheel_radius) * self.direction
        peak = float(np.max(np.abs(degps))) * STEPS_PER_DEG
        if peak > self.max_wheel_raw:
            degps = degps * (self.max_wheel_raw / peak)
        return degps

    def wheel_degps_to_body(self, degps) -> tuple[float, float, float]:
        """Wheel angular speeds (deg/s) -> body velocity (vx m/s, vy m/s, wz deg/s)."""
        surface = np.radians(np.asarray(degps, dtype=float) * self.direction) * self.wheel_radius
        vx, vy, w = self.inverse @ surface
        return float(vx), float(vy), float(np.degrees(w))

    def body_to_wheel_raw(self, vx: float, vy: float, wz_deg: float) -> list[int]:
        """Body velocity -> raw servo velocity ticks for (left, back, right)."""
        return [int(max(-0x7FFF, min(0x7FFF, round(d * STEPS_PER_DEG)))) for d in self.body_to_wheel_degps(vx, vy, wz_deg)]

    def wheel_raw_to_body(self, raw) -> tuple[float, float, float]:
        return self.wheel_degps_to_body(np.asarray(raw, dtype=float) / STEPS_PER_DEG)

    @classmethod
    def from_config(cls, base) -> BaseKinematics:
        return cls(
            base.wheel_radius_m,
            base.base_radius_m,
            base.wheel_positions_deg,
            base.roller_angle_deg,
            base.wheel_direction,
            base.max_wheel_raw,
        )
