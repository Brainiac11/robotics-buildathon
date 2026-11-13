# Offloading heavy computation

A Raspberry Pi 4 cannot run segmentation or vision-language models at useful speed (a small
YOLO model manages about 3 frames per second; SAM-class models take seconds per frame).
Classical OpenCV (colour thresholds, ArUco/AprilTag markers) runs fine on the Pi.

## What works today: tethered mode

Run the whole app on a laptop with a GPU and point it at the robot. Your model is then an
ordinary function call in your own process.

```python
from buildathon import Robot
from ultralytics import YOLO  # your choice of library; note its licence (AGPL-3.0)

model = YOLO("yolo11n-seg.pt")
with Robot.connect() as robot:  # ROBOT_HOST=<pi-address>, ROBOT_SESSION=<id from organizer>
    while True:
        obs = robot.observe()
        result = model(obs.image(), verbose=False)[0]
        ...
        robot.drive(vx=0.1)  # keep sending: commands expire after 0.5 s
```

This works unchanged against the simulator, so develop there first. On the robot an organizer
enables tethering for your slot (see the organizer runbook). If Wi-Fi drops, your commands stop
arriving and the robot's watchdog stops the base.

Keep the loop honest about latency: a frame is 30-100 ms old by the time your model has
answered, more on a busy network. Drive slowly, and prefer "turn until centred, then advance"
over fast continuous tracking.

## Not built yet: onboard app with a perception worker

The plan (`PLAN.md`) is a worker on the laptop that subscribes to the robot's camera stream,
runs the model and publishes results back through the robot host to an app running on the Pi.
Until that exists, use tethered mode for anything heavy.
