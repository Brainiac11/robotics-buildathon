---
name: run-sim
description: Run and test a robot app in the Build-a-thon simulator, inspect what the robot did (camera frames, state, traces), and pass the sim-check gate. Use when asked to test, run, debug or verify a robot app, to see what the robot sees, or before any request to deploy to the real robot.
---

# Run and gate an app in simulation

## Fast loop

```bash
uv run robot sim-check teams/<team>      # starts its own private simulator; nothing else needed
```

- Exit code 0 = PASS. Results: `.simcheck/<app>.json` (problems, warnings, safety events,
  final state, ground-truth positions) and `.simcheck/<app>.log` (the app's own output and
  traceback).
- Options: `--scene pick`, `--duration 30`, `--seed 3`. Scene, wheels and camera normally
  come from the app's `app.yaml` (`scene:`, `needs_base:`, `camera:`).
- It is deterministic: the same code gives the same result every time. If the result changed,
  the code changed.

Read the `.log` first when it fails. Each "problem" line says what to change. A "note" that
the app finished by itself is not a problem. Every run overwrites the app's previous result,
so finish with a plain `robot sim-check <app>`.

To check the task was achieved, read `final_truth` and `final_distance_to_objects_m` in the
`.json` (robot at rest after the app ended); the gate also prints the distances.

## Watching a run

```bash
uv run robot sim &                       # real-time simulator (table scene, arm-only), dashboard on http://localhost:8080
uv run robot run teams/<team> --duration 20 --trace traces/run1
uv run robot snapshot --out snapshots    # at any moment
```

- `traces/run1/trace.jsonl`: one JSON object per line (5 per second) with `t`, `state`,
  `command`, `odom`, `events`, `truth`.
- `traces/run1/frame_*.jpg`: what the camera saw, one per second. **Read these images** to
  check what the robot was looking at.
- `snapshots/camera.jpg` (camera), `snapshots/overview.jpg` (third-person view of the scene),
  `snapshots/state.json`.
- `uv run robot status` prints state; `uv run robot reset --seed 1` restarts the scene.
- `uv run robot trace --out traces/watch --duration 20` records without running an app (it
  watches whatever is driving); with `--host <robot address>` it records the real robot.
- Stop the simulator when done with `uv run robot stop-sim`. Never use `pkill`: other
  simulators may be running on the machine.
- `run`, `snapshot`, `status`, `reset` and `stop-sim` use `$ROBOT_HOST` (default `localhost`).
  If the default ports are taken (the error says so), start your own with
  `robot sim --port 5660 --dashboard-port 8081` and `export ROBOT_HOST=localhost:5660`.
  `--port` takes three consecutive ports.

## Interpreting results

| Message | Meaning | Fix |
|---|---|---|
| never connected | App did not call `Robot.connect()` | Check it runs at all: read the `.log` |
| exited with error code N | Exception, or the app called `raise SystemExit("...")` | Its last output line is shown; the rest is in `.simcheck/<app>.log` |
| stalled | Simulated time stopped advancing | Replace `time.sleep()` / blocking calls with `robot.sleep()` |
| joint angle outside its limits | Target beyond `robot.limits["joints_deg"]` | Clamp or change the target |
| base speed above the limit | Above `max_linear_m_s` / `max_angular_deg_s` | Lower the speed |
| drive commands while the base is off | Driving in arm-only mode | Check `robot.base_enabled`, or set `needs_base: true` |
| did not stop within 5s | Ignores the stop signal | Use `with Robot.connect()` / `run(Behavior)` |
| warning: watchdog | Left the base driving without refreshing | `robot.sleep()` while driving, `robot.stop()` after |

## What a PASS means

The app connects, runs without crashing, stays inside limits and stops when told. It does not
mean the task was achieved (check the trace, `final_truth` or snapshots for that), and it does
not mean it will work on the real robot. Only an organizer deploys to the real robot.
