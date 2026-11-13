# Hardware bring-up

First power-on of the robot, in the order that finds problems earliest. Nothing here has been
run on the real robot yet: expect to fix small things, and note what you change.

**Keep a hand on the servo power switch whenever the robot is powered.** It is the only stop
that works whatever the software is doing.

Commands marked **[Pi]** run on the Raspberry Pi over SSH, from `/opt/buildathon/repo`.
`TOOLS` below is short for:

```bash
docker compose -f docker/compose.robot.yaml run --rm tools
```

## Confirmed so far on this robot (2026-11-13, read-only, servo board on a laptop's USB)

- Servo board: QinHeng `1a86:55d3`, serial `5AE6083718`; appears as `/dev/ttyACM0`. The udev
  rule in `scripts/pi/99-buildathon.rules` matches it.
- All nine servos answer at 1 Mbaud: STS3215 (model 777), firmware 3.10, IDs 1-9.
  **Step 3 is done.**
- Supply reads about 11.4 V: these are the 12 V servos.
- Wheels (7, 8, 9) are already in velocity mode; the arm joints carry limits and homing
  offsets. The robot has been calibrated with LeRobot before. That calibration was read back
  from the motors into `config/calibration/buildathon.json` and matches them, so
  **step 5 can be skipped** unless the joint angles turn out to be wrong in the mirror.
- Calibrated joint ranges: pan ±120°, lift ±113°, elbow ±102°, wrist flex ±104°, wrist roll
  a full turn. The limits in `robot.yaml` are inside these.
- A full state read takes 1.5 ms; the 30 Hz loop has ample margin on a laptop.
- `tools doctor` passes for the bus and all motors.
- The pre-flight check (`--preflight-only`) runs on the real bus and refuses to start while
  the wrist roll is near its wrap point.
- Folded by hand, the arm reads about pan 5, lift -108, elbow 105, wrist flex 82. The
  simulator drawn at those angles shows a folded arm, so the joint directions of shoulder
  lift, elbow and wrist flex agree between the real arm and the simulator. That rest pose is
  outside the limits in `robot.yaml` (lift ±95, elbow ±92, wrist flex ±90), so the arm will
  hold it at start and move inside the limits when first commanded.
- Not yet checked: any motion, wheel directions, the camera (none was connected), the Pi.

**Before enabling torque for the first time:** the wrist roll read 176°, right next to the
point where its encoder wraps from +180° to -180°. Turn it by hand to roughly the middle (near
0° in the mirror) first, or it may spin almost a full turn to get back to where it "was".

## 0a. Mirror: compare the real arm with the simulator, without powering a motor

With servo power on but torque off (the state the robot is in after power-up):

```bash
./scripts/mirror.sh /dev/ttyACM0        # or no argument on the Pi; open http://localhost:8090
```

The simulated arm copies the real arm's joint readings. Nothing is commanded.

- [ ] Move each joint by hand, one at a time. The same joint must move the same way in the
      simulator view. Note any joint that moves the opposite way or by a different amount.
- [ ] Fold the arm into the pose you want it to rest in. Write the six numbers from the
      State panel into `arm.named_poses_deg.home` in `config/robot.yaml`.
- [ ] Open and close the gripper by hand: fully closed should read about 0, fully open about 100.
- [ ] Put the robot on the floor and push it straight forward: `x.vel` must be positive.
      Push it to its left: `y.vel` positive. Turn it counter-clockwise (seen from above):
      `theta.vel` positive. A wrong sign or a mixed-up axis means the wheel positions,
      `wheel_direction` or roller angle in `robot.yaml` are wrong. This check needs no motor.
- [ ] Note where the arm sits on the base (centre or front edge) and where the simulated arm
      passes through the simulated base: the sim mounts the arm at the centre.

## 0b. First motion from a laptop: teleop

With the servo board on a laptop's USB (no Pi needed), the first powered test is keyboard
teleoperation. [teleop.md](teleop.md) has the procedure and the "first time on this robot"
checklist:

```bash
./scripts/start-robot-host.sh          # pre-flight, confirmation, then torque on (safe mode)
uv run robot teleop                    # second terminal
```

The wheels are locked off unless you add `--base` (do that only with every wheel off the
ground the first time). This covers what steps 6 to 8 below do with the Pi; the failure drills
in step 9 still apply. For the Build-a-thon weekend the arm laptop runs everything:
[organizer-runbook.md](organizer-runbook.md).

## 0. Before powering anything

- [ ] **Wheel type.** Look at the rollers. Rollers at 90° to the wheel = omni wheel
      (`roller_angle_deg: 0`). Rollers at 45° = mecanum (`45` or `-45`). Photograph one wheel.
- [ ] **Wheel layout.** Measure where each wheel sits around the base, in degrees
      counter-clockwise from straight ahead, and which servo is which. Expected: left-front
      60°, back 180°, right-front -60°.
- [ ] **Sizes.** Wheel radius, and distance from the base centre to each wheel's contact point.
- [ ] **Power.** Servo supply voltage matches the servos (7.4 V servos: 5-7.4 V; 12 V servos:
      12 V). The Pi has its own 5 V / 3 A or better supply (a buck converter rated 5 A is
      safer). Servos are fed from the battery, never through the Pi.
- [ ] **A physical switch on the servo power line**, reachable while the robot moves.
- [ ] **Camera** position chosen (`base_front` or `wrist`) and fixed firmly.
- [ ] Put all of this into `config/robot.yaml` (the entries marked `MEASURE`) and commit.

## 1. The Pi

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager; set hostname, user,
   Wi-Fi and enable SSH in its settings.
2. **[Pi]** `git clone <repo> ~/buildathon && cd ~/buildathon && sudo ./scripts/pi/bootstrap.sh`
   Note the organizer token it prints. Log out and in again.
3. **[Pi]** `vcgencmd get_throttled` must print `throttled=0x0`. Anything else means the Pi's
   power supply is too weak; fix that before continuing.

## 2. Software smoke test (no motors needed)

This is the main unknown: LeRobot officially targets the Pi 5, not the Pi 4.

1. **[Pi]** `docker compose -f docker/compose.robot.yaml build host` (slow the first time).
2. **[Pi]** `TOOLS doctor --skip-motors`
3. **[Pi]** Check LeRobot imports:
   `docker compose -f docker/compose.robot.yaml run --rm --entrypoint python tools -c "import lerobot, torch; print(lerobot.__version__)"`

If step 3 dies with **"Illegal instruction"**, a dependency was built for a newer ARM CPU.
Find which (`python -X faulthandler -c "import lerobot"`), pin an older version of it in
`docker/Dockerfile.host-real`, rebuild. If it cannot be fixed, the fallback in `PLAN.md` is a
host backend that talks to the servos with `rustypot` directly.

## 3. Servo IDs (skip if already done)

New servos all ship as ID 1 and must be given their ID **one at a time**, with only that servo
connected to the board. Order: gripper (6) down to shoulder pan (1), then wheels 9, 8, 7.

**[Pi]** `TOOLS setup-motors` and follow LeRobot's prompts.

If the robot is already assembled and IDs were never set, the servo cables have to be
unplugged to do this. Arm IDs: shoulder_pan 1, shoulder_lift 2, elbow_flex 3, wrist_flex 4,
wrist_roll 5, gripper 6. Wheels: left 7, back 8, right 9.

No wheels yet? Set `base.present: false` in `config/robot.yaml`; everything below then works
for the arm alone.

## 4. Doctor

**[Pi]** `TOOLS doctor`

Every motor must answer, with a sensible voltage. Fix every FAIL before going on. Put the
camera path it prints into `camera.device` in `config/robot.yaml`. Run
`TOOLS doctor --fix-camera` if the frame rate is low.

## 5. Calibrate

**[Pi]** `TOOLS calibrate` and follow LeRobot's prompts (move each joint through its range).

Then copy the calibration into the repo so a re-flashed SD card can restore it:
`cp /opt/buildathon/calibration/*.json config/calibration/` and commit.

## 6. First motion with stock LeRobot (wheels OFF the ground)

Prove the hardware with LeRobot's own, unmodified software before using ours.

1. Put the robot on a stand so no wheel touches anything. Fold the arm into its rest pose.
2. **[Pi]** `TOOLS stock-host`
3. On a laptop with LeRobot installed, drive it with LeRobot's
   `examples/lekiwi/teleoperate.py` (set `remote_ip`), or send a few actions from a Python
   shell with `LeKiwiClient`.
4. Check each arm joint moves the way the same command moves the simulated arm
   (`robot sim`, then `robot.arm.set_joints(...)`). Note any joint with the opposite sign.

If stock LeRobot cannot move the robot, the problem is hardware or LeRobot setup, not this repo.

## 7. Wheel test (wheels OFF the ground)

**[Pi]** `TOOLS wheel-test`

It spins each wheel alone, then commands forward, left and turn. Apply the
`wheel_direction` changes it suggests to `config/robot.yaml`. If "forward" does not look like
forward, the wheel positions or roller angle in `robot.yaml` are wrong: fix them, then run
`uv run pytest tests/test_kinematics.py` on a laptop and try again.

## 8. Our host, on the stand

1. Arm folded in its rest pose (starting the host briefly releases torque).
2. **[Pi]** `docker compose -f docker/compose.robot.yaml up host` (foreground, to see the log).
3. Laptop: open `http://<pi-address>:8080`. Camera and joint angles should be live.
4. Laptop: `robot enable --host <pi-address>` (needs `BUILDATHON_ORGANIZER_TOKEN`), and in
   another terminal `robot session start --host <pi-address>`.
5. **[Pi]** start the tether (`docker compose -f docker/compose.robot.yaml --profile tether up -d tether`),
   then from the laptop run `ROBOT_HOST=<pi-address> ROBOT_SESSION=<id> robot run apps/03_arm_wave`.

## 9. Failure drills (still on the stand, wheels spinning)

With `apps/01_keyboard_teleop` holding the wheels turning, do each of these. **The wheels must
stop every time.** Do not put the robot on the floor until they do.

- [ ] Kill the app (Ctrl-C).
- [ ] Stop `robot enable` (Ctrl-C).
- [ ] Press STOP on the dashboard.
- [ ] Switch the Wi-Fi router off.
- [ ] **[Pi]** `docker kill buildathon-host-1`.
- [ ] Flip the servo power switch.

## 10. On the floor

1. Safe mode on (`robot safe-mode on`), clear space, someone at the power switch.
2. `apps/01_keyboard_teleop`: forward, back, sideways, turn.
3. `robot deploy apps/02_drive_square`. Measure how far off the square is; correct
   `wheel_radius_m` (distance error) and `base_radius_m` (turn error) in `robot.yaml`.
4. Start the host on boot: **[Pi]** `sudo systemctl start buildathon-host`.

## Write down

Battery run time, the Pi's temperature after 20 minutes (`TOOLS doctor`), camera frame rate,
and anything you had to change. These go into `docs/troubleshooting.md`.
