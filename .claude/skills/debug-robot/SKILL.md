---
name: debug-robot
description: Diagnose problems with the Build-a-thon robot stack - the simulator not starting, apps that cannot connect, the robot not moving, motion blocked, camera or servo problems on the Raspberry Pi. Use when something about the robot, simulator or an app's connection to them is not working.
---

# Debug the robot stack

Start by finding out which layer is failing. Run these and read the output before changing code.

```bash
uv run robot status              # is a host answering? is motion blocked, and why?
uv run robot status --json       # everything, including safety event counters
uv run robot snapshot            # can it produce a camera frame?
uv run pytest -q                 # is the repo itself healthy?
```

## Reading `robot status`

- **No answer:** no host at `$ROBOT_HOST` (default `localhost:5560`). Start `robot sim`, or
  fix the address/port.
- **motion: BLOCKED** lists reasons:
  - `estop`: someone pressed stop. An organizer clears it (`robot clear-estop`).
  - `no_organizer_heartbeat`: real robot only; an organizer must be running `robot enable`.
  - `no_active_session` / `session_time_limit`: real robot only; the app's session is missing
    or ran out. An organizer starts one (or redeploys).
- **base: OFF (arm-only):** drive commands are being discarded on purpose.
- **safety events** count what the host had to correct: `joint_limit`, `base_speed`,
  `base_disabled`, `invalid_value`, `watchdog` (the app stopped refreshing drive commands).

## Common causes

`docs/troubleshooting.md` has the full tables. The frequent ones:

- Robot moves briefly then stops: drive commands expire after 0.5 s; use `robot.sleep()` or
  call `drive()` every loop.
- Works in real-time sim, fails in the gate: waiting with `time.sleep()`.
- App hangs in `Robot.connect()` for 5 s then `RobotTimeout`: wrong `ROBOT_HOST`.
- Simulator will not start on Linux: OpenGL. Try `MUJOCO_GL=osmesa uv run robot sim`, or the
  Docker simulator (`docker compose -f docker/compose.sim.yaml up sim`).

## Real robot (organizers)

Diagnosis on the Pi is read-only and safe to suggest:

```bash
docker compose -f docker/compose.robot.yaml run --rm tools doctor
docker compose -f docker/compose.robot.yaml logs --tail 80 host
vcgencmd get_throttled           # anything but 0x0 means a power problem
```

`doctor` reports power, serial port, each servo (ID, voltage, temperature) and camera frame
rate, with a fix for each failure. Do not run tools that move motors (`wheel-test`,
`calibrate`, `setup-motors`) or restart the host yourself: tell the organizer what you found
and what you recommend. The hardware code in this repo has not been validated on the robot
yet, so a bug in `backends/real_lekiwi.py` or `tools/` is a real possibility: read the
traceback before blaming the hardware.
