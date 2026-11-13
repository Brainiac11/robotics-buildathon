---
name: run-event
description: Help an organizer operate the shared Build-a-thon robot during the event - deploying a team's app to the real robot, arm-only deployments, tethered slots, stopping and recovery. Use only when an organizer explicitly asks to deploy to, operate or recover the real robot.
metadata:
  organizer: "true"
disable-model-invocation: true
---

# Run the event (organizer)

The procedure is `docs/organizer-runbook.md`; safety layers are in `docs/safety.md`.

## Deploying a team's app

1. Check the station has `ROBOT_SSH`, `ROBOT_HOST` and `BUILDATHON_ORGANIZER_TOKEN` set.
2. Run the gate yourself first and read the result: `uv run robot sim-check teams/<team>`.
   Look at `.simcheck/<team>.json`: warnings, `final_truth`, and whether `needs_base` matches
   what the app does.
3. Skim the team's `main.py` for anything the gate cannot see: very long blocking calls,
   network access, files written outside its directory, speeds right at the limits.
4. Tell the organizer the exact command and what it will do; **they** run it:
   - `uv run robot deploy teams/<team>` (safe mode, 180 s, base per `app.yaml`)
   - `--no-base` to force arm-only, `--full-speed` only after a clean safe-mode run.
5. Remind them: `robot enable` must be held in another terminal, and someone is at the servo
   power switch.

Never run `robot deploy`, `robot enable`, `robot base on`, `robot clear-estop` or
`robot session start` yourself. `robot estop`, `robot status` and `robot stop-app` are fine
to run if asked.

## Arm-only by default when in doubt

If the room is crowded, the base is misbehaving, or a team only needs the arm: `robot base off`
(or deploy with `--no-base`). The app's drive commands are then discarded by the robot.

## When something goes wrong

Use the "Stopping" and "Recovering" tables in the runbook. Read `robot status` and the host
log before proposing a fix. `robot deploy` and the Pi-side setup have not been proven on the
hardware yet: if a deploy step fails, report the failing command and its output rather than
retrying blindly.
