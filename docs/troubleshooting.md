# Troubleshooting

Commands are shown without the `uv run` prefix; add it (`uv run robot status`).

First, ask the robot what is going on:

```bash
uv run robot status        # is anything answering? is motion blocked, and why?
uv run robot snapshot      # can it produce a camera frame?
```

## Participants: simulator and apps

| Symptom | Cause and fix |
|---|---|
| `RobotTimeout: no robot host answered at ...` | The simulator is not running (`robot sim`), or `ROBOT_HOST` points somewhere else. The address shown is the one your app tried |
| `Port ... is already in use` | A simulator is already running. Stop it with `robot stop-sim`, or start another on other ports: `robot sim --port 5660 --dashboard-port 8081`, then `export ROBOT_HOST=localhost:5660` (`--port` takes three ports in a row) |
| The robot starts driving, then stops after half a second | Drive commands expire. Use `robot.sleep()` while driving, or call `drive()` on every pass of your loop |
| `[buildathon] the robot is not moving: motion is blocked (estop)` | Someone pressed STOP. "Clear stop" on the dashboard, or `robot clear-estop` |
| `BaseDisabledError` | Your code tried to drive and the wheels are off, which is the event's default. Remove the driving, or if your team was granted the wheels, test with `robot sim --base` and set `needs_base: true` in `app.yaml` |
| The arm or base is slower than you asked | Safe mode is on (dashboard, or `robot sim --safe-mode`), or you asked for more than the limits in `robot.limits` |
| `arm.move_to()` returns `False` | The arm did not arrive in time: the target is beyond a joint limit, something is in the way, motion is blocked, or `timeout` is too short for a long move in safe mode |
| Gripper not fully open or closed after a short sleep | The jaws need up to a second. Use `gripper.open(wait=True)` |
| `ModuleNotFoundError` for a package you installed | List it in `requirements.txt` next to your `main.py`; `robot run` and the gate install from there |
| Colours work in the simulator but not on the robot | Expected. Retune on real frames: see "Collect real camera frames" in [robot-day.md](robot-day.md) |
| The robot ends up somewhere different each run | Real-time runs depend on timing. The gate (`robot sim-check`) is exactly repeatable; use it to compare changes |
| Objects are not where they were | `robot reset` puts them back (seed 0). A different `--seed` gives a different layout on purpose |
| Dashboard "speed" well under 1.00x | Your machine cannot render fast enough. See "Performance" in [sim.md](sim.md), or close other programs |
| `robot sim` fails with an OpenGL or EGL error | Your machine cannot create a graphics context for the simulator's camera. Use the Docker simulator ("Docker-only workflow" in [getting-started.md](getting-started.md)) |
| `protocol mismatch` | Your copy of the repo is older or newer than the simulator or robot you are talking to. `git pull`, `uv sync`, restart your simulator; if it is the real robot, tell an organizer |
| Docker: the scene resets when you run an app | Start the simulator once with `up sim`, and run apps with `run --rm app` in another terminal |

### The gate (`robot sim-check`)

| Message | Meaning | Fix |
|---|---|---|
| `never connected` | Your app never called `Robot.connect()` | It probably crashed first: read `.simcheck/<app>.log` |
| `exited with error code N` | An exception, or your app called `raise SystemExit("...")` | The last line of its output is shown; the rest is in the `.log` |
| `stalled` | Simulated time stopped for 20 seconds | Your app is blocked on something (input, a network call, an endless wait) |
| warning: `the simulation advanced only 0.1s` | Your app waited without the SDK, so the robot did nothing in the gate | Replace `time.sleep()` with `robot.sleep()` |
| `asked for a joint angle outside its limits` | A target beyond `robot.limits["joints_deg"]` | Keep targets inside the limits |
| `asked for a base speed above the limit` | Above 0.30 m/s or 90 deg/s | Lower the speed |
| `sent drive commands while the base is off` | Driving with the wheels off (the default) | Remove the driving, or set `needs_base: true` in `app.yaml` if your team has the wheels |
| `did not stop within 5s when told to` | Your app ignores the stop signal | Use `with Robot.connect() as robot:` or `run(Behavior)`; do not catch `SystemExit` |
| warning: `the watchdog stopped it` | You left the base driving without fresh commands | `robot.sleep()` while driving, `robot.stop()` when done |
| PASS, but the robot did the wrong thing | The gate does not judge the task | Read the distance line and `.simcheck/<app>.json`; see "A pass is not the same as working" in [getting-started.md](getting-started.md) |

### On the real robot

| Symptom | Cause and fix |
|---|---|
| Dashboard shows "motion blocked" | Normal between runs. During a run: STOP was pressed, or your time ran out. Ask the supervisor; it is not your code |
| Nothing happens and your app prints "motion is blocked" | The same |
| It worked in the simulator and not here | See "What usually goes wrong the first time" in [robot-day.md](robot-day.md) |
| The cube is a centimetre from where your app reaches | The real arm differs slightly from the simulator. Adjust angles on the real arm; prefer sensing (camera, gripper reading) over fixed angles |

## Organizers: robot hardware

These are for whoever runs the robot. Participants do not need them. On the Pi, `TOOLS` is
short for `docker compose -f docker/compose.robot.yaml run --rm tools`.

| Symptom | Cause and fix |
|---|---|
| `/dev/buildathon-bus` missing | Servo board unplugged, the udev rule is not installed (`scripts/pi/bootstrap.sh`), or the `brltty` package is installed and has taken the port |
| "Could not connect on port" although the board is plugged in | Something else holds the port: a running host, or a leftover mirror reader (`docker rm -f buildathon-mirror-reader`) |
| `PRE-FLIGHT FAILED: wrist roll reads ...` | Turn the wrist by hand to the middle of its travel and start again ([teleop.md](teleop.md)) |
| Some motors do not answer | Servo IDs not set (new servos are all ID 1), a loose cable in the chain, or no servo power. `TOOLS doctor` says which |
| Random "Incorrect status packet" or timeouts | Usually power: check `vcgencmd get_throttled` on the Pi and the battery voltage |
| "Illegal instruction" when the host starts on the Pi | A Python package was built for a newer ARM processor than the Pi 4's: see step 2 of [hardware-bringup.md](hardware-bringup.md) |
| "no calibration matching the motors" | Run `TOOLS calibrate`; check the calibration folder has the file |
| Camera frame rate low | `TOOLS doctor --fix-camera` (switches off auto-exposure); add light |
| Camera device name changed | Use the `/dev/v4l/by-id/...-video-index0` path in `robot.yaml`, never `/dev/video0` |
| The arm drops when the host stops | Stopping the host releases torque. Support the arm first |
| A wheel turns the wrong way | `TOOLS wheel-test`, then `base.wheel_direction` in `robot.yaml` |
| The robot curves when told to go straight | Wheel positions or radius wrong in `robot.yaml`, or a wheel is slipping |

Confirmed on this robot so far: the servo board is `1a86:55d3` on `/dev/ttyACM0`, all nine
servos answer, and the supply reads about 11.4 V. The rest of the organizer table has not been
confirmed on this robot yet; add what you learn.
