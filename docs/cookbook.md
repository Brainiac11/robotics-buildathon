# Cookbook

Complete, working programs for common jobs. Copy one into your `main.py` and change it.

Every recipe on this page is run through the gate by the test suite (`tests/test_docs.py`), so
they work as written. The first comment line of each says which simulator scene it expects:
start that scene with `uv run robot sim --scene <name>` to try it, and put the same name in
your `app.yaml` (`scene: <name>`) so the gate uses it too.

**The arm** (what the Build-a-thon is about)

- [Move the arm through a sequence](#move-the-arm-through-a-sequence)
- [Pick something up and put it down](#pick-something-up-and-put-it-down)
- [Find the cubes in the camera picture](#find-the-cubes-in-the-camera-picture)
- [Find the right colour thresholds](#find-the-right-colour-thresholds)
- [A state machine](#a-state-machine)
- [Use a slow model without freezing the robot](#use-a-slow-model-without-freezing-the-robot)
- [Record your own data](#record-your-own-data)
- [Check yourself against ground truth](#check-yourself-against-ground-truth)

**The wheels** (off by default; only if the organizers have enabled the base for your team)

- [Work with or without the wheels](#work-with-or-without-the-wheels)
- [Drive a set distance and turn a set angle](#drive-a-set-distance-and-turn-a-set-angle)
- [Go to a point, sideways if needed](#go-to-a-point-sideways-if-needed)
- [Find a colour and turn to face it](#find-a-colour-and-turn-to-face-it)
- [Drive up to a coloured block and stop in front of it](#drive-up-to-a-coloured-block-and-stop-in-front-of-it)

## Move the arm through a sequence

`move_to` takes a named pose or joint angles, waits until the arm arrives, and tells you
whether it did.

```python
# recipe: arm-sequence | scene: table
from buildathon import Robot

STEPS = [
    "ready",
    {"shoulder_pan": 40, "elbow_flex": 60},  # joints you leave out stay where they are
    {"shoulder_pan": -40},
    "home",
]

with Robot.connect() as robot:
    robot.gripper.open()
    for step in STEPS:
        arrived = robot.arm.move_to(step, tolerance=4, timeout=6)
        joints = {name: round(angle) for name, angle in robot.observe().joints.items()}
        print(step, "->", "arrived" if arrived else "TIMED OUT", joints)
    robot.gripper.close(wait=True)  # without wait=True, gripper commands return at once
```

A `tolerance` of 3 to 5 degrees is realistic: the arm sags slightly under its own weight.

To find joint angles for a spot, drive the arm there by hand with `uv run robot teleop` and
read them off its status line.

## Pick something up and put it down

Two full examples, both short:

- [apps/06_pick_and_place](../apps/06_pick_and_place/main.py): pick the red cube off the table
  and put it on the yellow pad (scene `table`).
- [apps/05_pick_cube](../apps/05_pick_cube/main.py): lift a cube off a pedestal (scene `pick`).

The pattern that makes grasping reliable:

1. Open the gripper and move to a point **above** the object.
2. Come straight down onto it.
3. `gripper.close(wait=True)`. It returns `False` if the jaws stopped short of closed, which
   means something is between them. `True` means you missed.
4. Lift straight up before moving sideways.

Both examples use fixed joint angles, so they only work when the object is where they expect.
Finding the object with the camera is the next step.

## Find the cubes in the camera picture

The camera is fixed on a stand, looking at the table from in front of the robot. Because it
**faces** the robot, the picture is mirrored relative to the robot: the robot's left is on the
right of the picture.

Red needs **two** hue ranges, because red sits at both ends of OpenCV's 0-180 hue scale.

```python
# recipe: find-cubes | scene: table
import cv2

from buildathon import Robot

COLOURS = {  # HSV (low, high) ranges; OpenCV hue runs 0-180
    "red": [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],  # red wraps around 0
    "green": [((40, 90, 40), (88, 255, 255))],
    "blue": [((100, 120, 60), (130, 255, 255))],
}


def find(image, ranges, min_pixels=40):
    """Centre (x, y) in pixels and area of the largest patch of this colour, or None."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, *ranges[0])
    for extra in ranges[1:]:
        mask |= cv2.inRange(hsv, *extra)
    count, _, stats, centres = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return None
    biggest = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
    area = int(stats[biggest, cv2.CC_STAT_AREA])
    if area < min_pixels:
        return None
    return float(centres[biggest][0]), float(centres[biggest][1]), area


with Robot.connect() as robot:
    robot.arm.move_to("home")  # fold the arm so it does not hide the table
    image = robot.sleep(0.5).image()
    width = image.shape[1]
    for name, ranges in COLOURS.items():
        seen = find(image, ranges)
        if seen is None:
            print(f"{name}: not in view")
            continue
        x, y, area = seen
        side = "left" if x > width / 2 else "right"  # mirrored: the camera faces the robot
        print(f"{name}: pixel ({x:.0f}, {y:.0f}), {area} pixels, on the robot's {side}")
```

In the default `table` scene the 2.5 cm cubes cover about 700 pixels each. An object nearer
the camera (further from the robot) is lower in the picture.

## Find the right colour thresholds

Colours on the real camera differ from the simulator. Save a frame (`uv run robot snapshot`),
open it in any image viewer, and read off the pixel coordinates of a point on your object. Put
them in `PIXEL` below: the recipe grows a region of similar colour around that point and
prints the HSV range it covers. It also saves the frame with the region outlined, so you can
check it measured the right thing.

```python
# recipe: sample-colours | scene: table
import pathlib
import tempfile

import cv2
import numpy as np

from buildathon import Robot

PIXEL = (401, 293)  # (x, y) of a point ON the object. This is the red cube in the simulator.

with Robot.connect() as robot:
    robot.arm.move_to("home")
    image = robot.sleep(0.5).image()

height, width = image.shape[:2]
mask = np.zeros((height + 2, width + 2), np.uint8)
flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)
cv2.floodFill(image.copy(), mask, PIXEL, 0, (45, 45, 45), (45, 45, 45), flags)
region = mask[1:-1, 1:-1] > 0

pixels = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[region]
hue, sat, val = pixels[:, 0].astype(int), pixels[:, 1], pixels[:, 2]
print(f"region around {PIXEL}: {len(pixels)} pixels")
if hue.min() < 15 and hue.max() > 165:  # some of both ends of the scale: this is red
    print(f"  hue wraps around 0 (red): use TWO ranges, 0-{hue[hue < 90].max() + 5} and {hue[hue >= 90].min() - 5}-180")
else:
    print(f"  hue {max(0, hue.min() - 5)} to {min(180, hue.max() + 5)}")
print(
    f"  saturation at least {max(0, int(np.percentile(sat, 5)) - 30)}, value at least {max(0, int(np.percentile(val, 5)) - 40)}"
)

outline, _ = cv2.findContours(region.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
cv2.drawContours(image, outline, -1, (255, 255, 255), 1)
path = pathlib.Path(tempfile.gettempdir()) / "frame.jpg"
cv2.imwrite(str(path), image)
print("saved", path)
```

The ranges it prints already include a margin. Lighting changes saturation and brightness far
more than hue, so on the real robot keep the hue range tight and be generous with the other
two. For frames from the real robot without running an app, see "Collect real camera frames"
in [robot-day.md](robot-day.md).

## A state machine

The `Behavior` class calls your `step()` at a fixed rate and takes care of connecting,
stopping and cleaning up. Keep the current state in `self`.

```python
# recipe: state-machine | scene: table
from buildathon import Behavior, run

LOOK = {"left": -40, "centre": 0, "right": 40}  # shoulder_pan angles; negative is the robot's left


class Scan(Behavior):
    rate_hz = 10

    def setup(self, robot):
        robot.arm.move_to("ready")
        self.todo = ["left", "right", "centre"]
        self.state = None

    def step(self, robot, obs):
        arrived = self.state is None or abs(obs.joints["shoulder_pan"] - LOOK[self.state]) < 3
        if not arrived:
            return  # still moving: nothing to decide yet
        if not self.todo:
            return False  # finished
        self.state = self.todo.pop(0)
        print(f"{obs.t:5.1f}s  looking {self.state}")
        robot.arm.set_joints(shoulder_pan=LOOK[self.state])  # returns at once; step() checks arrival

    def teardown(self, robot):
        robot.arm.move_to("home")


if __name__ == "__main__":
    run(Scan())
```

## Use a slow model without freezing the robot

If each frame takes your model a third of a second, calling it inside the main loop makes the
whole app sluggish: nothing else happens while the model thinks. Run the model in a background
thread on the newest frame, and keep the loop running.

```python
# recipe: slow-model | scene: table
import threading
import time

from buildathon import Robot


class Latest:
    """Runs fn(image) in the background on the newest frame and keeps the latest answer."""

    def __init__(self, fn):
        self.fn = fn
        self.result, self.result_t = None, -1.0
        self._job, self._lock = None, threading.Lock()
        threading.Thread(target=self._work, daemon=True).start()

    def submit(self, image, t):
        with self._lock:
            self._job = (image, t)  # replaces any frame the model has not started on

    def _work(self):
        while True:
            with self._lock:
                job, self._job = self._job, None
            if job is None:
                time.sleep(0.005)
                continue
            answer = self.fn(job[0])
            self.result, self.result_t = answer, job[1]


def slow_model(image):
    time.sleep(0.3)  # stands in for a neural network
    return float(image[:, :, 2].mean())  # "how red is the picture"


with Robot.connect() as robot:
    robot.arm.move_to("ready")
    model = Latest(slow_model)
    start = robot.observe().t
    while True:
        obs = robot.observe()
        if obs.t - start > 5:
            break
        model.submit(obs.image(), obs.t)
        answer_is_recent = model.result is not None and obs.t - model.result_t < 1.0
        if answer_is_recent:  # act only on a recent answer, never on a stale one
            robot.arm.set_joints(shoulder_pan=15 if model.result > 120 else -15)
    robot.arm.move_to("home")
```

`time.sleep()` is fine inside the background thread; it is the main loop that must not wait
with it. Try this against the real-time simulator: the gate's simulator runs faster than real
time, so a slow model looks even slower there.

Heavy models cannot run on a small computer at all: see [offload.md](offload.md).

## Record your own data

`--trace` records the standard things. For anything else, write your own file.

```python
# recipe: log-to-csv | scene: table
import csv
import pathlib
import tempfile

from buildathon import Robot

path = pathlib.Path(tempfile.gettempdir()) / "run_log.csv"

with Robot.connect() as robot, path.open("w", newline="") as f:
    log = csv.writer(f)
    obs = robot.observe()
    log.writerow(["t", *obs.joints])
    robot.arm.pose("ready")  # start moving, without waiting
    start = obs.t
    while obs.t - start < 2:
        log.writerow([round(obs.t, 3), *(round(angle, 2) for angle in obs.joints.values())])
        obs = robot.observe()

print("wrote", path)
```

Print anything you want to keep from a run on the real robot: the supervisor's laptop shows
your app's output, and files your app writes there are not handed back automatically.

## Check yourself against ground truth

In simulation only, each observation carries the true position of every object. Use it to
measure how well you did; never use it to do the task, because it does not exist on the real
robot.

```python
# recipe: ground-truth | scene: table
from buildathon import Robot

PAD = (0.22, 0.22)  # centre of the yellow pad in the `table` scene: forward, left (metres)

with Robot.connect() as robot:
    truth = robot.observe().info.get("truth")
    if truth is None:
        print("no ground truth here: this is the real robot")
    else:
        for name, (x, y, z) in truth["objects"].items():
            on_pad = abs(x - PAD[0]) < 0.05 and abs(y - PAD[1]) < 0.05
            print(f"{name}: {x:.3f} m forward, {y:+.3f} m left, {z:.3f} m up{'  <- on the pad' if on_pad else ''}")
```

Positions are measured from the centre of the robot's base at table level. The gate records
the same information in `.simcheck/<app>.json` (`final_truth`) after your app ends, which is
how you check that a pick-and-place really put the cube where you meant.

---

# If the wheels are enabled

The Build-a-thon runs with the wheels **switched off**: the robot is clamped to a table. These
recipes are for teams whose base the organizers have enabled. Try them with
`uv run robot sim --base` (add `--camera-mount base_front` for the two camera recipes, which
expect the camera riding on the front of the base), and put `needs_base: true` in `app.yaml`.

## Work with or without the wheels

Check before driving so the same app works either way.

```python
# recipe: with-or-without-base | scene: table
from buildathon import Robot

with Robot.connect() as robot:
    if robot.base_enabled:
        robot.drive(vx=0.1)
        robot.sleep(1.0)
        robot.stop()
    else:
        print("the base is off (arm-only mode): skipping the drive")
    robot.arm.move_to("ready")
```

## Drive a set distance and turn a set angle

Uses wheel odometry and slows down near the target so it does not overshoot.

```python
# recipe: drive-and-turn | scene: empty | base: on
import math

from buildathon import Robot


def drive_forward(robot, distance_m, speed=0.15):
    obs = robot.observe()
    x0, y0, _ = obs.odom
    while True:
        remaining = distance_m - math.hypot(obs.odom[0] - x0, obs.odom[1] - y0)
        if remaining <= 0.005:
            break
        robot.drive(vx=min(speed, max(0.03, 1.5 * remaining)))  # slow down near the end
        obs = robot.observe()
    robot.stop()


def turn(robot, angle_deg, speed=45):
    """Positive turns left (counter-clockwise), negative turns right."""
    obs = robot.observe()
    target = obs.odom[2] + angle_deg
    while True:
        error = target - obs.odom[2]
        if abs(error) <= 0.5:
            break
        robot.drive(wz=math.copysign(min(speed, max(6.0, 2.0 * abs(error))), error))
        obs = robot.observe()
    robot.stop()


with Robot.connect() as robot:
    drive_forward(robot, 0.4)
    turn(robot, 90)
    turn(robot, -90)
    print("odometry now:", robot.sleep(0.5).odom)
```

## Go to a point, sideways if needed

The base can move in any direction without turning first. This drives in a straight line to a
point given in odometry coordinates (metres from where the robot started).

```python
# recipe: go-to-point | scene: empty | base: on
import math

from buildathon import Robot


def go_to(robot, x, y, speed=0.2, tolerance=0.02):
    while True:
        obs = robot.observe()
        px, py, heading = obs.odom
        dx, dy = x - px, y - py
        distance = math.hypot(dx, dy)
        if distance < tolerance:
            break
        # The error is in "room" coordinates; drive() wants "robot" coordinates.
        angle = math.radians(heading)
        forward = math.cos(angle) * dx + math.sin(angle) * dy
        left = -math.sin(angle) * dx + math.cos(angle) * dy
        v = min(speed, max(0.04, 1.2 * distance))
        robot.drive(vx=v * forward / distance, vy=v * left / distance)
    robot.stop()


with Robot.connect() as robot:
    go_to(robot, 0.3, 0.2)  # forward 30 cm and left 20 cm, in one diagonal move
    go_to(robot, 0.0, 0.0)  # and back
    print("back at:", robot.sleep(0.5).odom)
```

## Find a colour and turn to face it

With the camera on the front of the base (`camera: base_front` in `app.yaml`): look, decide,
act, repeat.

```python
# recipe: face-a-colour | scene: targets | base: on | camera: base_front
import cv2

from buildathon import Robot

BLUE = ((100, 120, 60), (130, 255, 255))  # HSV low and high. OpenCV hue runs 0-180.


def find(image, low, high, min_pixels=150):
    """(offset, size) or None. offset: -1 far left .. +1 far right. size: fraction of the image."""
    mask = cv2.inRange(cv2.cvtColor(image, cv2.COLOR_BGR2HSV), low, high)
    m = cv2.moments(mask, binaryImage=True)
    if m["m00"] < min_pixels:
        return None
    height, width = mask.shape
    return (m["m10"] / m["m00"] - width / 2) / (width / 2), m["m00"] / (width * height)


with Robot.connect() as robot:
    start = robot.observe().t
    while True:
        obs = robot.observe()
        if obs.t - start > 20:
            print("gave up: no blue in 20 seconds")
            break
        seen = find(obs.image(), *BLUE)
        if seen is None:
            robot.drive(wz=-30)  # nothing in view: turn right and keep looking
        elif abs(seen[0]) < 0.05:
            print(f"facing blue; it fills {seen[1]:.1%} of the picture")
            break
        else:
            robot.drive(wz=-40 * seen[0])  # to the right in the picture means turn right (negative)
    robot.stop()
```

## Drive up to a coloured block and stop in front of it

How close is "close"? Use where the **bottom edge** of the blob is in the picture: it moves
steadily down as you approach. Measured in the simulator with an 8 cm block straight ahead:

| Robot centre to block centre | Gap from the robot's edge to the block | Blob size (fraction of image) | Bottom edge (0 top, 1 bottom) |
|---|---|---|---|
| 0.90 m | 0.72 m | 0.02 | 0.29 |
| 0.60 m | 0.42 m | 0.05 | 0.45 |
| 0.50 m | 0.32 m | 0.08 | 0.57 |
| 0.45 m | 0.27 m | 0.11 | 0.66 |
| 0.40 m | 0.22 m | 0.17 | 0.79 |
| 0.35 m | 0.17 m | 0.28 | 0.98 |

Closer than about 0.35 m the block starts to leave the picture: the bottom edge is stuck at
1.0 and the size goes *down* again, so a size threshold set too high never triggers.

```python
# recipe: approach-a-colour | scene: targets | base: on | camera: base_front
import cv2

from buildathon import Robot

COLOURS = {  # HSV (low, high) ranges; OpenCV hue runs 0-180
    "red": [((0, 120, 70), (10, 255, 255)), ((170, 120, 70), (180, 255, 255))],  # red wraps around 0
    "green": [((40, 90, 40), (88, 255, 255))],
    "blue": [((100, 120, 60), (130, 255, 255))],
}
TARGET = "green"
STOP_WHEN_BOTTOM_EDGE_AT = 0.79  # about 0.40 m centre to centre: see the table above


def find(image, ranges, min_pixels=150):
    """(offset, size, bottom) or None. offset -1 left..+1 right; bottom 0 top..1 bottom of the image."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, *ranges[0])
    for extra in ranges[1:]:
        mask |= cv2.inRange(hsv, *extra)
    ys, xs = mask.nonzero()
    if len(xs) < min_pixels:
        return None
    height, width = mask.shape
    return (xs.mean() - width / 2) / (width / 2), len(xs) / (width * height), ys.max() / height


with Robot.connect() as robot:
    robot.arm.move_to("home")  # keep the arm out of the camera's way
    start = robot.observe().t
    while True:
        obs = robot.observe()
        if obs.t - start > 40:
            print(f"gave up: no {TARGET} block reached in 40 seconds")
            break
        seen = find(obs.image(), COLOURS[TARGET])
        if seen is None:
            robot.drive(wz=30)  # search: turn left on the spot
            continue
        offset, size, bottom = seen
        if bottom >= STOP_WHEN_BOTTOM_EDGE_AT and abs(offset) < 0.15:
            print(f"stopped in front of the {TARGET} block (size {size:.2f}, bottom edge {bottom:.2f})")
            break
        forward = 0.12 if abs(offset) < 0.4 else 0.0  # only advance when roughly facing it
        robot.drive(vx=forward, wz=-50 * offset)
    robot.stop()
```
