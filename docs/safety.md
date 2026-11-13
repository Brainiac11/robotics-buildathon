# Safety

The robot is an arm on a moving base, driven by code written in a hurry. These are the layers
that protect people and the robot, from the strongest to the weakest.

| Layer | Stops | Works when |
|---|---|---|
| **Servo power switch** (physical) | Everything | Always. The only layer that survives any software failure |
| **Host exit handler** (`docker/host-entrypoint.sh`) | Wheels | The host crashes or is stopped |
| **Loop watchdog** (`server.py`) | Wheels | The host hangs (for example a blocked serial read): it exits after 1.5 s |
| **Organizer heartbeat** (`robot enable`) | Base at once, arm freezes | Wi-Fi drops, or the organizer lets go |
| **E-stop** (dashboard STOP, space bar, `robot estop`) | Base at once, arm freezes | Anyone presses it; latched until an organizer clears it |
| **Session** | Commands from other apps | An app without the current session id is ignored; sessions time out |
| **Command watchdog** | Base | An app stops sending drive commands for 0.5 s |
| **Limits** (`config/robot.yaml`) | Excess speed, joint range | Always; safe mode halves the speeds |
| **Arm-only mode** | Base | The base is switched off: every drive command is zeroed |
| **The gate** (`robot sim-check`) | Crashing or limit-breaking apps | Before deployment |

## What each layer does not do

- The **arm holds position** on every software stop. It does not go limp (it would fall) and
  it does not retract. Only the power switch removes arm torque.
- The **gate** proves an app does not crash or break limits in simulation. It does not prove
  the app is safe or correct on the real robot.
- **Limits are joint-space.** Nothing stops the arm hitting the base, the camera or the floor.
- **Nothing senses people or obstacles.** Keep a clear arena and a barrier.
- Participants' containers get no hardware devices, but anyone with SSH to the Pi can do
  anything. Keep the SSH key and the organizer token with organizers.

## Rules for running the real robot

1. One organizer holds `robot enable` and watches the robot the whole time it can move.
2. One person is within reach of the servo power switch.
3. First run of any app is in safe mode (the default for `robot deploy`).
4. The arm must be folded in its rest pose before the host starts: connecting briefly releases
   torque.
5. Nobody reaches into the arm's range while the servos are powered.

## Arm-only mode

Use it whenever the wheels are not needed: bench work, manipulation tasks, a crowded room.

- Per app: `needs_base: false` in `app.yaml` (applies in the gate and on deploy).
- Per deploy: `robot deploy <app> --no-base`.
- At any time: `robot base off` / `robot base on`, or the dashboard button.
- Permanently for a session of the host: `BUILDATHON_BASE_ENABLED=0` in `/opt/buildathon/robot.env`.
- No wheels fitted at all: `base.present: false` in `config/robot.yaml`.

When off, wheels are held still under torque (`disabled_behavior: lock`) or left free to roll
(`free`), as set in `robot.yaml`.
