# Simulator

MuJoCo (pinned to 3.3.7) with the official SO-101 arm model from MuJoCo Menagerie
(`sim/assets/so101`, Apache-2.0) on a base generated from `config/robot.yaml`.

```bash
uv run robot sim                          # the default: table scene, arm-only, workspace camera
uv run robot sim --scene pick             # cube on a pedestal
uv run robot sim --camera-mount wrist     # camera on the gripper instead
uv run robot sim --safe-mode              # half-speed limits, like a first real run
uv run robot sim --base --scene targets   # wheels enabled (only if your team has them)
uv run robot reset --seed 3               # put everything back; seed moves the objects
uv run robot stop-sim                     # stop it (Ctrl-C in its terminal also works)
uv run robot sim --rehearse               # behave like the real robot: see the organizer runbook
```

Ports: 5560-5562 and 8080 by default. `--port N` uses N, N+1 and N+2; then set
`ROBOT_HOST=localhost:N` for the other commands.

Dashboard: <http://localhost:8080> (camera, third-person view, state, stop button).

## What is and is not modelled

- **Arm:** full dynamics from the Menagerie model, position-controlled like the servos.
- **Base** (only when enabled): a planar body driven by velocity (it cannot tip and the
  wheels do not slip). Real wheels slip and drift; the sim does not.
- **Camera:** rendered at the configured resolution and field of view. Colours, exposure and
  lens distortion differ from the real LifeCam.
- **Not modelled:** servo backlash, battery sag, network delay, camera motion blur.

A pass in sim means "does not crash or break limits", not "works on the robot".

## Scenes

| Scene | What is in it |
|---|---|
| `table` (default) | Three 2.5 cm cubes (red, green, blue) on the table within the arm's reach, and a yellow 10 cm pad to put things on |
| `pick` | A 2.5 cm cube on a 10 cm high pedestal, 0.3 m ahead |
| `empty` | Just the floor |
| `targets` | For the wheels: three 8 cm cubes on the floor about 0.9 m away |

Objects are moved a little (1 cm in `table` and `pick`, up to 5 cm in `targets`) according to a **seed**.
Seed 0 is the default everywhere: when the simulator starts, after `robot reset`, and in the
gate. `robot reset --seed 3` and `robot sim-check <app> --seed 3` give a different, repeatable
layout.

Files in `config/scenes/`. Add one by copying `targets.yaml`: a list of boxes with `pos_m` (the
centre), `size_m` (full edge lengths, so the target blocks are 8 cm cubes), colour and whether
they can move. `randomize.pos_jitter_m` moves objects by a seeded
random amount on reset.

## Camera

The default camera (`workspace`) is fixed on a stand in front of the robot, looking back at
the table: 0.80 m in front of the robot, 0.50 m up, aimed at a point 0.25 m in front of the
robot. Because it faces the robot, the robot's left is on the right of the picture. The pose
is in `config/robot.yaml` (`camera.mounts.workspace`) and will be updated to match the real
camera once that is placed.

`--camera-mount wrist` puts the camera on the gripper instead, and `--camera-mount base_front`
on the front of the wheeled base (for driving). An app can ask the gate for a specific one
with `camera: wrist` in its `app.yaml`.

## Ground truth

Every observation in simulation carries `obs.info["truth"]`: the robot's true `x`, `y`
(metres) and `theta` (degrees, not wrapped), and each movable object's `[x, y, z]` centre.
`robot snapshot` (`state.json`, key `truth`), `robot status --json` (key `status.truth`),
traces (each line's `truth`) and gate results (`final_truth`) include it.

## Real time vs lockstep

- `robot sim` runs in real time. The header's `rtf` (shown as "speed" on the dashboard) drops
  below 1.0 if your machine cannot keep up.
- `robot sim-check` runs its own private simulator in **lockstep**: simulated time advances
  only when the app calls `observe()`/`sleep()`. Results are identical on every machine and
  every run. This is why apps must not wait with `time.sleep()`.

## Recording a run

```bash
uv run robot run teams/my-team --duration 20 --trace traces/run1
```

writes `trace.jsonl` (state, commands, odometry, safety events, sim ground truth, 5 per
second) and a camera frame per second.

`uv run robot trace --out traces/watch` records the same things without running an app: it
only watches whatever is already driving the robot. It also works against the real robot
(`--host <robot address>`).

## Performance

Rendering is the main cost. On Linux the simulator uses the GPU (EGL) when it can and falls
back to software rendering; the Docker image always uses software rendering (about two CPU
cores at 640x480, 15 fps). If the sim is slow, lower `camera.fps` or the resolution in
`config/robot.yaml`. That is a change for your machine only: do not commit it, and remember
the gate and the real robot use 640x480.
