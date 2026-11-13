"""Safety filter between what an app asks for and what the robot is told to do.

Runs once per host tick, so every limit is "per second", independent of how fast an app sends.
The same filter runs in the simulator and on the real robot.

Rules:
* Arm targets are clamped to joint limits and approached at a limited joint speed.
* Base velocity is clamped, ramped with an acceleration limit, and expires: if no base command
  arrives for `watchdog_timeout_s`, the base stops. The arm holds position.
* When motion is not allowed (e-stop, missing organizer heartbeat, no active session) the base is
  zeroed at once and the arm freezes where it was last commanded.
* When the base is disabled (arm-only mode) base velocity is always zero.
"""

from __future__ import annotations

import math
from collections import Counter

from buildathon import protocol as P

from .config import Limits


def _approach(current: float, target: float, max_step: float) -> float:
    delta = target - current
    if abs(delta) <= max_step:
        return target
    return current + math.copysign(max_step, delta)


class SafetyFilter:
    def __init__(self, limits: Limits, dt: float, watchdog_timeout_s: float, full_limits: Limits | None = None):
        self.limits = limits  # what is enforced now (halved in safe mode)
        self.full_limits = full_limits or limits  # the robot's real limits: asking beyond these is an app bug
        self.dt = dt
        self.watchdog_timeout_s = watchdog_timeout_s
        self.events: Counter[str] = Counter()
        self.arm_goal: dict[str, float] = {}  # where the app wants each joint (already clamped)
        self.arm_cmd: dict[str, float] = {}  # what is sent this tick (rate limited)
        self.base_goal = [0.0, 0.0, 0.0]
        self.base_goal_t = -math.inf
        self.base_cmd = [0.0, 0.0, 0.0]
        self._watchdog_fired = True

    def reset(self, measured: dict[str, float]) -> None:
        """Start from the measured pose so nothing jumps when the host starts."""
        self.arm_cmd = {k: float(measured.get(k, 0.0)) for k in P.POS_KEYS}
        self.arm_goal = dict(self.arm_cmd)
        self.base_goal = [0.0, 0.0, 0.0]
        self.base_cmd = [0.0, 0.0, 0.0]
        self.base_goal_t = -math.inf
        self._watchdog_fired = True

    def set_limits(self, limits: Limits) -> None:
        self.limits = limits

    def accept(self, action: dict[str, float], now: float, base_active: bool) -> None:
        """Take a command from the app. Out-of-range values are clamped and counted."""
        lim = self.limits
        for key in P.POS_KEYS:
            if key not in action:
                continue
            value = float(action[key])
            if not math.isfinite(value):
                self.events["invalid_value"] += 1
                continue
            lo, hi = lim.position_range(key)
            if value < lo - 1e-6 or value > hi + 1e-6:
                self.events["joint_limit"] += 1
            self.arm_goal[key] = min(hi, max(lo, value))
        if any(k in action for k in P.BASE_KEYS):
            vx, vy, wz = (float(action.get(k, g)) for k, g in zip(P.BASE_KEYS, self.base_goal))
            if not all(math.isfinite(v) for v in (vx, vy, wz)):
                self.events["invalid_value"] += 1
                return
            if not base_active:
                if vx or vy or wz:
                    self.events["base_disabled"] += 1
                vx = vy = wz = 0.0
            # Clamp to what is enforced now, but only count it against the app when it asked for
            # more than the robot's full limits: in safe mode an honest request is just slowed.
            speed = math.hypot(vx, vy)
            if speed > self.full_limits.max_linear_m_s + 1e-9 or abs(wz) > self.full_limits.max_angular_deg_s + 1e-9:
                self.events["base_speed"] += 1
            if speed > lim.max_linear_m_s + 1e-9:
                vx, vy = vx * lim.max_linear_m_s / speed, vy * lim.max_linear_m_s / speed
            if abs(wz) > lim.max_angular_deg_s + 1e-9:
                wz = math.copysign(lim.max_angular_deg_s, wz)
            self.base_goal = [vx, vy, wz]
            self.base_goal_t = now
            self._watchdog_fired = False

    def tick(self, now: float, *, base_active: bool, motion_ok: bool) -> dict[str, float]:
        """Advance one control period and return the full action to send to the robot."""
        lim, dt = self.limits, self.dt
        if not motion_ok:
            self.arm_goal = dict(self.arm_cmd)  # freeze; a fresh command is needed to move again
            self.base_goal = [0.0, 0.0, 0.0]
            self.base_cmd = [0.0, 0.0, 0.0]
        else:
            for key in P.POS_KEYS:
                speed = lim.max_gripper_speed_pct_s if key == P.GRIPPER_KEY else lim.max_joint_speed_deg_s
                self.arm_cmd[key] = _approach(self.arm_cmd[key], self.arm_goal[key], speed * dt)

            target = self.base_goal
            if now - self.base_goal_t > self.watchdog_timeout_s:
                if not self._watchdog_fired and any(self.base_goal):
                    self.events["watchdog"] += 1
                self._watchdog_fired = True
                self.base_goal = target = [0.0, 0.0, 0.0]
            if not base_active:
                self.base_cmd = [0.0, 0.0, 0.0]
            else:
                # Ramp the linear velocity as a vector, and the turn rate separately.
                dvx, dvy = target[0] - self.base_cmd[0], target[1] - self.base_cmd[1]
                dist = math.hypot(dvx, dvy)
                max_dv = lim.max_linear_accel_m_s2 * dt
                if dist > max_dv:
                    dvx, dvy = dvx * max_dv / dist, dvy * max_dv / dist
                self.base_cmd[0] += dvx
                self.base_cmd[1] += dvy
                self.base_cmd[2] = _approach(self.base_cmd[2], target[2], lim.max_angular_accel_deg_s2 * dt)
        return {**self.arm_cmd, **dict(zip(P.BASE_KEYS, self.base_cmd))}
