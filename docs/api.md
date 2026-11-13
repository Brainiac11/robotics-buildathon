# SDK reference

New here? Start with [getting-started.md](getting-started.md). For working programs see
[cookbook.md](cookbook.md); for joint directions, reach and limits see [robot.md](robot.md).

`from buildathon import Robot, Behavior, run, BaseDisabledError, RobotError, RobotTimeout`

Units: metres, m/s, degrees, deg/s, gripper 0-100. Frame: +x forward, +y left, +theta
counter-clockwise seen from above.

## Connecting

```python
with Robot.connect() as robot:  # stops the base and disconnects on exit, error or Ctrl-C
    ...
```

`Robot.connect(host=None, *, session=None, timeout=5.0, handle_signals=True)`

- `host` defaults to the `ROBOT_HOST` environment variable, then `localhost`. Write
  `name:port` if the simulator was started with `--port`.
- `session` is only needed on the real robot when your app runs on your own laptop
  (tethered): the organizer gives you a session id for your slot, and commands without it are
  ignored. It defaults to the `ROBOT_SESSION` environment variable. Leave it alone otherwise.

| Property | Meaning |
|---|---|
| `robot.mode` | `"sim"`, `"real"` or `"mock"` |
| `robot.base_enabled` | `False` in arm-only mode |
| `robot.limits` | Dict of the speed and joint limits in force now (halved speeds in safe mode) |
| `robot.info` | Everything the host reported on connect (camera size, rate, named poses) |
| `robot.lockstep` | `True` in the gate, where simulated time only advances when your app calls the SDK ("lockstep") |

## Observing

`obs = robot.observe()` returns the next observation, newer than the last one you got
(about 30 per second). In lockstep it advances the simulation one step.

| Field | Meaning |
|---|---|
| `obs.t` | Robot time in seconds (simulated time in the sim) |
| `obs.joints` | `{"shoulder_pan": deg, ..., "gripper": 0-100}` |
| `obs.gripper` | Gripper opening, 0-100 |
| `obs.base_velocity` | Measured `(vx, vy, wz)` |
| `obs.odom` | `(x, y, heading_deg)` integrated from wheel speeds. Drifts; heading is not wrapped |
| `obs.image(name=None, rgb=False)` | Camera frame, HxWx3 `uint8`. **BGR** unless `rgb=True` |
| `obs.jpeg()` | The same frame as JPEG bytes (useful to send to a model server) |
| `obs.cameras` | List of camera names in this observation (empty if the robot has no camera) |
| `obs.image_seq` | Increases when the camera delivers a new frame (camera is slower than state) |
| `obs.base_enabled`, `obs.estop`, `obs.motion_enabled` | Robot status flags |
| `obs.state` | Raw values by LeKiwi key (`arm_shoulder_pan.pos`, `x.vel`, ...) |
| `obs.info` | Full header: `inhibit` reasons, `events` counters, and `truth` (sim ground truth) |

`obs.image()` raises `RobotError` if the robot has no camera frame (check `obs.cameras`).
In simulation `obs.info["truth"]` holds ground truth: `x`, `y` (metres), `theta` (degrees, not
wrapped to 360) and `objects` (name to `[x, y, z]` of its centre). It does not exist on the
real robot: use it to check results, never inside a behavior.

State arrives about 30 times a second but the camera only about 15, so two observations in a
row often carry the **same picture**. Compare `obs.image_seq` if you only want to process new
frames.

`robot.sleep(seconds)` waits in robot time and returns the latest observation. Use it instead
of `time.sleep()`: it works in lockstep and keeps a drive command alive.

## Driving the base

```python
robot.drive(vx=0.15, vy=0.0, wz=30)  # set velocity
robot.sleep(1.5)
robot.stop()
```

A drive command lasts 0.5 s unless refreshed. `robot.sleep()`, `arm.move_to()` and the
`Behavior` runner refresh it; a bare loop of `robot.observe()` does not, so call `drive()`
every iteration in control loops. If the base is off, `drive()` raises `BaseDisabledError`.

## Arm and gripper

```python
robot.arm.set_joints(shoulder_pan=20, elbow_flex=45)  # returns immediately
robot.arm.move_to("ready")  # a named pose; waits; returns True/False
robot.arm.move_to({"shoulder_lift": -30, "elbow_flex": 40})  # a dict of joint angles
robot.arm.move_to(shoulder_lift=-30, tolerance=3, timeout=8)  # or keyword arguments
robot.arm.pose("home")  # a named pose, without waiting
robot.arm.poses  # dict of the named poses and their angles
robot.gripper.open()  # returns immediately; also close() and set(40)
robot.gripper.close(wait=True)  # waits; True if fully closed, False if it stopped short
```

`arm.move_to(target=None, tolerance=3.0, timeout=8.0, **joints) -> bool`: `target` is a pose
name or a dict of joint angles. It returns `True` once every commanded joint is within
`tolerance` degrees, or `False` after `timeout` seconds of robot time (also when motion is
blocked). `arm.set_joints()` takes the same dict or keywords and does not wait.

`gripper.set(percent, wait=False, timeout=3.0) -> bool`, and `open(wait=False)` /
`close(wait=False)`. With `wait=True` it returns when the jaws arrive (`True`) or stop moving
short of the target (`False`): after `close(wait=True)`, `False` means something is between
the jaws. Without `wait=True` the call returns at once; full travel takes about half a
second, and a full second in safe mode, so prefer `wait=True` to a fixed sleep. A closed
empty gripper reads about 0; one holding an object stays partly open.

Joints you do not mention keep their target. The host moves joints at a limited speed
(`robot.limits["max_joint_speed_deg_s"]`), so a far target takes time. There is no Cartesian
(x, y, z) control yet.

## Raw actions

`robot.send_action({"arm_elbow_flex.pos": 30, "x.vel": 0.1})` sends LeKiwi-keyed targets
directly. Unknown keys raise `ValueError`.

## Behavior

```python
from buildathon import Behavior, run


class Mine(Behavior):
    rate_hz = 10

    def setup(self, robot): ...
    def step(self, robot, obs): ...  # return False to finish
    def teardown(self, robot): ...  # always called


run(Mine())  # or run(Mine(), duration=30)
```

`duration` is in seconds of robot time; without it the behavior runs until `step()` returns
`False`. `rate_hz` is how often `step()` is called (also in robot time).

## Stopping and signals

`Robot.connect()` turns SIGTERM (what `robot run --duration`, the gate and `docker stop` send)
into a normal `SystemExit`, so `with Robot.connect()` and `run()` stop the base on the way
out. Do not catch `SystemExit` or `BaseException` in a loop. Pass `handle_signals=False` if
your program installs its own handler.

In lockstep (the gate), commands are applied at the next `observe()`/`sleep()`, because that
is when simulated time advances.

## Other

- `robot.stop()` stops the base; the arm holds.
- `robot.estop()` latches the emergency stop (an organizer clears it).
- `robot.snapshot()` returns the host's latest observation without stepping the sim.
- `robot.status()` returns `{"status": <the latest observation header>, "stats": {"commands": n, "rejected": n, "overruns": n, ...}}`.

## When the robot will not move

If motion is blocked (someone pressed STOP, or on the real robot the organizer is not holding
it enabled or your session has ended), your commands are ignored. The SDK prints one line to
say so:

```text
[buildathon] the robot is not moving: motion is blocked (estop). Commands are ignored until that is cleared.
```

Your app keeps running: `arm.move_to()` returns `False`, the base stays still.
`obs.motion_enabled` is `False` and `obs.info["inhibit"]` lists the reasons, if you want to
wait or exit cleanly.

## Errors

| Error | Meaning |
|---|---|
| `RobotTimeout` | No host answered. Start `robot sim`, or check `ROBOT_HOST` |
| `BaseDisabledError` | Drive command in arm-only mode |
| `RobotError` | The host refused a request (message says why), or protocol version mismatch |
