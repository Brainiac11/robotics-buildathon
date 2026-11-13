#!/usr/bin/env bash
# Start the REAL robot's host on this computer (servo board plugged into USB), in the foreground.
# THIS ENABLES TORQUE: the arm stiffens and holds its pose, and the robot can then be driven.
#
#   ./scripts/start-robot-host.sh [--base] [--full-speed] [serial-device]
#
#   (default)      arm-only: the wheels are locked and cannot be driven
#   --base         enable the wheels (robot on a stand or on the floor, never while clamped)
#   --full-speed   normal limits (default is safe mode: half speed)
#   LAN=1          also accept connections from other machines (default: this computer only)
#
# Then, in another terminal:   uv run robot teleop              (drive it by hand)
#                         or:   uv run robot slot teams/<team>   (run a team's app)
# Both use the token saved in .robot-token.
# Stop with Ctrl-C. WHEN THE HOST STOPS THE ARM GOES LIMP: support it first.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BASE=0; MODE="--safe-mode"; DEVICE=""
for arg in "$@"; do
    case "$arg" in
        --no-base) BASE=0 ;;
        --base) BASE=1 ;;
        --full-speed) MODE="" ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) DEVICE="$arg" ;;
    esac
done
[ -n "$DEVICE" ] || DEVICE="$(ls /dev/buildathon-bus /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -1 || true)"
[ -n "$DEVICE" ] && [ -e "$DEVICE" ] || { echo "No servo board found. Plug it in, or pass the device (for example /dev/ttyACM0)."; exit 1; }
docker image inspect buildathon-host-real >/dev/null 2>&1 || {
    echo "Building the host image (first time only, a few minutes)..."
    docker build -q -f docker/Dockerfile.host-real -t buildathon-host-real . >/dev/null
}

# One token per checkout, kept out of git. `robot teleop` and the other organizer commands read it.
if [ -z "${BUILDATHON_ORGANIZER_TOKEN:-}" ]; then
    [ -f .robot-token ] || (umask 077; head -c 12 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 12 > .robot-token)
    BUILDATHON_ORGANIZER_TOKEN="$(cat .robot-token)"
fi
BIND="127.0.0.1:"; [ "${LAN:-0}" = "1" ] && BIND=""

docker rm -f buildathon-mirror-reader buildathon-host >/dev/null 2>&1 || true   # they would hold the serial port
RUN=(docker run --rm --init --name buildathon-host
     --device "$DEVICE:/dev/buildathon-bus" --group-add "$(stat -c %g "$DEVICE")"
     -v "$PWD/config:/repo/config:ro" -v "$PWD/config/calibration:/data/calibration:ro"
     -e BUILDATHON_ORGANIZER_TOKEN="$BUILDATHON_ORGANIZER_TOKEN" -e BUILDATHON_BASE_ENABLED="$BASE")

echo "== Pre-flight (read-only: nothing moves, torque stays off)"
if out="$("${RUN[@]}" --entrypoint python buildathon-host-real -m buildathon_host --backend real --preflight-only 2>&1)"; then
    echo "$out" | grep -v "Warning\|warn(\|acceleratesupport"
else
    echo "$out" | grep -v "Warning\|warn(\|acceleratesupport"
    echo; echo "Fix the problem above, then run this again."; exit 1
fi

cat <<MSG

== About to ENABLE TORQUE on the real robot ($DEVICE)
   base: $([ "$BASE" = 1 ] && echo "ON  -> put the robot on a stand with ALL WHEELS OFF THE GROUND for a first run" || echo "off (arm-only)")
   limits: $([ -n "$MODE" ] && echo "safe mode (half speed)" || echo "FULL speed")

   Before you continue:
     - nothing and nobody within the arm's reach (about half a metre around the base)
     - you can reach the servo power switch
     - the arm will stiffen and hold the pose it is in now
     - when you stop this (Ctrl-C) the arm goes LIMP: support it first

MSG
read -r -p "Type yes to enable torque: " answer
[ "$answer" = "yes" ] || { echo "Not started."; exit 1; }

echo
echo "Dashboard: http://localhost:8080"
echo "In another terminal:   uv run robot teleop   |   uv run robot slot teams/<team>"
echo "Emergency: space bar on the dashboard, 'p' in teleop, or the servo power switch."
echo
exec "${RUN[@]}" -it -p "${BIND}5560-5562:5560-5562" -p "${BIND}8080:8080" buildathon-host-real $MODE
