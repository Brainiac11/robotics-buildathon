---
name: hardware-bringup
description: Guide an organizer through first power-on and validation of the real Build-a-thon robot (Raspberry Pi 4, SO-101 arm, wheel servos, camera) step by step. Use only when an organizer explicitly asks for help bringing up, calibrating or validating the physical robot.
metadata:
  organizer: "true"
---

# Hardware bring-up (organizer, human in the loop)

The procedure is `docs/hardware-bringup.md`. Follow it in order; do not skip ahead.

## How to help

- **One step at a time.** Give the organizer the next command, wait for them to paste the
  output, interpret it, then continue. Tick off the checklist as you go.
- **You do not run motor-moving commands.** The organizer runs them at the robot. You may run
  read-only checks (`tools doctor`, logs, `vcgencmd get_throttled`) if you have a shell on the Pi.
- **Before any step that moves something**, restate the physical precondition from the doc
  (wheels off the ground, arm folded, hand on the servo power switch) and ask for confirmation.
- **Record what was learned.** Measurements go into `config/robot.yaml` (replace the values
  marked `MEASURE`); fixes and surprises go into `docs/troubleshooting.md`; calibration files
  get copied to `config/calibration/`. Propose these edits as you go.

## Things that are expected to need fixing

Nothing under `packages/host/buildathon_host/backends/real_lekiwi.py`, `tools/`,
`docker/compose.robot.yaml` or `scripts/pi/` has run on hardware. When something fails:

1. Check whether stock LeRobot shows the same failure (`tools stock-host`,
   `lerobot-calibrate`). If it does, the cause is hardware or LeRobot setup.
2. If only this repo's code fails, read the traceback against LeRobot v0.7.0's source and fix
   the code; keep the fix minimal and note it.
3. A Raspberry Pi 4 "Illegal instruction" on import is a known risk (step 2 of the doc).

## After the geometry is measured

Run `uv run pytest tests/test_kinematics.py` and `uv run robot sim-check apps/02_drive_square`
on a laptop: the simulator is built from the same `robot.yaml`, so a wrong wheel layout shows
up there first. If the wheels are mecanum-style, set `roller_angle_deg` and confirm sideways
motion on the stand before trusting it.

## Do not

Raise limits in `config/robot.yaml`, disable the heartbeat or session requirement, or skip the
failure drills (step 9) to save time.
