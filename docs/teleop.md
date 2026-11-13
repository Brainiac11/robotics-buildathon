# Teleoperation

Move the arm (and, when the wheels are enabled, drive the base) from the keyboard:

```bash
uv run robot teleop
```

It works the same against the simulator and the real robot. In simulation anyone can use it,
and it is the quickest way to get a feel for the robot or to find joint angles for a pose.
On the real robot it is an organizer tool.

## Keys

```text
  BASE (hold the key)          ARM (tap or hold)                 OTHER
    w / s   forward / back       z / c   shoulder pan  left/right   space   stop the base now
    a / d   left / right         r / f   shoulder lift up/down      + / -   base speed up / down
    q / e   turn left / right    t / g   elbow         up/down      [ / ]   arm step smaller / larger
                                 y / h   wrist flex    up/down      p       E-STOP (latches)
                                 u / j   wrist roll                 x       quit
                                 o / l   gripper open / close
```

- **The base moves only while a key is held.** It stops about half a second after you let go.
  Space stops it at once.
- **Arm keys nudge one joint** by a few degrees per press (3 by default; `[` and `]` change
  it). Hold a key to keep moving. The first press on a joint starts from where the joint
  actually is, so nothing jumps.
- The line at the bottom shows every joint angle, the base velocity and, if the robot will
  not move, why (`BLOCKED: ...`).
- Keys must be typed into the terminal running `robot teleop`, not the dashboard.

Starting speed is 0.10 m/s and 30 deg/s; `+` and `-` change it up to the robot's limits, or
start with `uv run robot teleop --speed 0.2 --turn-speed 60`.

## In the simulator

```bash
uv run robot sim                       # terminal 1; open http://localhost:8080
uv run robot teleop                    # terminal 2
```

To find joint angles for a pose: move the arm there with the keys and read the numbers off the
status line or the dashboard's State panel. Put them in your app with
`robot.arm.move_to({...})`, or add a named pose to `config/robot.yaml`.

The wheels are off by default, so the base keys report that the base is switched off. Start
the simulator with `uv run robot sim --base` to drive.

## On the real robot (organizers)

Teleop is how the real robot is first moved, so it is deliberately cautious.

**With the servo board plugged into this computer's USB:**

```bash
./scripts/start-robot-host.sh          # terminal 1: checks, asks, then enables torque
uv run robot teleop                    # terminal 2
```

`start-robot-host.sh`:

1. Runs a **pre-flight check** that only reads: calibration matches the motors, servo voltage,
   and the wrist roll is not near the point where its encoder wraps. If anything is wrong it
   says what to fix and stops, with torque still off.
2. Lists what must be true (clear space, wheels off the ground for a first run, a hand near
   the servo power switch) and waits for you to type `yes`.
3. Starts the robot host in safe mode (half speed). Torque comes on; the arm holds the pose it
   is in.

The wheels are locked off by default. Options: `--base` to enable them (never while the robot
is clamped), `--full-speed` for normal limits, `LAN=1` in front to let other machines connect.

`robot teleop` then holds the robot enabled and runs its session by itself, using the token
the script saved in `.robot-token`. **The robot can move only while teleop is running**: quit
it (`x`), close the terminal or lose the connection, and motion is blocked within a second.

**With the Raspberry Pi on the robot:** start the host on the Pi as in the
[organizer runbook](organizer-runbook.md), then from a laptop on the same network:

```bash
export BUILDATHON_ORGANIZER_TOKEN=<token from /opt/buildathon/robot.env on the Pi>
uv run robot teleop --host <robot address>
```

The command port must be reachable for this: on the Pi, start the tether
(`docker compose -f docker/compose.robot.yaml --profile tether up -d tether`).

### Stopping

| | |
|---|---|
| Stop the base | Let go of the key, or space |
| Stop everything, and keep it stopped | `p` in teleop, STOP on the dashboard, or `uv run robot estop` |
| Clear an e-stop | `uv run robot clear-estop` |
| End teleop | `x` |
| Shut the host down | Ctrl-C in its terminal. **The arm goes limp: hold it first** |
| Anything unexpected | The servo power switch |

### First time on this robot

Do these in order (the wheels are off unless you started the host with `--base`):

1. One arm joint at a time, small taps. Confirm each key moves the joint it says, the way it
   says. If a joint goes the other way, stop and note it: the simulator and the real arm
   disagree for that joint.
2. The gripper: `o` opens, `l` closes.
3. Only if you need the wheels: with the robot unclamped and on a stand with every wheel off
   the ground, restart the host with `--base` and try each base key briefly. A wheel turning
   the wrong way is fixed with `base.wheel_direction` in `config/robot.yaml`. Only then put the
   robot on the floor, with space around it.

## Troubleshooting

| You see | Meaning |
|---|---|
| `PRE-FLIGHT FAILED: wrist roll reads ...` | Turn the wrist by hand to the middle of its travel and start again. The mirror (`./scripts/mirror.sh`) shows the number live |
| `This host needs the organizer token` | Run from the repo folder (so `.robot-token` is found), or set `BUILDATHON_ORGANIZER_TOKEN` |
| `BLOCKED: estop` | Someone pressed stop. `uv run robot clear-estop` |
| `BLOCKED: no_organizer_heartbeat` for more than a moment | Teleop cannot reach the host; check the host terminal |
| Base keys say "base is switched off" | The default. Start the host (or simulator) with `--base` if you mean to drive |
| `No robot host answered` | Start the simulator or the robot host first |
| "Could not connect on port" when starting the host | Something else has the serial port: stop the mirror or another host |
