# The robot

What you are programming, what it can physically do, and what is still being confirmed.

**At the Build-a-thon the robot is used as a fixed arm:** it is clamped to a table, its wheels
are switched off, and a camera on a stand looks at the table in front of it. "The base" below
only matters if the organizers enable the wheels for your team.

## At a glance

| Part | What it is |
|---|---|
| Arm | SO-101: five joints plus a gripper, six STS3215 servos |
| Camera | One USB webcam on a stand, looking at the table in front of the arm. 640x480, about 15 frames per second |
| Computer | The "arm laptop" the arm is plugged into, run by a supervisor. Your app runs there |
| Sensors | Joint angles and the camera. **No** depth camera, force sensor or touch sensor |
| Base | Round, three wheels. **Switched off for this event** |

Your app gets the robot's state 30 times a second and a new camera frame about 15 times a
second.

## Directions and units

```text
            +x  forward
             ^
             |
  +y left <--o       turning counter-clockwise (left), seen from above, is positive
```

Metres, metres per second, degrees, degrees per second. The gripper is 0 (closed) to 100 (open).

## The base (only if enabled for your team)

```python
robot.drive(vx=0.15, vy=0.0, wz=30)  # forward m/s, left m/s, counter-clockwise deg/s
```

| | Limit | In safe mode |
|---|---|---|
| Speed in any direction | 0.30 m/s | 0.15 m/s |
| Turning | 90 deg/s | 45 deg/s |
| Acceleration | 0.6 m/s per second | 0.3 |

The base is round, about 0.29 m across (the wheels sit 0.125 m from the centre). Distances
reported by the simulator and the gate are measured from the **centre** of the base.

**Safe mode** is how every app first runs on the real robot. Asking for more than the
safe-mode limit is not an error: the robot just goes at the lower speed, and `robot.limits`
shows the halved values. Only asking for more than the full limits above counts against you
in the gate. Try your app with `uv run robot sim --safe-mode` to see the difference.

- The robot ramps up and down by itself: ask for 0.3 m/s and it takes half a second to get
  there, and the same to stop. Leave room.
- You can combine all three: `drive(vx=0.1, vy=0.1, wz=20)` moves diagonally while turning.
- A drive command lasts **0.5 seconds**, then the base stops unless you send another.
- `obs.odom` is `(x, y, heading)` worked out from the wheel speeds since the robot started.
  It is good for "drive 40 cm" and "turn 90 degrees" and it **drifts**: real wheels slip. Do
  not expect it to bring you back to the same spot after a long run. The heading keeps
  counting past 360.
- **The base may be switched off.** For arm-only work the organizers disable the wheels;
  `robot.base_enabled` is then `False` and `drive()` raises `BaseDisabledError`. An app that
  only uses the arm should say `needs_base: false` in its `app.yaml`.

## The arm

Six values, by name. `robot.limits["joints_deg"]` has the limits at run time.

| Joint | Limit (degrees) | A positive angle... (in the simulator) |
|---|---|---|
| `shoulder_pan` | -100 to 100 | swings the arm to the robot's **right** (clockwise from above) |
| `shoulder_lift` | -95 to 95 | tips the upper arm forward and down |
| `elbow_flex` | -92 to 92 | folds the forearm down and back |
| `wrist_flex` | -90 to 90 | tips the gripper down |
| `wrist_roll` | -150 to 150 | rotates the gripper about its own axis |
| `gripper` | 0 to 100 | opens the jaws (0 closed, 100 open) |

> Note that `shoulder_pan` is positive to the **right**, the opposite of the base's turning
> direction. Whether each joint on the real arm matches the simulator's direction is being
> confirmed during hardware bring-up; this table will be updated if any differ.

Joints move at up to 120 degrees per second (60 in safe mode), so a big move takes a second
or two. `arm.move_to()` waits for it; `arm.set_joints()` does not.

### Named poses

```python
robot.arm.move_to("ready")
```

| Pose | pan, lift, elbow, wrist flex, wrist roll | What it looks like | Gripper tip (forward, up) |
|---|---|---|---|
| `home` | 0, -90, 90, 60, 0 | Folded over the base. The simulated arm starts here | 0.18 m, 0.11 m |
| `ready` | 0, -30, 40, 50, 0 | Raised in front, gripper angled down: a good starting point for picking | 0.26 m, 0.17 m |
| `up` | 0, 0, 0, 0, 0 | Upper arm up, forearm straight ahead | 0.39 m, 0.34 m |

Tip positions are from the centre of the base at floor level, measured in the simulator.
`robot.arm.poses` gives the same angles at run time.

For your own poses, keep a dictionary in your code:
`PICK = {"shoulder_lift": 13, "elbow_flex": 12, "wrist_flex": 49}` then
`robot.arm.move_to(PICK)`. Find the angles by moving the arm with `uv run robot teleop` and
reading them off. Do not add them to `config/robot.yaml`: the real robot uses the organizers'
copy of that file, not yours.

### Reach

The gripper tip reaches about **0.45 m forward of the base centre**, which is about 0.3 m
beyond the base's front edge, at heights from the floor up to about 0.2 m. There is no
"move the gripper to x, y, z" command: you command joint angles. To find angles for a spot,
move the arm in the simulator and read them off the dashboard.

Nothing stops the arm from hitting the base, the camera or the floor. Joint limits only keep
each joint inside its own range.

### The gripper

`gripper.open()`, `gripper.close()` and `gripper.set(40)` return immediately; the jaws take
about half a second for full travel, and a full second in safe mode. `gripper.close(wait=True)`
waits for them, and returns `False` if they stopped short of closed, which means you caught
something. You can also read `obs.gripper`: about 0 is closed on nothing, a higher value means
an object is holding the jaws apart. See `apps/05_pick_cube`.

## The camera

- `obs.image()` is a 480x640x3 `uint8` array in **BGR** order. `obs.jpeg()` is the same frame
  as JPEG bytes.
- It is fixed on a stand, looking at the table from in front of the robot, about 44 degrees
  top to bottom and 57 degrees side to side. It sees the arm, and the table between itself
  and the robot.
- It **faces** the robot, so the picture is mirrored relative to the robot: the robot's left
  is on the right of the picture. Things nearer the camera (further from the robot) are lower
  in the picture.
- In the simulator the camera is 0.80 m in front of the robot and 0.50 m above the table,
  aimed at a point 0.25 m in front of the robot. The real camera will be close to that but not
  identical, so do not rely on exact pixel positions from the simulator.
- State arrives twice as often as pictures, so `robot.observe()` often returns the same
  picture twice. `obs.image_seq` goes up by one for each new frame.
- A raised arm can hide part of the table from the camera. Fold it (`arm.move_to("home")`)
  before looking for objects.

## Safety behaviour you will see

The robot refuses or limits things on purpose. None of these are bugs.

| What you see | Why |
|---|---|
| Base stops half a second after your last drive command | Watchdog: protects against crashed or stuck apps |
| A joint stops at its limit, or the base goes slower than asked | Limits: your request was clamped. The gate fails apps that ask for too much |
| Nothing moves; the dashboard says "motion blocked" | Someone pressed STOP, or (real robot) the organizer is not holding it enabled, or your time slot has not started or has run out |
| `BaseDisabledError` | The wheels are switched off (arm-only mode) |
| Everything is half speed | Safe mode: every app's first run on the real robot |

When motion is blocked the arm holds still where it is; it does not go limp.

## Simulator versus real robot

The simulator is for getting your logic right. Expect to adjust on the real robot:

| | Simulator | Real robot |
|---|---|---|
| Colours and lighting | Clean, even | Shadows, glare, auto-exposure. **Retune colour thresholds on real frames** |
| Arm | Follows commands closely | Sags a little under load, has slack in the joints; its zero positions differ slightly, so angles that work in the simulator can be a centimetre or two off |
| Objects | Three cubes and a pad, in known places | Whatever is on the table, wherever it is |
| Camera | In a known place | Roughly the same view, not pixel-identical |
| Timing | Instant | Camera frames are tens of milliseconds old |
| Extra information | `obs.info["truth"]` has true positions | Not available |

Ask the supervisor for real camera frames during your slot to tune your vision: see
[robot-day.md](robot-day.md).

## Still being confirmed

The robot's hardware is being brought up as this is written. These may change, and the
simulator will be updated to match:

- The camera's exact position.
- The direction of each joint relative to the simulator. Comparing the real arm's folded
  pose with the simulator's suggests shoulder lift, elbow and wrist flex agree; shoulder pan,
  wrist roll and the gripper have not been checked yet.
- Where the arm sits on its base (the simulator puts it at the centre).
- The `home` pose: the real arm rests slightly more folded than the simulator's.

Confirmed so far: all nine servos respond, and the arm's real joint ranges are wider than the
limits above, so the limits are safe.
