#!/usr/bin/env bash
# Prepare a fresh Raspberry Pi OS Lite (64-bit) for the robot. Safe to run again.
# NOT YET RUN ON A PI: read it before running it, and expect to fix small things.
#
#   sudo ./scripts/pi/bootstrap.sh            # from a checkout of this repo on the Pi
#
# What it does: installs Docker, removes brltty (it steals the servo board's serial port),
# adds a udev rule for a stable /dev/buildathon-bus, creates /opt/buildathon with a settings
# file and a random organizer token, and installs a service that starts the robot host at boot.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "run with sudo"; exit 1; fi
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
USER_NAME="${SUDO_USER:-pi}"
echo "== repo: $REPO   user: $USER_NAME"

if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "!! This is $(uname -m), not a 64-bit ARM system. Use Raspberry Pi OS Lite (64-bit)."; exit 1
fi

echo "== packages"
apt-get update -q
apt-get remove -y brltty 2>/dev/null || true
apt-get install -y -q ca-certificates curl git v4l-utils avahi-daemon

if ! command -v docker >/dev/null; then
    echo "== Docker (from Docker's Debian repository)"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker,dialout,video "$USER_NAME"

echo "== udev rule for the servo board"
install -m 0644 "$REPO/scripts/pi/99-buildathon.rules" /etc/udev/rules.d/99-buildathon.rules
udevadm control --reload-rules && udevadm trigger

echo "== /opt/buildathon"
install -d -o "$USER_NAME" -g "$USER_NAME" /opt/buildathon /opt/buildathon/calibration /opt/buildathon/app
if [[ ! -e /opt/buildathon/repo ]]; then ln -s "$REPO" /opt/buildathon/repo; fi
if [[ ! -f /opt/buildathon/robot.env ]]; then
    TOKEN="$(head -c 12 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 12)"
    cat > /opt/buildathon/robot.env <<ENV
# Settings for the robot host container. Edit, then: sudo systemctl restart buildathon-host
BUILDATHON_ORGANIZER_TOKEN=$TOKEN
# 1 = wheels can be driven, 0 = arm-only mode
BUILDATHON_BASE_ENABLED=1
ENV
    chown "$USER_NAME:$USER_NAME" /opt/buildathon/robot.env
    chmod 600 /opt/buildathon/robot.env
    echo "   organizer token: $TOKEN   (saved in /opt/buildathon/robot.env; keep it private)"
fi
# Restore calibration committed to the repo, without overwriting newer files on the Pi.
if compgen -G "$REPO/config/calibration/*.json" >/dev/null; then
    cp -n "$REPO"/config/calibration/*.json /opt/buildathon/calibration/ && chown -R "$USER_NAME:$USER_NAME" /opt/buildathon/calibration
fi

echo "== service (enabled, not started: bring the hardware up first)"
install -m 0644 "$REPO/scripts/pi/buildathon-host.service" /etc/systemd/system/buildathon-host.service
systemctl daemon-reload
systemctl enable buildathon-host.service

echo
echo "Done. Next:"
echo "  1. Log out and in again (group changes), or reboot."
echo "  2. Build the host image:  cd $REPO && docker compose -f docker/compose.robot.yaml build host"
echo "  3. Follow docs/hardware-bringup.md from step 2."
if command -v vcgencmd >/dev/null; then echo "  Power check now: $(vcgencmd get_throttled)  (throttled=0x0 is good)"; fi
