# Architecture

```
 app (participant code)                 robot host: one program, three backends
 +---------------------------+  5561    +----------------------------------------------+
 | buildathon SDK            |--------->| commands  (ZeroMQ PULL, JSON, with session)  |
 | Robot / Arm / Gripper     |<---------| observations (PUB: JSON header + JPEG)       |
 +---------------------------+  5560    | requests  (REP 5562: hello, status, step...) |
                                        | safety filter -> backend                     |
   browser  http://host:8080  --------->| dashboard                                    |
                                        +----------------------+-----------------------+
                                             sim (MuJoCo)   real (LeRobot)   mock
```

- **One contract.** Apps only know the SDK. The host speaks the same protocol whether its
  backend is the simulator, the real robot or the test mock. `ROBOT_HOST` picks which host.
- **Safety is in the host**, between the app's command and the backend, so it behaves the same
  in simulation and on the robot. See [safety.md](safety.md).
- **The host owns the hardware.** On the Pi only the host container has the serial port and
  camera. App containers have neither.
- **`config/robot.yaml` describes the robot once.** The real backend uses it for wheel
  kinematics and limits; the simulator builds its model from it.

## A control tick (30 per second)

1. Take the newest valid command (correct session, known keys).
2. Safety filter: clamp to limits, move arm targets at limited speed, ramp base velocity,
   apply watchdog, e-stop, heartbeat, session and arm-only rules.
3. Backend writes the filtered action, advances (sim) and reads state.
4. Integrate wheel odometry, capture a camera frame if one is due, publish the observation.

## Real time and lockstep

Normally the host ticks on the wall clock. With `--lockstep` (the gate) it ticks only when a
client sends a `step` request, which makes runs deterministic and independent of machine speed.

## The real backend

`backends/real_lekiwi.py` wraps LeRobot v0.7.0's `LeKiwi` robot (arm servos 1-6 in position
mode, wheel servos 7-9 in velocity mode, one serial bus). It overrides only the two wheel
kinematics methods, to use measured geometry from `robot.yaml`; with the default geometry the
output is identical to stock LeKiwi (checked in `tests/test_kinematics.py` and against a real
LeRobot install). With `base.present: false` it uses LeRobot's `SO101Follower` instead.

## Ports

| Port | Purpose |
|---|---|
| 5560 | Observations |
| 5561 | Commands. On the Pi this is not published to the network unless tethering is enabled |
| 5562 | Requests |
| 8080 | Dashboard |
| 5555, 5556 | Reserved for a LeRobot `LeKiwiClient` compatibility shim (not built) |

## Not built yet

Perception offload worker and relay, replay backend, the LeKiwi compatibility shim, CI image
builds. See `PLAN.md`.
