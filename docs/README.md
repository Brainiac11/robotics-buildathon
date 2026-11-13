# Documentation

## I am a participant

| I want to... | Read |
|---|---|
| Install and run my first app | [getting-started.md](getting-started.md) |
| Know what the robot can physically do | [robot.md](robot.md) |
| Copy working code for a common job | [cookbook.md](cookbook.md) |
| Move the arm by hand from the keyboard | [teleop.md](teleop.md) |
| Look up a function | [api.md](api.md) |
| Understand the simulator, scenes and traces | [sim.md](sim.md) |
| Use a neural network or a GPU | [offload.md](offload.md) |
| Get signed off and prepare for my testing slot | [robot-day.md](robot-day.md) |
| Work with an AI coding agent | [using-ai-agents.md](using-ai-agents.md) |
| Fix something that is not working | [troubleshooting.md](troubleshooting.md) |
| Find the schedule, rules and who to ask | [event-info.md](event-info.md) |

The example apps are described in [../apps/README.md](../apps/README.md).

## I am an organizer

| I want to... | Read |
|---|---|
| Bring the hardware up for the first time | [hardware-bringup.md](hardware-bringup.md) |
| Run the arm: power-up, testing slots, power-down | [organizer-runbook.md](organizer-runbook.md) |
| Know what protects people and the robot | [safety.md](safety.md) |
| Understand how the pieces fit | [architecture.md](architecture.md) |
| See what is built and what is not | [../PLAN.md](../PLAN.md) |

## Command summary

```text
robot sim [--scene S] [--safe-mode] [--base]
                                     start the simulator (dashboard on http://localhost:8080)
robot stop-sim                       stop it
robot teleop                         move the arm from the keyboard
robot run <app> [--duration S] [--trace DIR]
                                     run an app against the simulator or robot
robot sim-check <app> [--seed N] [--scene S]
                                     the gate: must pass before the real robot
robot snapshot [--host H] [--out DIR]   save the camera frame and state to files
robot trace [--host H] --out DIR     record state and frames while something else drives
robot status [--host H] [--json]     print the robot's state
robot reset [--seed N]               reset the simulated scene
robot estop [--host H]               stop the robot now
```

Put `uv run` in front of each (the docs sometimes leave it out for brevity).
`robot <command> --help` lists every option. `slot`, `deploy`, `enable`, `base`, `session`,
`safe-mode`, `clear-estop` and `stop-app` are for supervisors on the real robot (see the
[organizer runbook](organizer-runbook.md)); in the simulator they work for anyone, which is
handy for trying things such as `robot base off`.
