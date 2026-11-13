# Example apps

Run any of them against the simulator: `uv run robot sim` in one terminal,
`uv run robot run apps/<name>` in another. Each is short enough to read in a couple of minutes.

**The arm** (the Build-a-thon setup; these all run with the wheels off)

| App | Scene | What it teaches |
|---|---|---|
| [00_hello](00_hello/main.py) | any | Connecting, reading joints and limits, saving a camera frame. Moves nothing |
| [03_arm_wave](03_arm_wave/main.py) | `table` | Named poses, joint angles, the gripper |
| [06_pick_and_place](06_pick_and_place/main.py) | `table` | Picking the red cube off the table and putting it on the pad; telling whether the gripper is holding something. **Start here** |
| [05_pick_cube](05_pick_cube/main.py) | `pick` | Lifting a cube off a pedestal (`uv run robot sim --scene pick`) |
| [_template](_template/main.py) | `table` | The starting point for your own app |

**The wheels** (off at the event; these need `uv run robot sim --base`)

| App | Scene | What it teaches |
|---|---|---|
| [02_drive_square](02_drive_square/main.py) | `empty` | Driving a distance and turning an angle with odometry |
| [04_follow_color](04_follow_color/main.py) | `targets`, with `--camera-mount base_front` | A camera loop that drives to a coloured block, and the `Behavior` class |
| [01_keyboard_teleop](01_keyboard_teleop/main.py) | any | A minimal keyboard-control app, to read as code |

To move the robot by hand, use `uv run robot teleop` ([docs/teleop.md](../docs/teleop.md)).

To start your own: `cp -r apps/_template teams/<your-team>`. Do not edit the examples in
place; copy what you need. More building blocks are in [docs/cookbook.md](../docs/cookbook.md).

`05_pick_cube` and `06_pick_and_place` are deliberately open-loop: they replay fixed joint
angles, so they only work with the cube in its default place (`uv run robot reset --seed 4`
makes them miss). Making one find the cube with the camera is a good first challenge.
