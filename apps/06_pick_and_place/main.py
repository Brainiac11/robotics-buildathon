"""Pick the red cube off the table and put it on the yellow pad (scene: table).

A fixed sequence of joint angles, no camera: it works for where the cube sits by default, and
misses if the cube is somewhere else (try `robot reset --seed 4`). Using the camera to find the
cube first is the natural next step.

How the angles were found: move the arm with `uv run robot teleop` until the gripper is where
you want it, and read the joint angles off the status line.
"""

from buildathon import Robot

# shoulder_pan is negative to the robot's LEFT. The red cube is to the left, the pad further left.
ABOVE_CUBE = {"shoulder_pan": -20.1, "shoulder_lift": 26.9, "elbow_flex": 5.5, "wrist_flex": 41.0, "wrist_roll": 0.0}
AT_CUBE = {"shoulder_pan": -20.1, "shoulder_lift": 48.7, "elbow_flex": -0.8, "wrist_flex": 27.2, "wrist_roll": 0.0}
ABOVE_PAD = {"shoulder_pan": -50.7, "shoulder_lift": 24.5, "elbow_flex": 6.1, "wrist_flex": 40.3, "wrist_roll": 0.0}
AT_PAD = {"shoulder_pan": -50.7, "shoulder_lift": 42.2, "elbow_flex": 1.6, "wrist_flex": 29.5, "wrist_roll": 0.0}

with Robot.connect() as robot:
    arm, gripper = robot.arm, robot.gripper

    print("reaching for the cube")
    gripper.open(wait=True)
    arm.move_to(ABOVE_CUBE, tolerance=2)  # come in from above so the jaws do not knock it over
    arm.move_to(AT_CUBE, tolerance=2)
    robot.sleep(0.3)  # let the arm settle

    closed_fully = gripper.close(wait=True)
    if closed_fully:  # nothing between the jaws
        print("missed: the gripper closed on nothing")
        arm.move_to("home")
        raise SystemExit(1)
    print(f"holding the cube (gripper at {robot.observe().gripper:.0f})")

    print("carrying it to the pad")
    arm.move_to(ABOVE_CUBE, tolerance=3)
    arm.move_to(ABOVE_PAD, tolerance=3)
    arm.move_to(AT_PAD, tolerance=2)
    gripper.open(wait=True)

    arm.move_to(ABOVE_PAD, tolerance=3)
    arm.move_to("home")
    print("done")
