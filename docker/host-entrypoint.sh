#!/bin/sh
# Runs the robot host on the Pi. Whatever way the host exits (clean stop, crash, watchdog),
# the wheels are zeroed afterwards: they are in velocity mode and would otherwise keep turning.
if [ "$1" = "tool" ]; then
    shift
    name="$1"; shift
    case "$name" in
        doctor)       exec python -m buildathon_host.tools.doctor "$@" ;;
        wheel-test)   exec python -m buildathon_host.tools.wheel_test "$@" ;;
        stop-wheels)  exec python -m buildathon_host.tools.stop_wheels "$@" ;;
        read-joints)  exec python -m buildathon_host.tools.read_joints "$@" ;;
        setup-motors) exec python -m buildathon_host.tools.lerobot_cli setup-motors ;;
        calibrate)    exec python -m buildathon_host.tools.lerobot_cli calibrate ;;
        stock-host)   # LeRobot's own host, unmodified: the fallback if ours misbehaves
                      exec python -m lerobot.robots.lekiwi.lekiwi_host --robot.id="${ROBOT_ID:-buildathon}" \
                          --robot.port="${SERIAL_PORT:-/dev/buildathon-bus}" --robot.calibration_dir=/data/calibration \
                          --robot.cameras='{}' --host.connection_time_s=3600 "$@" ;;
        *) echo "unknown tool: $name (doctor, read-joints, wheel-test, stop-wheels, setup-motors, calibrate, stock-host)"; exit 2 ;;
    esac
fi
python -m buildathon_host --backend real "$@"
code=$?
python -m buildathon_host.tools.stop_wheels
exit $code
