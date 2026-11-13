---
name: write-behavior
description: Write or change a robot app (behavior) for the Build-a-thon SO-101 vehicle using the buildathon Python SDK. Use when asked to make the robot drive, move its arm, use its gripper, react to its camera, or when creating a new app or team directory.
---

# Write a robot app

An app is a directory with `main.py` (and optionally `app.yaml`, `requirements.txt`). It talks
to the robot only through the `buildathon` SDK and runs unchanged in simulation and on the robot.

## Steps

1. **Create the app** from the template unless one exists:
   `cp -r apps/_template teams/<team-name>` (participant code always goes in `teams/`).
2. **Assume arm-only.** At the event the robot is clamped to a table and the wheels are off
   (`needs_base: false`, the default). Only if the team says it was granted the wheels: set
   `needs_base: true`, test with `robot sim --base`, and check `robot.base_enabled` before driving.
3. **Pick the scene** for testing in `app.yaml`: `table` (default: three small cubes and a
   pad within reach), `pick` (cube on a pedestal), `empty`, or `targets` (for the wheels).
4. **Write `main.py`.** Use a plain `with Robot.connect() as robot:` script for sequences and
   the `Behavior` class for sense-act loops. Read `docs/api.md` for the full API,
   `docs/robot.md` for joint directions, reach and limits, and `docs/cookbook.md` for tested
   programs (driving a distance, going to a point, a colour camera loop, arm sequences, a
   background model thread); copy
   patterns from `apps/06_pick_and_place` (grasp and place), `apps/03_arm_wave` (poses) and
   the cookbook's "find the cubes in the camera picture".
5. **Test** with the `run-sim` skill: run it, look at snapshots or a trace, then pass
   `robot sim-check`.

## Rules that prevent the common failures

- Units: metres, m/s, degrees, deg/s, gripper 0-100. +x forward, +y left, +theta
  counter-clockwise from above.
- Wait with `robot.sleep(seconds)`, never `time.sleep()`: the gate runs in simulated time.
- A drive command expires after 0.5 s. In a control loop call `robot.drive(...)` every
  iteration; `robot.sleep()` and `arm.move_to()` keep the last one alive for you.
- Always end with the base stopped: `with Robot.connect()` and `run(Behavior)` do this.
- Stay inside `robot.limits` (joint ranges, speeds). Out-of-range requests are clamped by the
  robot and fail the gate.
- `obs.image()` is BGR (OpenCV order). Pass `rgb=True` for libraries that expect RGB.
- `obs.odom` drifts and its heading is not wrapped to 0-360.
- `obs.info["truth"]` (ground-truth pose and object positions) exists only in simulation: use
  it for debugging and tests, never in the behavior itself.
- There is no Cartesian arm control: command joint angles or named poses (`robot.arm.poses`).
- `arm.move_to()` waits (and returns False on timeout); `arm.set_joints()`, `arm.pose()` and
  all gripper commands return at once. After a gripper command, `robot.sleep(0.5)`.
- The camera is fixed on a stand and **faces** the robot: the robot's left is on the right of
  the picture. The arm and the pad are yellow; a raised arm can hide part of the table.
- `shoulder_pan` is positive to the robot's right, negative to its left.
- Do not import `lerobot`, open serial ports, or edit anything in `packages/` or
  `config/robot.yaml` limits to make an app work.

## Extra Python packages

List them in `requirements.txt` next to `main.py`. Heavy models (segmentation, VLMs) cannot
run on the robot's Raspberry Pi: see the `offload-perception` skill.
