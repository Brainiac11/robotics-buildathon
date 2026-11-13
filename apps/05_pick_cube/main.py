"""Pick up the cube in the `pick` scene with a fixed sequence of joint angles (no camera).

This is open-loop: the angles below were worked out for where the cube sits in the simulator
with the default seed. Move the cube (robot reset --seed 3) and it will miss. Making it find
the cube with the camera is the interesting part, and is left to you.
"""

from buildathon import Robot

ABOVE = {"shoulder_pan": 0.8, "shoulder_lift": -2.9, "elbow_flex": 10.6, "wrist_flex": 58.0, "wrist_roll": 0.0}
GRASP = {"shoulder_pan": 0.8, "shoulder_lift": 13.3, "elbow_flex": 11.5, "wrist_flex": 49.0, "wrist_roll": 0.0}

with Robot.connect() as robot:
    arm, gripper = robot.arm, robot.gripper

    gripper.open()  # gripper commands return at once...
    arm.move_to(ABOVE, tolerance=2)  # ...move_to waits until the arm arrives
    arm.move_to(GRASP, tolerance=2)
    robot.sleep(0.5)

    gripper.close()
    robot.sleep(1.0)  # give the jaws time to close

    arm.move_to(ABOVE, tolerance=3)
    arm.move_to(shoulder_lift=-30, tolerance=4)
    obs = robot.sleep(0.5)

    # A closed, empty gripper reads about 0. Something between the jaws keeps it open.
    if obs.gripper > 5:
        print(f"holding the cube (gripper at {obs.gripper:.0f})")
    else:
        print("missed: the gripper closed on nothing")
