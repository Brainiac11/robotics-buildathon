# Robotics Build-A-Thon: SO-101 arm

Program an SO-101 robot arm: in simulation on your laptop first, then on the real arm.

```python
from buildathon import Robot

with Robot.connect() as robot:
    robot.arm.move_to("ready")  # a named pose; waits until the arm is there
    robot.arm.move_to(shoulder_pan=-30)  # one joint, in degrees
    robot.gripper.close(wait=True)
    frame = robot.observe().image()  # camera picture as a NumPy array
```

The same code runs against the simulator and the real arm.

## Start here

1. **[Getting started](docs/getting-started.md)**: install, run the simulator, write your
   first app, pass the gate. About fifteen minutes.
2. **[The robot](docs/robot.md)**: the joints, which way they turn, how far the arm reaches,
   the camera, and how the simulator differs from the real thing.
3. **[Cookbook](docs/cookbook.md)**: tested, copy-paste programs for moving the arm, picking
   things up and finding objects with the camera.

The short version, with [uv](https://docs.astral.sh/uv/getting-started/installation/) installed:

```bash
uv sync
uv run robot sim                            # leave running; open http://localhost:8080
uv run robot run apps/06_pick_and_place     # in a second terminal
uv run robot teleop                         # or move the arm yourself from the keyboard
```

Docker instead of uv: see "Docker-only workflow" in [getting started](docs/getting-started.md).

## How the weekend works

1. Copy the template into your own directory: `cp -r apps/_template teams/<your-team>`.
2. Build your project against the simulator.
3. Pass the gate: `uv run robot sim-check teams/<your-team>`, and show your team engineer it
   working. That is "ready for the arm".
4. In your testing slot a supervisor runs your code on the real arm.
5. Demo on Sunday.

Schedule, rules and who to ask: [event information](docs/event-info.md). Making the most of
your slot: [your time on the real arm](docs/robot-day.md).

## More

| | |
|---|---|
| [All documentation](docs/README.md) | Index for participants and organizers, and a command summary |
| [Example apps](apps/README.md) | Small programs to read and run |
| [API reference](docs/api.md) | Every SDK function |
| [Keyboard control](docs/teleop.md) | Move the arm by hand; the quickest way to find joint angles |
| [Working with an AI agent](docs/using-ai-agents.md) | The repo ships rules and skills for coding agents |
| [Troubleshooting](docs/troubleshooting.md) | When something does not work |

## Status

The simulator, SDK and gate are tested and working on Linux; macOS and Windows have not been
tested yet (use the Docker workflow if the native one fails). The real arm responds and its
calibration is loaded, but it has only just been brought up: expect small differences from the
simulator. The robot also has a wheeled base, which is switched off for this event.
[PLAN.md](PLAN.md) has the engineering details.
