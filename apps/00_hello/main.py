"""Connect, print what the robot reports, save one camera frame. Moves nothing."""

import tempfile
from pathlib import Path

import cv2
from buildathon import Robot

with Robot.connect() as robot:
    print(f"robot: {robot.info['robot']}  mode: {robot.mode}  base enabled: {robot.base_enabled}")
    print(f"limits: {robot.limits}")
    obs = robot.observe()
    print(f"time: {obs.t:.2f}s")
    for joint, value in obs.joints.items():
        print(f"  {joint:14s} {value:7.1f}")
    print(f"base velocity: {obs.base_velocity}   odometry: {obs.odom}")
    if obs.cameras:
        image = obs.image()  # BGR, like OpenCV
        path = Path(tempfile.gettempdir()) / "hello_frame.jpg"
        cv2.imwrite(str(path), image)
        print(f"saved {path} ({image.shape[1]}x{image.shape[0]})")
