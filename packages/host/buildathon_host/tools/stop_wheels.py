"""Zero the wheel servos, without the rest of the host. Run after the host exits for any reason.

Wheels are in velocity mode: they keep their last commanded speed if the host dies. This writes
speed 0 to IDs 7, 8, 9 directly. NOT YET RUN ON HARDWARE.
"""

from __future__ import annotations

import sys


def main() -> int:
    from ..config import load_config

    cfg = load_config()
    if not cfg.base.present:
        return 0
    try:
        from lerobot.motors import Motor, MotorNormMode, SerialMotorsBus

        names = ("base_left_wheel", "base_back_wheel", "base_right_wheel")
        bus = SerialMotorsBus(
            port=cfg.real.serial_port,
            motors={n: Motor(i, "sts3215", MotorNormMode.RANGE_M100_100) for n, i in zip(names, (7, 8, 9))},
        )
        bus.connect(handshake=False)
        for _ in range(3):
            bus.sync_write("Goal_Velocity", dict.fromkeys(names, 0), normalize=False)
        bus.disconnect(disable_torque=False)
        print("wheels zeroed")
        return 0
    except Exception as exc:
        print(f"could not zero the wheels: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
