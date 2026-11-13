---
name: offload-perception
description: Use a heavy vision model (object detection, segmentation, SAM, a vision-language model) with the Build-a-thon robot by running it on a laptop or desktop instead of the robot's Raspberry Pi. Use when an app needs a neural network, a GPU, or an LLM/VLM to interpret camera images.
---

# Heavy perception: run it off the robot

The robot's computer is a Raspberry Pi 4. It runs classical OpenCV well (colour thresholds,
contours, ArUco/AprilTag markers) and neural networks badly (a nano YOLO model: about 3 frames
per second; SAM-class and vision-language models: unusable). Decide first whether the task
really needs a network.

## What exists today: tethered mode

Read `docs/offload.md`. In short: the whole app runs on the laptop that has the GPU, and
connects to the robot over the network. The model is a normal function call in the app.

1. Add the model library to the app's `requirements.txt` (and install it locally:
   `uv pip install -r teams/<team>/requirements.txt`).
2. Write the app as usual; call the model on `obs.image()` (BGR) or `obs.image(rgb=True)`.
   For an HTTP model API, send `obs.jpeg()` (already-encoded bytes).
3. Develop and gate it against the simulator exactly like any other app.
4. On the real robot it must be run tethered from the laptop
   (`ROBOT_HOST=<robot address> ROBOT_SESSION=<id>`), which an organizer enables per slot.
   Say so in the app's README: it cannot be deployed onto the Pi.

## Design rules for a slow model in the loop

- Never block the control loop on the model for long: base commands expire after 0.5 s, so the
  robot stops (safely) while the model thinks. That is acceptable for "look, think, then move"
  behaviors; for continuous tracking, run the model in a background thread and keep calling
  `robot.drive()` from the main loop with the latest result.
- Record `obs.image_seq` or `obs.t` with each result and ignore results older than about
  0.5 s when moving.
- Drive slower than you would with local vision.
- For vision-language models, send small JPEGs (`obs.jpeg()`), ask for short structured
  answers, and treat the answer as untrusted: validate numbers before turning them into motion.
- Model licences vary (Ultralytics YOLO is AGPL-3.0). Keep model code in the team directory.

## Not available yet

A perception worker that feeds results to an app running on the Pi is planned (`PLAN.md`) but
not built. Do not write code against `robot.perception`; it does not exist.
