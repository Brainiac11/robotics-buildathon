"""Move the arm through named poses and wave. Uses only the arm, so it runs in arm-only mode."""

from buildathon import Robot

with Robot.connect() as robot:
    arm, gripper = robot.arm, robot.gripper
    print(f"named poses: {', '.join(arm.poses)}")

    arm.move_to("ready")
    gripper.open()
    for _ in range(3):
        arm.move_to(shoulder_pan=30, wrist_roll=40, tolerance=4)
        arm.move_to(shoulder_pan=-30, wrist_roll=-40, tolerance=4)
    gripper.close()
    arm.move_to("home")
    print("wave complete")
