"""Spin each wheel alone, slowly, so you can confirm IDs and directions.

PUT THE ROBOT ON A STAND WITH ALL WHEELS OFF THE GROUND FIRST. NOT YET RUN ON HARDWARE.

Then drives each body direction briefly (still on the stand) so you can compare with the
simulator: forward (+x), left (+y), turn left (+theta).
"""

from __future__ import annotations

import time

from ..config import load_config
from ..kinematics import STEPS_PER_DEG, BaseKinematics

WHEELS = ("base_left_wheel", "base_back_wheel", "base_right_wheel")
SPIN_DEG_S = 60.0


def main() -> int:
    cfg = load_config()
    if not cfg.base.present:
        print("robot.yaml says base.present is false: no wheels to test.")
        return 1
    answer = input("Are ALL wheels off the ground, with nothing near them? Type 'yes' to continue: ")
    if answer.strip().lower() != "yes":
        print("aborted")
        return 1

    from ..backends.real_lekiwi import make_robot

    robot = make_robot(cfg, with_camera=False)
    robot.connect(calibrate=False)
    bus = robot.bus
    kin = BaseKinematics.from_config(cfg.base)
    raw = int(round(SPIN_DEG_S * STEPS_PER_DEG))
    results = {}
    try:
        for i, wheel in enumerate(WHEELS):
            print(f"\nSpinning {wheel} (ID {7 + i}), position {cfg.base.wheel_positions_deg[i]} deg around the base.")
            print("Expected: looking at the wheel from OUTSIDE the robot, the top of the wheel moves to your RIGHT")
            print("          (which would push the robot counter-clockwise, seen from above).")
            bus.sync_write(
                "Goal_Velocity",
                {w: (raw * int(cfg.base.wheel_direction[i]) if w == wheel else 0) for w in WHEELS},
                normalize=False,
            )
            time.sleep(2.0)
            robot.stop_base()
            results[wheel] = input("  Which wheel moved, and which way? [ok / reversed / wrong-wheel / none]: ").strip().lower()
        print("\nNow the three body directions. With the default layout (back wheel straight behind):")
        print("  FORWARD: the back wheel stays still; left and right wheels spin in opposite directions.")
        print("  LEFT: all three spin; the back wheel fastest.   TURN LEFT: all three spin the same way.")
        for label, body in (("FORWARD (+x)", (0.08, 0, 0)), ("LEFT (+y)", (0, 0.08, 0)), ("TURN LEFT (+theta)", (0, 0, 30))):
            input(f"\nPress Enter to command {label} for 2 s (still on the stand)...")
            bus.sync_write("Goal_Velocity", dict(zip(WHEELS, kin.body_to_wheel_raw(*body))), normalize=False)
            time.sleep(2.0)
            robot.stop_base()
    finally:
        robot.stop_base()
        robot.disconnect()

    print("\nSummary:")
    for i, (wheel, result) in enumerate(results.items()):
        print(f"  {wheel}: {result}")
        if result == "reversed":
            print(f"    -> in config/robot.yaml set base.wheel_direction[{i}] to {-int(cfg.base.wheel_direction[i])}")
        elif result in ("wrong-wheel", "none"):
            print("    -> check the servo ID and wiring (IDs must be left=7, back=8, right=9)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
