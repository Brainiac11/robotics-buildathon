# Build-a-thon repo for the SO-101 vehicle — implementation plan

## Status (updated 2026-11-13, after a verification pass)

**Event setup** (2026-11-13, from the organizers' ops playbook): the robot is used as an arm
clamped to a table. Arm-only is now the default everywhere (wheels on request via `--base`),
the default camera is a fixed one facing the robot (`workspace` mount), the default scene is
`table`, and the real arm is run from the laptop it is plugged into: `scripts/start-robot-host.sh`
then `robot slot <team>` (gate, safe-mode first run, hold-enabled, log) or `robot teleop`.
The Raspberry Pi path below is for after the event.

**Participant documentation** (2026-11-13): `docs/getting-started.md`, `docs/robot.md`,
`docs/cookbook.md` (ten recipes, each run through the gate by `tests/test_docs.py`),
`docs/robot-day.md`, `docs/using-ai-agents.md`, `docs/event-info.md` (a template the
organizers must fill in), `docs/README.md` (index), `apps/README.md`, `teams/README.md`.
Doc links, SDK names and CLI commands in the docs are checked against the code.

**Real robot, read-only checks done** (2026-11-13): see the top of `docs/hardware-bringup.md`.

**Teleoperation** (2026-11-13): `robot teleop` (keyboard; base hold-to-move, per-joint arm
jog), `scripts/start-robot-host.sh` (real host on a laptop, with a read-only pre-flight before
torque) and `docs/teleop.md`. Tested in simulation and rehearsal mode; the pre-flight and
launcher were run against the real bus up to the torque prompt. The powered path has not been
run yet.

**Built and verified in simulation** (85 tests pass; every example passes the gate; Docker
flow run end to end with CPU-only rendering):
SDK, host with sim and mock backends, safety layer (limits, watchdog, e-stop, heartbeat,
session, run-time cap, safe mode), base on/off (arm-only mode), browser dashboard, `robot`
CLI (`sim`, `stop-sim`, `run`, `--trace`, `sim-check`, `snapshot`, `status`, organizer
commands), `robot sim --rehearse` (the real robot's enable/session rules in simulation), six
example apps and a template, three scenes, Docker images and compose for the simulator and
apps, `AGENTS.md`/`CLAUDE.md`, docs, six agent skills.

**How it was verified:** clean-copy install; mutation testing of the safety code (14 deliberate
breaks, all caught); ten deliberately faulty apps through the gate; real-time checks (app
killed mid-drive, e-stop, base switched off while driving, malformed network input, port
conflicts, 90 s stability run); dashboard rendered in headless Chrome; Docker with an app that
installs its own requirements; a fresh AI agent given only the repo built a working app.
Bugs found and fixed in that pass: a malformed command could crash the host; the gate's
port selection raced with client sockets (about 1 start in 15 failed); the gate recorded the
final state mid-motion; `robot sim` did not die with its parent shell; scene `size_m` was a
half-size.

**Written, checked only as far as possible without hardware:** real backend
(`backends/real_lekiwi.py`: builds against a real LeRobot 0.7.0 install and its wheel commands
match stock LeKiwi exactly; never connected to servos), Pi tools (`doctor`, `wheel-test`,
`stop-wheels`, setup/calibrate wrappers), `docker/Dockerfile.host-real` (built for x86 only),
`docker/compose.robot.yaml` (syntax validated only), `scripts/pi/bootstrap.sh`, `robot deploy`.

**Not verified at all:** anything on macOS or Windows; an ARM build of the Pi image; the Pi 4
itself.

**Not started:** Phase 0 itself (needs the robot: follow `docs/hardware-bringup.md`),
perception offload worker and relay bus, replay backend, LeRobot `LeKiwiClient` compatibility
ports, CI, laptop preflight script, skill evaluation with `skill-creator`.

**Changed from the plan below:** the organizer deploy tool is `robot deploy` in the CLI rather
than `scripts/station/deploy.py`; skills number six (four participant, two organizer).

## Context

The Build-a-thon needs one repo that lets participants control an SO-101 arm on a circular
3-wheel base in an approachable, extensible way. Their code must run in Docker on a Raspberry
Pi 4 mounted on the robot, must pass in simulation before it touches the real robot, and may
offload heavy perception to a laptop/desktop. The repo must ship agent docs and skills so
participants' AI agents can work in it. The hardware is untested, so bring-up, configuration
and deployment tooling are part of the deliverable.

The working directory was empty: this is a greenfield repo.

**Confirmed with the user:** wheel servos are Feetech, on the same bus as the arm; plain
Python API (no ROS 2); one shared robot; one Microsoft LifeCam, mount position not fixed.

## What research established (verified 2026-11-12)

- **The robot is effectively LeRobot's LeKiwi.** `lerobot` v0.7.0 (`src/lerobot/robots/lekiwi/`)
  already drives 9 STS3215 servos on one bus: arm IDs 1–6 in position mode, wheels 7/8/9 in
  velocity mode, with kiwi-drive kinematics (`LeKiwi._body_to_wheel_raw` /
  `_wheel_raw_to_body`), setup (`lerobot-setup-motors --robot.type=lekiwi`), calibration
  (`lerobot-calibrate --robot.type=lekiwi`) and a Pi-side server (`lekiwi_host`). We reuse it.
- **LeKiwi wire protocol:** ZMQ; commands as one JSON dict to a PULL socket on 5555;
  observations as multipart (JSON header + raw JPEG per camera) from a PUSH socket on 5556.
  Keys: `arm_shoulder_pan.pos` … `arm_gripper.pos` (degrees, gripper 0–100), `x.vel`, `y.vel`
  (m/s), `theta.vel` (deg/s). PUSH/PULL serves exactly one client correctly.
- **LeRobot needs Python ≥ 3.12 and always installs PyTorch.** On a Pi the default torch wheel
  pulls CUDA packages (484 MB); the CPU wheel is 171 MB from `download.pytorch.org/whl/cpu`.
  The Pi 4 is not LeRobot's reference platform (the Pi 5 is): there is a reported
  "Illegal instruction" on import from pyarrow 21 (fixed upstream in 22, not re-tested).
- **LeRobot's remote policy server excludes LeKiwi-type robots.** Offloading goes through the
  host/client split instead.
- **No ready-made simulator fits.** Nothing maintained offers SO-101 + 3-wheel base, CPU-only,
  in Docker, with the real interface. LeIsaac and ManiSkill need a GPU. Usable parts: MuJoCo
  Menagerie's official SO-101 model (`robotstudio_so101/`, Apache-2.0) and LeRobot's own
  `lerobot/so101-tabletop-mujoco` environment (same model, LeRobot units, headless cameras).
- **A Pi 4 cannot run segmentation.** YOLOv8n is about 3 FPS on a Pi 4; SAM-family models take
  seconds per image even on a Pi 5. Offloading is required for those.
- **Agent conventions:** `AGENTS.md` is the cross-tool standard; Claude Code reads it only if
  no `CLAUDE.md` exists, so `CLAUDE.md` must import it. Skills use the open `SKILL.md` format;
  `.agents/skills/` covers Codex/Cursor/Gemini/Copilot, Claude Code reads `.claude/skills/`.

## Decisions that differ from the brief (to approve)

1. **The sim is assembled, not adopted.** No preconfigured sim exists for this robot. The plan
   builds one from the official SO-101 MuJoCo model plus a simple base generated from the
   robot's measured geometry, behind the real robot's network interface.
2. **An organizer station deploys to the robot; participants submit.** With one shared robot,
   giving every team SSH to the Pi is root access to the event's single point of failure.
   Participants run everything themselves in sim, then push their team directory; the station
   re-runs the gate and deploys in their time slot. The deploy script is the same one, so
   self-serve deploy can be switched on by handing out the key.
3. **The real robot moves only while an organizer heartbeat is present.** If Wi-Fi drops or
   the organizer releases the deadman, the robot stops, even though the app runs onboard.
   This is a config flag, on by default.

## Architecture

One contract, interchangeable backends. Participant code never touches hardware directly.

```
 laptop (tethered)  or  Pi (onboard)          robot-host: one program, backends real | sim | mock
 ┌──────────────────────────┐  commands      ┌─────────────────────────────────────────────┐
 │ app container             │──────────────▶│ native sockets: SUB observations, commands   │
 │ buildathon SDK            │◀──────────────│   with session id, relay bus for perception  │
 └──────────────────────────┘  observations  │ safety: per-second limits, watchdog, e-stop, │
 ┌──────────────────────────┐                │   operator heartbeat, run-time cap           │
 │ perception worker (laptop │  dials host   │ dashboard :8080 (camera, state, stop)        │
 │ GPU): detect/segment/VLM  │◀─────────────▶│ LeKiwi-compatible ports 5555/5556 (shim)     │
 └──────────────────────────┘                └─────────────────────────────────────────────┘
```

- **Sim vs real is one environment variable:** `ROBOT_HOST=sim` or the Pi's address.
- **The app runs on the Pi (onboard) or on a laptop (tethered)** with the same code.
- **Every laptop connection dials out to the host.** Nothing needs inbound access to a
  participant laptop, which firewalls, WSL2 and changing addresses would block.
- **Safety lives in the host, which organizers own,** and behaves identically in sim.

### Key design decisions

1. **Bring up hardware with stock LeRobot first; then own the host loop.** Stock
   `lekiwi_host` exits after a fixed time, stops only the base on timeout, has no limits and
   serves one client. Our host calls LeRobot's `LeKiwi` class for all motor I/O and adds the
   rest. Stock `lekiwi_host` stays documented as the event-day fallback.
2. **Native protocol for our tools, LeKiwi shim for LeRobot's.** The SDK, dashboard and
   perception worker use PUB/SUB observations and commands that carry a session id, so many
   viewers and one controller coexist. Ports 5555/5556 speak LeRobot's exact protocol for one
   client (on in sim; organizer-enabled on the robot) so stock LeRobot teleoperation, dataset
   recording and policies work. LeKiwi key names are used everywhere.
3. **One controller at a time, by session.** The host accepts commands only from the active
   session id. The onboard app gets it from the deploy script; a tethered laptop gets it from
   the organizer for its slot. On the robot the command port is on the Docker network unless
   tethering is enabled.
4. **The SDK does not depend on LeRobot** (pyzmq + numpy + opencv only). App images stay
   small and avoid the Pi 4 torch/pyarrow risks. Only the real backend imports LeRobot.
5. **Robot geometry is config, not code.** `KiwiBase(LeKiwi)` overrides the two kinematics
   methods to read wheel angles, wheel radius, base radius and roller type from
   `config/robot.yaml`. The sim base is generated from the same file.
6. **The base can be switched off (arm-only mode).** `robot.yaml` has `base.enabled`
   (drive allowed) and `base.present` (wheel servos are on the bus at all). Overrides, most
   specific wins: a team's `app.yaml` (`needs_base: false`), `robot sim --no-base`, the
   station deploy `--no-base` flag, and an organizer-only toggle on the running host. When
   disabled, the host zeroes every base velocity regardless of what the app sends, holds the
   wheels locked (or free, by config), and reports `base_enabled: false`; the SDK's `drive()`
   raises a clear `BaseDisabledError`. The sim honours the same flag, so an arm-only app is
   gated arm-only. With `base.present: false` the real backend uses LeRobot's plain SO-101
   driver, which also lets the arm be brought up before the wheels are wired.
6a. **One camera, named mount.** `robot.yaml` declares device, format and mount (`base_front`
   or `wrist`, with pose). The sim renders from the same mount.
7. **Sim time is explicit.** Every observation carries sim time and a sequence number; the
   SDK's loop runner paces on it. `sim-check` runs in lockstep (deterministic); interactive
   sim runs in real time and reports its real-time factor.
8. **Browser dashboard and headless traces instead of a GUI viewer.** Works from Docker on
   Linux, macOS and Windows with only a port mapping. `robot run --duration N --trace DIR`
   writes state JSON and PNG frames so coding agents get feedback without a browser.

## Repository layout

```
AGENTS.md  CLAUDE.md(@AGENTS.md)  README.md  LICENSE(Apache-2.0)  pyproject.toml(uv workspace)
config/     robot.yaml  limits.yaml  scenes/*.yaml  calibration/  .env.example
packages/
  sdk/         buildathon/  robot.py  types.py  perception.py  behavior.py
  host/        buildathon_host/  server.py  protocol.py  lekiwi_shim.py  safety.py  dashboard/
               backends/{base.py, real_lekiwi.py, mujoco_sim.py, mock.py, replay.py}
  perception/  buildathon_perception/  worker.py  models/
  cli/         robot  (cross-platform Python; no make or rsync needed by participants)
sim/assets/    so101/ (Menagerie)  base.xml.j2 (generated from robot.yaml)  scenes/
apps/          00_hello  01_keyboard_teleop  02_drive_square  03_follow_color
               05_offload_segment  _template/
teams/         <team-name>/  (participant code and requirements.txt)
docker/        Dockerfile.{host-real,host-sim,app,perception}
               compose.sim.yaml  compose.robot.yaml  compose.perception.yaml
scripts/pi/    bootstrap.sh  99-buildathon.rules  buildathon-host.service
scripts/station/  deploy.py  (organizer station: gate, copy, run, slot/session)
docs/          architecture.md  api.md  sim.md  hardware-bringup.md  offload.md
               safety.md  troubleshooting.md  organizer-runbook.md
.agents/skills/ (canonical)   .claude/skills/ (synced copy)   scripts/sync-skills.py
tests/         protocol, safety, kinematics, sim smoke
```

## Components

### SDK (`packages/sdk`)
- `Robot.connect()` reads `ROBOT_HOST`. `observe()` returns joints (deg), base velocity,
  odometry, named images (JPEG bytes kept, decoded lazily), sim/robot time and sequence.
- `drive(vx, vy, wz)`, `arm.set_joints(...)`, named poses (`arm.pose("home")`),
  `gripper.open()/close()`, `stop()`, raw `send_action(dict)` in LeKiwi keys. Cartesian
  inverse kinematics is deferred.
- `Behavior` base class (`setup` / `step(obs)` / `teardown`) with a fixed-rate runner as the
  extension point; `apps/_template` scaffolds one.
- `robot.perception.latest("segment")` and `.ask(prompt)` read results relayed by the host,
  tagged with the frame sequence number so stale results are discarded.
- Units and frames follow LeRobot (m/s, deg/s, degrees, gripper 0–100; +x forward, +y left).

### Host (`packages/host`)
- Safety layer, enforced per second on the host tick (not per message): base speed and
  acceleration caps, joint limits, arm joint-speed cap, command staleness watchdog (base
  stops, arm holds), e-stop latch, operator heartbeat, per-deploy run-time cap, low servo
  voltage stop, a "safe mode" profile with reduced limits, and a "home and park" action.
- Process-failure cover: systemd `WatchdogSec` on the host and an `ExecStopPost` that zeroes
  the wheel servos, because wheels in velocity mode keep their last speed if the host hangs.
- Backends: `real_lekiwi` (LeRobot `LeKiwi` + `OpenCVCamera`, `fourcc="MJPG"`), `mujoco_sim`,
  `mock`, and `replay` (plays back frames and state recorded from the real robot, so teams
  can tune vision on real LifeCam images without the robot).
- Protocol version in every observation header; wheel odometry integrated in the host.

### Simulation (`mujoco_sim` backend, `docker/compose.sim.yaml`)
- MuJoCo pinned to 3.3.7 (4.0 came out six days ago; LeRobot's SO-101 environment pins 3.3.7).
- Model: Menagerie SO-101 on a cylinder base generated from `robot.yaml`, moved as a planar
  body with velocity actuators, response lag and optional noise. Joint names, degrees and the
  0–100 gripper mapping follow `lerobot/so101-tabletop-mujoco`.
- Rendering: `MUJOCO_GL=osmesa` by default in the container so every machine gets the same
  pixels; `egl` opt-in on GPU hosts.
- Scenes in `config/scenes/*.yaml` (empty floor, coloured targets, cube pick) with seeded
  resets and an optional scoring function.
- **`robot sim-check <team>`** (the gate): the app starts, runs N seconds in lockstep, trips
  no safety limit, and exits cleanly on stop. Task success is scoring, reported separately.

### Real robot and Pi 4 (`real_lekiwi` backend, `scripts/pi`, `docker/compose.robot.yaml`)
- OS: Raspberry Pi OS Lite 64-bit (Trixie). Docker from Docker's Debian apt repository.
- `bootstrap.sh` (idempotent): Docker, udev rule for a stable `/dev/buildathon-bus` symlink,
  remove `brltty`, groups, hostname, fixed address, systemd unit that starts the host on boot.
- Host image: `python:3.12-slim-trixie`, `lerobot[lekiwi]==0.7.0`, torch from the CPU index,
  `pyarrow>=22`. Only this container gets devices.
- Calibration stored in a volume (`HF_LEROBOT_CALIBRATION`) and committed under
  `config/calibration/` so a re-flashed card restores it.
- `robot doctor`: Pi throttle and undervoltage flags, serial port, ping motor IDs 1–9, servo
  voltage, temperature and error flags, camera formats and measured FPS, disk, Wi-Fi signal.
- Organizer-only commands (refuse without `--organizer`): `setup-motors`, `calibrate`,
  `wheel-test` (each wheel alone, wheels off the ground), `record` (for the replay backend).
- LifeCam: opened by `/dev/v4l/by-id/...`, MJPG 640x480@30; `doctor` sets manual exposure and
  disables autofocus with `v4l2-ctl` (auto-exposure halves the frame rate in low light).

### Offloading (`packages/perception`)
- **Simplest mode: tethered.** The whole app runs on the laptop against the Pi; perception is
  a local function call with the laptop's GPU.
- **Onboard mode: perception worker.** A worker on the laptop subscribes to the host's
  observation stream (frames are already JPEG, nothing is re-encoded on the Pi), runs the
  model, and publishes results back through the host's relay bus to the onboard app.
- Device picked automatically (cuda → mps → cpu). Runs as a CUDA container on Linux/WSL2 or
  natively with `uv run` on macOS (Docker on macOS has no GPU access).
- First model: YOLO11n-seg. FastSAM, SAM 2 and VLMs (Ollama `qwen3-vl`/`gemma3`, or a hosted
  API) are later additions behind the same worker interface.
- Documented control pattern: fast local loop (30 Hz), perception at 2–10 Hz, stale results
  rejected, robot stops if perception goes silent.
- On-Pi fallback: classical OpenCV (colour thresholds, ArUco/AprilTag) in the examples.

### Submission and deploy (one shared robot)
- Participants: `robot sim`, `robot run`, `robot sim-check` locally, then `git push` their
  `teams/<team>/` directory.
- Organizer station (`scripts/station/deploy.py`): pulls the team directory, re-runs
  `sim-check`, copies the code to the Pi, installs `requirements.txt` into a cached volume
  on the Pi, stops the previous app, starts the new one in safe mode with a fresh session id
  and a run-time cap. The SDK is mounted from the repo, so a fix during the event is a
  `git pull`.
- Images are built once and pre-pulled before the event; the robot needs no internet to run.

### Agent docs and skills
- `AGENTS.md` (under 200 lines): what the robot is, architecture map, command cheat sheet,
  units and frames, hard rules (sim first; never write servo registers; never edit limits),
  links into `docs/`. `CLAUDE.md` contains `@AGENTS.md`. No nested instruction files.
- Rules are enforced robot-side (session id, heartbeat, organizer deploy), not by trusting
  agents to follow instructions.
- Skills, authored in `.agents/skills/` and copied to `.claude/skills/` by
  `scripts/sync-skills.py` (symlinks break on Windows):

| Skill | For | Purpose |
|---|---|---|
| `write-behavior` | participants | Scaffold and write an app with the SDK; units, loop template |
| `run-sim` | participants | Start the sim, run an app, read traces and snapshots, run `sim-check` |
| `offload-perception` | participants | Tethered mode, the perception worker, adding a model |
| `debug-robot` | both | `doctor`, logs, the known-failure table |
| `hardware-bringup` | organizers | The staged bring-up sequence, one confirmed step at a time |
| `run-event` | organizers | Station deploy, slots, e-stop, recovery from a re-flash |

  While building I will use the existing `skill-creator` skill to author and test these.

## Build order

**Phase 0 — Hardware bring-up with stock LeRobot (needs the robot; do first).**
Flash the Pi, install LeRobot in a container, then `lerobot-setup-motors`,
`lerobot-calibrate`, stock `lekiwi_host`, and a laptop script that drives the base and arm.
In the same pass: photograph and measure the wheels (type, angles, radius), time the battery,
test LifeCam frame rate, fit the servo power cut-off switch. This answers the biggest
unknowns before any custom code depends on them. In parallel (no hardware): measure MuJoCo
software-render speed in Docker on a CPU-only laptop.

**Milestone 1 — the whole loop, minimal.**
SDK (`observe`, `drive`, `send_action`, `stop`); host with mock, sim (cylinder base, one
camera) and real backends plus clamps, watchdog and operator heartbeat; dashboard with camera,
state and stop; `02_drive_square` passing `sim-check`, then running in a container on the Pi
through the station deploy script.

**Milestone 2 — participant experience.**
Arm API and named poses, remaining example apps and scenes, `--trace`, replay backend,
perception worker with one model, `AGENTS.md`, `docs/`, the four participant skills.

**Milestone 3 — event readiness.**
LeKiwi shim for stock LeRobot tools, organizer skills and runbook, laptop preflight script,
spare SD card image, full dry run with a volunteer team.

**Deferred unless time allows:** wheel-contact physics, automated `base-calibrate` (edit
`robot.yaml` by hand), multi-arch GHCR CI (one manual `buildx` build), SAM 2 and VLM workers,
Cartesian inverse kinematics, skills-sync CI check, Copilot/Gemini pointer files.

## What might go wrong

**Hardware (untested, highest risk)**
- **Wheel type.** "Mecanum" wheels on a 3-wheel base do not match LeKiwi's omni-wheel
  kinematics. Mitigation: config-driven kinematics and `wheel-test`. If the geometry cannot
  move sideways, `vy` is disabled and the SDK says so.
- **Pi 4 is not the reference platform.** Import crash (pyarrow), heavy torch import, slower
  JPEG encode. Fallback: a "lite" real backend using `rustypot` directly with LeRobot's
  kinematics copied in, dropping the LeRobot/torch dependency.
- **Power.** Nine servos and a Pi on one battery; undervoltage shows up as random serial
  timeouts. Needs a 5 V / 3 A+ converter for the Pi and servos fed from the battery directly.
- **Motor IDs.** Factory servos all ship as ID 1 and must be set one at a time (6→1, then
  9→8→7). If the robot is already assembled, the chain must be unplugged to do it.
- **Runaway base.** Covered by the staleness watchdog, operator heartbeat, systemd watchdog
  and the physical servo power switch; the switch is the only one that survives every failure.
- **Tipping and self-collision** with the arm extended on an accelerating base. Mitigation:
  acceleration caps, joint limits, safe mode, an arena barrier.
- **Servo overload.** Stalled grippers trip protection and drop torque; `doctor` and the
  dashboard show error flags and temperature.
- **Camera.** Auto-exposure and autofocus, narrow field of view, vibration. One camera and
  no LiDAR or IMU means navigation relies on vision plus drifting wheel odometry.
- **SD card corruption** from switching the battery off. Mitigation: a spare flashed card,
  config and calibration in git, a documented shutdown step.
- **One robot is a single point of failure.** Bring spare servos, cables, battery and card.

**Software**
- **LeRobot churn.** v0.7.0 is a week old and changed its motor backend; the wire protocol
  changed in v0.6.1. Mitigation: exact pin and lock file; check the shim by hand against
  LeRobot's real `LeKiwiClient` before the event.
- **Sim-to-real gap.** Base slip, servo backlash, camera exposure and lens. A sim pass means
  "does not crash or trip limits", not "works on the robot". Mitigation: first real run in
  safe mode; measured geometry fed back into the sim; the replay backend for real images.
- **Slow software rendering** on weak laptops. Mitigation: lockstep for the gate, lower
  resolution and frame rate in config, a real-time-factor warning.
- **Ultralytics models are AGPL-3.0.** Acceptable for an event; kept optional and in the
  perception package so the core stays Apache-2.0.

**Event operations**
- **Venue Wi-Fi** often isolates clients and blocks mDNS. Mitigation: bring a dedicated 5 GHz
  router with an internet uplink (coding agents and hosted models need it); fixed Pi address.
- **Latency spikes.** Mitigation: local control loop, watchdog, stale-result rejection.
- **Contention for one robot.** Mitigation: session id, time slots, sim and replay as the
  main development loop.
- **Laptop setup time.** Mitigation: a preflight script and images pulled before the event.
- **Agents acting on the real robot.** Mitigation: participants hold no robot credentials;
  motion needs the organizer heartbeat.

## Verification

- **Tests (`uv run pytest`):** kinematics round trip against LeRobot's matrix; safety clamps,
  watchdog, heartbeat and e-stop on the mock backend; SDK ↔ host protocol; sim smoke.
- **Sim end to end:** `robot sim`, `robot run apps/02_drive_square`, open
  `http://localhost:8080`, confirm camera and motion; `robot sim-check` passes for every
  example twice with identical results; repeat on a CPU-only machine and on macOS/Windows
  Docker Desktop.
- **Offload:** run the perception worker against the sim, confirm masks reach
  `05_offload_segment`; kill the worker and confirm the robot stops.
- **Pi without motors:** `bootstrap.sh` on a fresh card; `robot doctor` reports; host starts
  on boot with the mock backend.
- **Real robot, staged:** wheels off the ground → `doctor`, `wheel-test`; on the floor in
  safe mode → `01_keyboard_teleop`, `02_drive_square`. Then the failure drills: stop the app
  mid-run, drop the organizer heartbeat, turn off the router, `kill -9` the host, press
  e-stop, flip the power switch. The base must stop in every case.
- **Full path:** a volunteer submits a team directory; the station gates and deploys it.
- **Agent docs:** in a fresh clone, ask a coding agent to write and sim-check a new behavior
  using only the repo; `skills-ref validate` passes for every skill.

## Assumptions to confirm during build

- The Pi 4 has at least 4 GB RAM.
- The wheel servos are already, or can be, set to IDs 7, 8 and 9.
- A dedicated router with an internet uplink can be brought to the venue.
