# AGENTS.md

Instructions for AI coding agents (and people) working in this repo.

## What this is

Software for the Robotics Build-A-Thon robot: a LeRobot **SO-101 arm** (on a 3-wheel base that
is **switched off for the event**: the robot is clamped to a table), with one fixed USB camera
looking at the table. Participants write Python "apps" against a small SDK, prove them in
simulation, and a supervisor runs them on the one shared real arm from the laptop it is
plugged into. Event details: `docs/event-info.md`.

The same app code runs against the simulator and the real robot. Only `ROBOT_HOST` changes.

## Hard rules

1. **Simulation first.** Never suggest running new code on the real robot before
   `robot sim-check <app>` passes.
2. **Apps talk to the robot only through the `buildathon` SDK.** Never open the serial port,
   import `lerobot` motor classes, or write servo registers from an app.
3. **Do not edit safety limits to make something work.** `config/robot.yaml` limits,
   `packages/host/buildathon_host/safety.py` and the session/heartbeat checks are
   organizer-owned. If a limit blocks a task, say so and ask.
4. **Never run, enable or drive the real robot yourself.** `robot slot`, `robot deploy`, `robot enable`,
   `robot base`, `robot session`, `robot clear-estop`, `robot teleop` against the real robot,
   starting the real host (`scripts/start-robot-host.sh`), and the tools
   that move motors or write to servos (`wheel-test`, `calibrate`, `setup-motors`) are for a
   human organizer. Read-only checks (`tools doctor`, `tools read-joints`, `scripts/mirror.sh`)
   and `robot estop` are always fine.
5. **Participant code lives in `teams/<team-name>/`.** Do not change `packages/` or `apps/`
   for a team's task unless asked; copy `apps/_template` instead.
6. **Use `robot.sleep()`, not `time.sleep()`,** in app code. The gate runs the simulator in
   lockstep, where time only advances through the SDK.

## Commands

```bash
uv sync                                   # one-time setup (Python 3.12, managed by uv)
uv run robot sim                          # simulator: table scene, arm-only; dashboard http://localhost:8080
uv run robot run teams/my-team            # run an app against it (second terminal)
uv run robot run teams/my-team --duration 20 --trace traces/run1   # record state + frames
uv run robot sim-check teams/my-team      # the gate; writes .simcheck/<app>.json and .log
uv run robot snapshot --out snapshots     # save camera + third-person view + state.json
uv run robot status                       # print state; add --json for everything
uv run robot trace --out traces/x --duration 20   # watch-only recording of whatever is running
uv run robot stop-sim                     # stop the simulator you started
uv run robot teleop                       # keyboard control; needs a person at a terminal
uv run pytest                             # tests for SDK, host, safety, sim
```

`run`, `snapshot`, `status`, `reset` and `stop-sim` talk to `$ROBOT_HOST` (default
`localhost`; `--host` overrides). If the default ports are taken, start your own simulator
with `robot sim --port 5660 --dashboard-port 8081` and `export ROBOT_HOST=localhost:5660`;
`--port` takes three consecutive ports. Never stop simulators with `pkill`: other people's
may be running on the same machine.

No Python setup? `docker compose -f docker/compose.sim.yaml up sim`, then
`APP=teams/my-team docker compose -f docker/compose.sim.yaml run --rm app`.

**To see what the robot sees**, run `robot snapshot` and read `snapshots/camera.jpg`,
`snapshots/overview.jpg` (sim only) and `snapshots/state.json`, or read the frames a
`--trace` run wrote. `.simcheck/<app>.log` holds an app's output from the last gate run.

## Writing an app

An app is a directory with `main.py` and an optional `app.yaml`. Start from `apps/_template`.

```python
from buildathon import Robot

with Robot.connect() as robot:  # host from $ROBOT_HOST, default localhost
    obs = robot.observe()  # next observation (about 30 per second)
    image = obs.image()  # HxWx3 uint8, BGR (OpenCV order)
    if robot.base_enabled:  # False at the event: the wheels are off unless organizers enable them
        robot.drive(vx=0.15, wz=20)  # m/s forward, deg/s counter-clockwise
        robot.sleep(1.0)  # keeps the drive command alive
        robot.stop()
    robot.arm.move_to("ready")  # named pose; waits until reached (False after 8 s)
    robot.arm.set_joints(shoulder_pan=20)  # degrees; returns at once
    robot.gripper.open(wait=True)  # 100 = open, 0 = closed; without wait=True it returns at once
```

- **Units:** metres, m/s, degrees, deg/s, gripper 0-100. **Frame:** +x forward, +y left,
  +theta counter-clockwise from above.
- **Joints:** `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`,
  `gripper`. Raw action keys follow LeRobot's LeKiwi: `arm_<joint>.pos`, `x.vel`, `y.vel`,
  `theta.vel`.
- **Base velocity expires** after 0.5 s without a fresh drive command (watchdog).
  `robot.sleep()`, `arm.move_to()` and the `Behavior` runner refresh it for you.
- **Arm-only is the default.** `robot.drive()` raises `BaseDisabledError` unless the base is
  enabled. Write arm apps; only add `needs_base: true` to `app.yaml` if the team was granted
  the wheels (then test with `robot sim --base`).
- **Camera:** fixed on a stand facing the robot, so the picture is mirrored (robot's left is
  image right). `camera: wrist` or `camera: base_front` in `app.yaml` selects another mount
  for the gate.
- `shoulder_pan` is positive to the robot's **right**; negative is left.
- **Limits** are in `robot.limits`. Asking beyond them is clamped by the host and fails the gate.
- `obs.odom` is wheel odometry: it drifts, and its heading is not wrapped to 360.
- The `Behavior` class (`setup` / `step(robot, obs)` / `teardown`) plus `run()` is the
  structured alternative to a plain script; see `apps/_template`.
- Flagship example to copy from: `apps/06_pick_and_place` (pick the red cube, put it on the pad).

Full reference: `docs/api.md`. What the robot can physically do (joint directions, reach,
limits, camera): `docs/robot.md`. Working programs to copy from: `docs/cookbook.md`.

## app.yaml

```yaml
needs_base: false    # true only for apps that drive the wheels (off by default)
scene: table         # sim scene for the gate: table | pick | empty | targets (config/scenes/)
duration_s: 20       # simulated seconds the gate runs
# camera: wrist      # optional: workspace (default) | wrist | base_front
```

## What the gate checks

`robot sim-check` passes when the app connects, runs without crashing, never asks for anything
outside the limits (joint range, base speed, driving while the base is off), and stops within
5 s when told to. It does **not** judge whether the task was solved, and a pass does not mean
the app will work on the real robot.

- An app that finishes early on its own (exit code 0) is fine; the gate prints a note. But
  "0.1s simulated" with a PASS means the app did nothing: it probably waits with `time.sleep()`.
- Extra packages go in the app's `requirements.txt`; `robot run` and `robot sim-check` install
  them through uv automatically.
- Seed 0 is the default layout everywhere (simulator start, `robot reset`, the gate).
- To judge the task yourself, read `.simcheck/<app>.json`: `final_truth` (ground-truth robot
  pose and object positions) and `final_distance_to_objects_m`, recorded with the robot at rest.
- Results go to `.simcheck/` in the repo root (git-ignored). Each run overwrites the app's
  previous result, including runs with `--seed`, `--scene` or `--duration`.
- Exiting with `raise SystemExit("message")` counts as a failure (exit code 1), by design.

## Map

| Path | What |
|---|---|
| `packages/sdk/buildathon/` | The SDK apps import. `robot.py` is the client, `protocol.py` the wire format |
| `packages/host/buildathon_host/` | The robot host: `server.py`, `safety.py`, `kinematics.py`, `dashboard/` |
| `packages/host/buildathon_host/backends/` | `mujoco_sim.py` (simulator), `real_lekiwi.py` (hardware), `mock.py` (tests) |
| `packages/cli/buildathon_cli/` | The `robot` command, the gate (`simcheck.py`), deploy |
| `config/robot.yaml` | The robot: geometry, limits, camera, named poses. Read by sim and real host |
| `config/scenes/` | Simulation scenes |
| `apps/` | Examples and the template |
| `teams/` | Participant code |
| `docker/`, `scripts/pi/` | Images, compose files, Raspberry Pi setup |
| `docs/` | Index in `docs/README.md`. Participants: `getting-started.md`, `robot.md`, `cookbook.md` (tested recipes), `api.md`, `sim.md`, `offload.md`, `robot-day.md`, `using-ai-agents.md`, `troubleshooting.md`. Organizers: `hardware-bringup.md`, `organizer-runbook.md`, `safety.md`, `architecture.md`. Both: `teleop.md` |
| `.agents/skills/`, `.claude/skills/` | Agent skills (same content; edit `.agents/skills/` and run `scripts/sync-skills.py`) |

## Current state (read before assuming a feature exists)

- **Working and tested in simulation:** SDK, host, safety layer, simulator, dashboard, gate,
  arm-only mode, Docker sim flow, event rehearsal (`robot sim --rehearse`).
- **Confirmed on the real robot, read-only:** all nine servos answer (IDs 1-9), `tools doctor`,
  calibration read back into `config/calibration/buildathon.json`, the mirror
  (`scripts/mirror.sh`). No motor has been commanded by this repo's code yet.
- **Written but never run on hardware:** the motion path of `backends/real_lekiwi.py`,
  `tools/wheel_test.py`, `docker/compose.robot.yaml`, `scripts/pi/`, `robot deploy`. Treat as
  drafts until `docs/hardware-bringup.md` is completed.
- **Not built yet:** perception offload worker, replay backend, LeRobot `LeKiwiClient`
  compatibility ports, CI. See `PLAN.md`.
- Geometry in `config/robot.yaml` marked `MEASURE` is LeKiwi defaults, not this robot.

## When changing the repo itself

- Keep the SDK free of heavy dependencies (pyzmq, numpy, opencv only). It must not import
  `lerobot` or `mujoco`.
- A protocol change needs `PROTOCOL_VERSION` bumped in `packages/sdk/buildathon/protocol.py`.
- Run `uv run pytest` and `uv run ruff check .` before finishing; re-run `robot sim-check` on
  the example apps if you touched the SDK, host or sim.
- Docs are tested: `tests/test_docs.py` runs every `# recipe:` block in `docs/cookbook.md`
  through the gate and checks relative links. If you change the SDK, update `docs/api.md`,
  `docs/cookbook.md` and this file in the same change.
