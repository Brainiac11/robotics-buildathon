# Supervisor and organizer runbook

How to run the real arm during the Build-a-thon. The arm's servo board is plugged into the
**arm laptop** by USB; there is no Raspberry Pi in the loop this weekend. (The Pi setup in
`scripts/pi/` and `docker/compose.robot.yaml` is for later and has not been run.)

> `robot slot` and `robot teleop` are tested in simulation and in rehearsal mode. On the real
> arm, only the read-only checks have been run so far. Do the dry run below before the event
> relies on it, and keep LeRobot's own teleoperation as the fallback.

## Arm laptop: one-time setup

```bash
git clone https://github.com/Brainiac11/robotics-buildathon.git && cd robotics-buildathon
uv sync
docker build -f docker/Dockerfile.host-real -t buildathon-host-real .     # a few minutes
```

Needs Linux, Docker, uv, and your user in the `dialout` group (`groups` shows it).

## Powering up (Sol: Friday 5:00, Saturday 11:00, Sunday 8:00)

1. Arm clamped inside the taped zone, folded in its rest pose, nothing within reach of it.
2. Servo power on. USB plugged into the arm laptop.
3. Terminal 1, in the repo:

   ```bash
   ./scripts/start-robot-host.sh
   ```

   It runs a read-only pre-flight (calibration, voltage, wrist roll not near its wrap point),
   then asks you to type `yes` before enabling torque. The wheels are locked off by default.
   Leave this terminal open: it is the robot host. Dashboard: <http://localhost:8080>.
4. Terminal 2: check it by hand, then run the backup demo.

   ```bash
   uv run robot teleop                         # tap one joint at a time; x to quit
   uv run robot slot apps/03_arm_wave          # the backup demo: poses and a wave, at half speed
   ```

If the pre-flight fails it says what to fix and leaves torque off.

## Running a testing slot

```bash
git pull                                       # get the team's code (or: git fetch && git checkout <their branch>)
uv run robot slot teams/<team>                 # FIRST RUN: safe mode (half speed)
uv run robot slot teams/<team> --full-speed    # later runs, once the first looked sane
```

`robot slot` does the six steps in the ops playbook in one command:

1. Re-runs the gate on the team's code. It refuses to continue if the gate fails.
2. Sets safe mode (unless `--full-speed`) and keeps the wheels off.
3. Holds the robot enabled and runs the app, showing its output. **The arm can move only
   while this command is running.**
4. Stops when the app finishes, after 3 minutes (`--max-runtime 300` to change), or when you
   press **Ctrl-C**.
5. Blocks motion again and reports any safety events.
6. Asks for a one-line note and appends it to `slots/slot-log.md`. The app's full output is
   saved next to it. Hand the log to the next supervisor.

Useful extras:

| | |
|---|---|
| A team asks for real camera frames | `uv run robot snapshot --out snapshots/<team>` and send them the files |
| Move the arm back to rest between teams | `uv run robot teleop` |
| A team's app needs extra packages | It has a `requirements.txt`; they install automatically on first run (needs internet) |
| Skip the gate for a quick re-run of unchanged code | `--skip-check` |
| A team that was granted the wheels | Restart the host with `./scripts/start-robot-host.sh --base` (robot unclamped, on a stand first), then `robot slot teams/<team> --base` |

## Stopping

| Situation | Do |
|---|---|
| Stop this run | **Ctrl-C** in the `robot slot` terminal |
| Anything looks wrong | STOP on the dashboard (or space bar there), or `uv run robot estop` |
| The arm is not responding to that | **Unplug the servo power.** That is the kill switch |
| After an e-stop | Fix the cause. The next `robot slot` clears it |

## Powering down (9 PM Friday, 8 PM Saturday, after demos Sunday)

1. Move the arm to its rest pose with `uv run robot teleop`, or support it by hand.
2. Ctrl-C in terminal 1. **The arm goes limp when the host stops.**
3. Servo power off. Cover the arm.

## When something breaks

| Problem | Fix |
|---|---|
| `PRE-FLIGHT FAILED: wrist roll reads ...` | Turn the wrist by hand to the middle of its travel; start again |
| `No servo board found` / "Could not connect on port" | USB cable; another program holding the port (`docker ps`, then `docker rm -f buildathon-host buildathon-mirror-reader`) |
| "no calibration matching the motors" | A servo was replaced or recalibrated. Recalibrate with LeRobot, then copy the new file to `config/calibration/buildathon.json` |
| `The robot host refused: ... needs the organizer token` | Run from the repo folder so `.robot-token` is found; it is created by `start-robot-host.sh` |
| "motion blocked" on the dashboard between runs | Normal. The arm only moves during `robot slot` or `robot teleop` |
| Random timeouts or "Incorrect status packet" in terminal 1 | Power or a loose servo cable. `uv run robot status --json` shows `health` with the supply voltage |
| The host stopped by itself | Read the last lines in terminal 1, start it again (arm folded first) |
| A servo is dead | Swap it, set its ID and recalibrate with LeRobot's tools, update the calibration file, run the backup demo |
| This software misbehaves and time is short | Fall back to LeRobot's own teleoperation and scripts, which do not depend on this repo |
| House Wi-Fi fails | The arm laptop needs internet only for `git pull` and first-time package installs: use a phone hotspot |

## Rehearse without the arm

`uv run robot sim --rehearse` makes the simulator behave like the real robot: nothing moves
unless a slot or teleop is running. Practise the whole routine with it:

```bash
export BUILDATHON_ORGANIZER_TOKEN=practice
uv run robot sim --rehearse                    # terminal 1
uv run robot slot apps/06_pick_and_place       # terminal 2
uv run robot teleop
```

## After the weekend: the Raspberry Pi

To run the robot untethered, with its wheels, the host moves onto a Pi on the robot:
[hardware-bringup.md](hardware-bringup.md) and `robot deploy`. None of that has been run on
hardware yet.
