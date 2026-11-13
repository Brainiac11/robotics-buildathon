"""Template app. Copy this directory to teams/<your-team>/ and edit.

Run it:      uv run robot sim                       (in one terminal)
             uv run robot run teams/<your-team>     (in another)
Gate it:     uv run robot sim-check teams/<your-team>

This uses the Behavior style: step() is called `rate_hz` times a second with the latest
observation. A plain `with Robot.connect() as robot:` script works just as well; see
docs/getting-started.md and docs/cookbook.md.

Units: metres, m/s, degrees, deg/s, gripper 0-100. Frame: +x forward, +y left.
"""

from buildathon import Behavior, run


class MyBehavior(Behavior):
    rate_hz = 15  # how often step() is called, in robot time

    def setup(self, robot):
        print(f"connected to the {robot.mode} robot; base enabled: {robot.base_enabled}")
        robot.arm.pose("home")

    def step(self, robot, obs):
        # obs.joints         arm angles in degrees
        # obs.base_velocity  measured (vx, vy, wz)
        # obs.odom           (x, y, heading) from wheel odometry; drifts over time
        # obs.image()        camera frame, HxWx3 uint8, BGR
        #
        # robot.drive(vx, vy, wz)     set base velocity (check robot.base_enabled first)
        # robot.arm.set_joints(...)   set joint targets in degrees
        # robot.gripper.open() / close()
        #
        # Return False to finish.
        return obs.t < 5.0

    def teardown(self, robot):
        print("done")


if __name__ == "__main__":
    run(MyBehavior())
