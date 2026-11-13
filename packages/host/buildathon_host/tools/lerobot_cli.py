"""Run LeRobot's own setup tools with this robot's settings filled in.

    python -m buildathon_host.tools.lerobot_cli setup-motors
    python -m buildathon_host.tools.lerobot_cli calibrate

Both are interactive and follow LeRobot's prompts. NOT YET RUN ON HARDWARE.
"""

from __future__ import annotations

import os
import sys

from ..config import load_config

COMMANDS = {"setup-motors": "lerobot-setup-motors", "calibrate": "lerobot-calibrate"}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    cfg = load_config()
    if cfg.base.present:
        robot_args = ["--robot.type=lekiwi", f"--robot.id={cfg.real.robot_id}"]
    else:
        robot_args = ["--robot.type=so101_follower", f"--robot.id={cfg.real.robot_id}_arm_only"]
    cmd = [
        COMMANDS[sys.argv[1]],
        *robot_args,
        f"--robot.port={cfg.real.serial_port}",
        f"--robot.calibration_dir={cfg.real.calibration_dir}",
        "--robot.cameras={}",
    ]
    print("running:", " ".join(cmd))
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    raise SystemExit(main())
