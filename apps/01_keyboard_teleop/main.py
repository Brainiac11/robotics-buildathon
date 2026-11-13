"""Drive the robot from the keyboard. Run it in a terminal:  robot run apps/01_keyboard_teleop

  w/s forward/back   a/d left/right   q/e turn   space stop
  1/2/3 arm poses home/ready/up       o/c gripper open/close   x quit

The base only moves while keys keep arriving (hold the key down); it stops by itself otherwise.
"""

import sys
import time

from buildathon import Robot

SPEED, TURN = 0.15, 40
KEYS = {"w": (SPEED, 0, 0), "s": (-SPEED, 0, 0), "a": (0, SPEED, 0), "d": (0, -SPEED, 0), "q": (0, 0, TURN), "e": (0, 0, -TURN)}
POSES = {"1": "home", "2": "ready", "3": "up"}


def key_reader():
    """Yield single key presses without waiting for Enter ('' when no key is pending)."""
    if sys.platform == "win32":
        import msvcrt

        while True:
            yield msvcrt.getwch() if msvcrt.kbhit() else ""
    else:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0)
                yield sys.stdin.read(1) if ready else ""
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


if not sys.stdin.isatty():
    print("keyboard teleop needs an interactive terminal; nothing to do here")
    raise SystemExit(0)

print(__doc__)
with Robot.connect() as robot:
    last_drive_key = 0.0
    for key in key_reader():
        key = key.lower()
        if key == "x":
            break
        if key in KEYS and robot.base_enabled:
            robot.drive(*KEYS[key])
            last_drive_key = time.monotonic()
        elif key in KEYS:
            print("base is switched off (arm-only mode)")
        elif key == " ":
            robot.stop()
        elif key in POSES:
            robot.arm.pose(POSES[key])
        elif key == "o":
            robot.gripper.open()
        elif key == "c":
            robot.gripper.close()
        elif not key and time.monotonic() - last_drive_key > 0.3:
            robot.stop()
        robot.observe()  # paces the loop at the robot's rate
