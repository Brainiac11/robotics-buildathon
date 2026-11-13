"""Print the real robot's joint readings as JSON lines, without commanding anything.

READ-ONLY: opens the serial port and reads positions and wheel speeds. It never enables torque,
never writes a register, and leaves the motors exactly as it found them. Used by the mirror
(scripts/mirror.sh), where the simulated arm follows the real one while you move it by hand.
"""

from __future__ import annotations

import json
import signal
import sys
import time

from buildathon import protocol as P

from ..config import load_config

RATE_HZ = 15


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def main() -> int:
    from ..backends.real_lekiwi import make_robot

    signal.signal(signal.SIGTERM, _interrupt)  # `docker stop` closes the port cleanly

    cfg = load_config()
    robot = make_robot(cfg, with_camera=False)
    if not robot.calibration:
        print(f"no calibration file at {robot.calibration_fpath}: run the calibrate tool first", file=sys.stderr)
        return 1
    bus = robot.bus
    bus.connect()  # the port and a handshake (reads only); NOT robot.connect(), which enables torque
    prefix = "arm_" if cfg.base.present else ""
    arm = [f"{prefix}{j}" for j in (*P.ARM_JOINTS, P.GRIPPER)]
    try:
        if not robot.is_calibrated:
            print("warning: the calibration file does not match the motors; angles may be wrong", file=sys.stderr)
        while True:
            start = time.monotonic()
            try:
                pos = bus.sync_read("Present_Position", arm, num_retry=2)
                line = {f"arm_{name.removeprefix('arm_')}.pos": round(float(v), 2) for name, v in pos.items()}
                if cfg.base.present:
                    raw = bus.sync_read("Present_Velocity", robot.base_motors, num_retry=2)
                    wheels = [raw["base_left_wheel"], raw["base_back_wheel"], raw["base_right_wheel"]]
                    body = robot._wheel_raw_to_body(*wheels)
                    line.update({k: round(float(v), 4) for k, v in body.items()})
                    line["wheels_raw"] = [int(w) for w in wheels]
                print(json.dumps(line), flush=True)
            except (ConnectionError, RuntimeError) as exc:
                print(f"read error: {exc}", file=sys.stderr)
            time.sleep(max(0.0, 1.0 / RATE_HZ - (time.monotonic() - start)))
    except (KeyboardInterrupt, BrokenPipeError):
        return 0
    finally:
        bus.disconnect(disable_torque=False)  # close the port; torque is left as it was


if __name__ == "__main__":
    raise SystemExit(main())
