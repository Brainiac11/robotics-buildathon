"""A small structure for algorithms: subclass Behavior, implement step(), call run()."""

from __future__ import annotations

from .robot import Robot
from .types import Observation


class Behavior:
    """Override the methods you need.

    class Spin(Behavior):
        rate_hz = 10
        def step(self, robot, obs):
            robot.drive(wz=30)

    if __name__ == "__main__":
        run(Spin())
    """

    rate_hz: float = 15.0

    def setup(self, robot: Robot) -> None:
        """Called once after connecting."""

    def step(self, robot: Robot, obs: Observation) -> bool | None:
        """Called `rate_hz` times per second of robot time. Return False to finish."""

    def teardown(self, robot: Robot) -> None:
        """Called once before disconnecting, even after an error or Ctrl-C."""


def run(behavior: Behavior, host: str | None = None, duration: float | None = None) -> None:
    """Connect, run the behavior until it returns False (or `duration` seconds pass), then stop."""
    with Robot.connect(host) as robot:
        try:
            behavior.setup(robot)
            obs = robot.observe()
            start = obs.t
            next_step = obs.t
            period = 1.0 / behavior.rate_hz
            while duration is None or obs.t - start < duration:
                if obs.t >= next_step:
                    next_step += period
                    if next_step < obs.t:  # fell behind: do not try to catch up
                        next_step = obs.t + period
                    if behavior.step(robot, obs) is False:
                        break
                elif robot._base_cmd:
                    robot._send(robot._base_cmd)
                obs = robot.observe()
        except KeyboardInterrupt:
            pass
        finally:
            try:
                behavior.teardown(robot)
            finally:
                robot.stop()
