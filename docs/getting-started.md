# Getting started

From nothing to your own app passing the gate, in about fifteen minutes. Everything here runs
on your laptop in simulation; no robot needed.

At the Build-a-thon the robot is an **SO-101 arm clamped to a table**, with a camera on a stand
looking at the table in front of it. The simulator starts in exactly that setup.

## 1. Install

You need **git** and **one** of the two setups below.

### Option A: uv (recommended)

[uv](https://docs.astral.sh/uv/getting-started/installation/) installs the right Python
(3.12) and every dependency for you.

```bash
git clone https://github.com/Brainiac11/robotics-buildathon.git
cd robotics-buildathon
uv sync
```

`uv sync` downloads about 300 MB the first time. Do it on good Wi-Fi.

Every command below starts with `uv run`, which runs it inside the project's environment.

### Option B: Docker only

If you would rather not install Python tooling, or the simulator will not start natively on
your machine, use Docker (Docker Desktop on macOS and Windows). See
[Docker-only workflow](#docker-only-workflow) at the end of this page.

> Tested on Linux, natively and in Docker. macOS and Windows have **not** been tested yet: if
> Option A fails there, use Option B, and tell an organizer what you saw.

## 2. Start the simulator

```bash
uv run robot sim
```

You should see a line ending in:

```text
host up: backend=sim lockstep=False base=OFF (arm-only) ports=5560/5561/5562 dashboard=http://localhost:8080
```

Leave it running and open <http://localhost:8080>. This is the **dashboard**:

- **Camera**: what the robot's camera sees: the arm, three small cubes and a yellow pad on
  the table. The camera faces the robot, so the robot's left is on the right of the picture.
- **Simulator view**: the robot from outside (simulation only).
- **State**: joint angles, live.
- **STOP**: stops the robot at once (also the space bar). "Clear stop" releases it.
- **Safe mode**: halves the speed limits, as on a first run on the real robot.
- **speed 1.00x** (top): how fast the simulation runs compared with real time. Well under
  1.00 means your computer is struggling to keep up.

"base OFF (arm-only)" is expected: the robot has wheels, but they are switched off for this
event. The token box, "Hold robot enabled" and the session buttons are for organizers on the
real robot; in the simulator you can ignore them. "Safety events" counts requests the robot
had to refuse or correct (for example a joint angle beyond its limit).

## 3. Run an example

In a second terminal, in the same folder:

```bash
uv run robot run apps/00_hello            # prints what the robot reports
uv run robot run apps/03_arm_wave         # moves through poses and waves
uv run robot run apps/06_pick_and_place   # picks up the red cube and puts it on the pad
uv run robot reset                        # puts the cubes back
uv run robot teleop                       # move the arm yourself from the keyboard; x to quit
```

Watch the dashboard while they run. [apps/README.md](../apps/README.md) describes each
example, and `robot teleop` shows its keys when it starts ([teleop.md](teleop.md)).

## 4. Write your own app

```bash
cp -r apps/_template teams/my-team        # use your team's name instead of my-team, here and below
uv run robot run teams/my-team
```

The template connects, folds the arm, waits five seconds and exits. You should see:

```text
connected to the sim robot; base enabled: False
done
```

Nothing moves yet: that is your part. The template is written in the `Behavior` style (a
class whose `step()` is called repeatedly; good for "look, decide, act" loops, explained in
[api.md](api.md)). The other style is a plain script, which is easier to start with. To try
it, replace the contents of `teams/my-team/main.py` with:

```python
from buildathon import Robot

with Robot.connect() as robot:  # connects to the simulator (or the robot)
    obs = robot.observe()  # what the robot knows right now
    print(obs.joints)

    robot.arm.move_to("ready")  # a named pose; waits until the arm is there
    robot.arm.move_to(shoulder_pan=-30)  # one joint: 30 degrees to the robot's left
    robot.gripper.open(wait=True)
    robot.gripper.close(wait=True)
    robot.arm.move_to("home")

    image = robot.observe().image()  # the camera picture, as a NumPy array
    print(image.shape)
```

Run it again and watch the dashboard: the arm rises, swings left, works its gripper and folds
away. Both styles work everywhere; use whichever suits the task.

Four things to know from the start:

1. **Units:** degrees for joints; the gripper is 0 (closed) to 100 (open). The six joints are
   `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll` and `gripper`.
   [robot.md](robot.md) says which way each one turns.
2. **Wait with `robot.sleep()`, not `time.sleep()`.** In the gate, simulated time only moves
   when your app calls the SDK, so an app that waits with `time.sleep()` does nothing there.
3. **`move_to()` waits for the arm; `set_joints()` does not.** Joints move at a limited speed
   and stop at their limits (`robot.limits`). There is no "move the gripper to x, y, z"
   command: you command joint angles. Find angles for a spot by moving the arm there with
   `uv run robot teleop` and reading them off.
4. **Images are BGR**, the OpenCV convention: `obs.image()` goes straight into `cv2` functions.

Next: [cookbook.md](cookbook.md) for ready-made pieces (finding the cubes with the camera,
picking things up), [api.md](api.md) for the full reference, [robot.md](robot.md) for what the
arm can physically do.

### Extra Python packages

List them in a `requirements.txt` next to your `main.py`, one per line. `robot run` and
`robot sim-check` then install them for your app automatically (the first run downloads them;
later runs are instant), and the same file is used when your app runs on the real arm.

### What you may change

Work inside `teams/<your-team>/`. Only that directory is taken to the real robot. You can edit
other files locally to experiment (for example `config/robot.yaml`), but the robot and the
organizers' gate use their own copies, so your app must not depend on such changes. Keep your
own arm poses as dictionaries in your code, not as named poses in `robot.yaml`.

### What about the wheels?

The robot has a wheeled base, switched off for this event. If the organizers enable it for
your team, `uv run robot sim --base` gives you a robot that drives, and the last section of
the [cookbook](cookbook.md) has the recipes. Otherwise ignore everything about driving.

## 5. See what happened

```bash
uv run robot snapshot                     # writes snapshots/camera.jpg, overview.jpg, state.json
uv run robot status                       # prints the robot's state
uv run robot run teams/my-team --duration 20 --trace traces/run1
```

`--duration 20` stops your app after 20 seconds of real time, if it has not finished by then.
`--trace` records the run: `traces/run1/trace.jsonl` has the state five times a second, and
there is one camera frame per second next to it. Use it to work out why the robot did what
it did.

`apps/00_hello` and some cookbook recipes save a picture to your system's temporary folder
and print where.

## 6. Pass the gate

```bash
uv run robot sim-check teams/my-team
```

The gate runs your app in its own private simulator (you do not need `robot sim` running) and
prints `PASS` or `FAIL`:

```text
sim-check my-team: scene=table base=off (arm-only) duration=20s simulated, seed=0
  note: the app finished by itself after 5.1s simulated, which is fine if it was done
  robot ended at rest; distance from its centre to: green_cube 0.31 m, red_cube 0.32 m, blue_cube 0.37 m
PASS: my-team (5.1s simulated, 3 commands) -> .simcheck/my-team.json
```

It passes when your app connects, does not crash, stays inside the robot's limits, and stops
within five seconds when told to. If it fails, each `problem:` line says what to change, and
`.simcheck/my-team.log` has your app's output.

Tell the gate about your app in `teams/my-team/app.yaml`:

```yaml
needs_base: false    # true only if your app drives the wheels (off by default at the event)
scene: table         # table | pick | empty | targets
duration_s: 30       # how many simulated seconds the gate runs it for
```

### A pass is not the same as working

The gate does **not** check that your app does its job. Check that yourself, from what the
gate tells you:

- **`simulated`** is how long the robot actually ran. `0.1s simulated` with a PASS means
  your app did nothing in the gate, usually because it waits with `time.sleep()`.
- `.simcheck/my-team.json` has the details: `final_state` (joint angles at the end) and
  `final_truth` (the true position of every object, so you can see whether the cube really
  ended up on the pad), plus `warnings` and `problems`.
- `.simcheck/my-team.log` is everything your app printed.

Objects are placed slightly differently depending on a **seed**. The gate uses seed 0. Try
others to make sure your app is not relying on one exact layout:

```bash
uv run robot sim-check teams/my-team --seed 1
uv run robot reset --seed 1               # the same layout in the simulator you are watching
```

**You must pass the gate, and show your team engineer your app working in the simulator,
before your app goes on the real arm.** The first real run is in safe mode (half speed);
`uv run robot sim --safe-mode` lets you see what that does to your app.

## 7. Get on the real arm

How sign-off, testing slots and demos work, and how to make the most of your time on the arm,
is in [robot-day.md](robot-day.md). The schedule is in [event-info.md](event-info.md).

## When you are done

```bash
uv run robot stop-sim                     # or Ctrl-C in the simulator's terminal
```

## Common first problems

| You see | Do this |
|---|---|
| `RobotTimeout: no robot host answered` | The simulator is not running (start `uv run robot sim`), or `ROBOT_HOST` points somewhere else |
| `Port ... is already in use` | A simulator is already running. `uv run robot stop-sim`, or see below |
| `[buildathon] the robot is not moving: motion is blocked (estop)` | Someone pressed STOP. Press "Clear stop" on the dashboard, or `uv run robot clear-estop` |
| `BaseDisabledError` | Your code tried to drive, and the wheels are off. That is the event's default; see "What about the wheels?" |
| The simulator will not start (OpenGL error) | Use the Docker-only workflow below |
| Dashboard "speed" well under 1.00x | Your machine is rendering slowly; see [sim.md](sim.md), "Performance" |

More in [troubleshooting.md](troubleshooting.md).

### Two simulators on one machine

Start the second one on other ports and point your commands at it:

```bash
uv run robot sim --port 5660 --dashboard-port 8081
export ROBOT_HOST=localhost:5660          # PowerShell: $env:ROBOT_HOST = "localhost:5660"
```

`--port` uses three ports in a row (5660, 5661 and 5662 here).

## Docker-only workflow

```bash
docker compose -f docker/compose.sim.yaml up sim
```

The first run builds the images (a few minutes). The dashboard is at <http://localhost:8080>.
In a second terminal, run an app in a container:

```bash
# Linux and macOS
APP=apps/06_pick_and_place docker compose -f docker/compose.sim.yaml run --rm app

# Windows PowerShell
$env:APP = "apps/06_pick_and_place"; docker compose -f docker/compose.sim.yaml run --rm app
```

Choose the scene when you start the simulator:

```bash
SCENE=pick docker compose -f docker/compose.sim.yaml up sim       # scene: table | pick | empty | targets
```

(PowerShell: `$env:SCENE = "pick"` on its own line first.)

Extra Python packages: list them in `requirements.txt` next to your `main.py`; they are
installed the first time the app runs.

Stop everything with `docker compose -f docker/compose.sim.yaml down`.

The gate (`robot sim-check`) needs the uv setup. If you only have Docker, ask your team
engineer or an organizer to run the gate for you; they run it again before the real arm in
any case.
