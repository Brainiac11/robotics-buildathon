#!/usr/bin/env bash
# Mirror the real robot in the simulator, READ-ONLY: nothing is commanded and torque is not touched.
#
#   ./scripts/mirror.sh [serial-device]        then open http://localhost:8090
#
# Move the real arm by hand (torque off): the simulated arm should make the same movement.
# Push the robot along the floor: the "x.vel / y.vel / theta.vel" rows should show
# forward = +x, left = +y, counter-clockwise = +theta. Ctrl-C to stop.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
DEVICE="${1:-/dev/buildathon-bus}"
[ -e "$DEVICE" ] || DEVICE="$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -1 || true)"
[ -n "$DEVICE" ] || { echo "no serial device found; pass it as the first argument"; exit 1; }
CAL="${CALIBRATION_DIR:-$PWD/config/calibration}"
NAME=buildathon-mirror-reader
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }   # the reader does not notice a closed pipe by itself
trap cleanup EXIT
cleanup
echo "reading $DEVICE (read-only); calibration from $CAL; dashboard: http://localhost:${MIRROR_DASHBOARD_PORT:-8090}"
docker run --rm --init --name "$NAME" --device "$DEVICE:/dev/buildathon-bus" --group-add "$(stat -c %g "$DEVICE")" \
    -v "$PWD/config:/repo/config:ro" -v "$CAL:/data/calibration:ro" \
    buildathon-host-real tool read-joints \
  | uv run python -m buildathon_host --backend mirror --port "${MIRROR_PORT:-5760}" --dashboard-port "${MIRROR_DASHBOARD_PORT:-8090}"
