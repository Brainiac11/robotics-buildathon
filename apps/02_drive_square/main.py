"""Drive a 0.5 m square using wheel odometry. The first thing to try on the real base.

Odometry is integrated from wheel speeds, so it drifts: on the real robot the square will not
close exactly. obs.odom heading is not wrapped (it keeps counting past 360).
"""

import math

from buildathon import Robot

SIDE_M = 0.5
SPEED_M_S = 0.15
TURN_DEG_S = 45


def drive_forward(robot, distance_m):
    obs = robot.observe()
    x0, y0, _ = obs.odom
    while True:
        remaining = distance_m - math.hypot(obs.odom[0] - x0, obs.odom[1] - y0)
        if remaining <= 0.005:
            break
        robot.drive(vx=min(SPEED_M_S, max(0.03, 1.5 * remaining)))  # slow down near the end
        obs = robot.observe()
    robot.stop()
    return robot.sleep(0.4)


def turn_left(robot, angle_deg):
    obs = robot.observe()
    target = obs.odom[2] + angle_deg
    while True:
        remaining = target - obs.odom[2]
        if remaining <= 0.5:
            break
        robot.drive(wz=min(TURN_DEG_S, max(6.0, 2.0 * remaining)))
        obs = robot.observe()
    robot.stop()
    return robot.sleep(0.4)


with Robot.connect() as robot:
    if not robot.base_enabled:
        raise SystemExit("The base is switched off (arm-only mode); this app needs it.")
    for side in range(4):
        drive_forward(robot, SIDE_M)
        obs = turn_left(robot, 90)
        print(f"side {side + 1} done, odometry x={obs.odom[0]:.2f} y={obs.odom[1]:.2f} heading={obs.odom[2]:.0f}")
    print("square complete")
