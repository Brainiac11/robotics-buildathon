"""`robot deploy`: put an app on the real robot. Run from the organizer station.

NOT YET RUN AGAINST A PI. The station needs: ssh access to the Pi (key-based), rsync, and the
organizer token in $BUILDATHON_ORGANIZER_TOKEN.

Steps: gate the app in simulation -> stop whatever is running -> copy the code -> switch the
base on or off for this app -> start a time-limited session in safe mode -> start the container.
The robot still only moves while an organizer holds `robot enable`.
"""

from __future__ import annotations

import os
import secrets
import shlex
import subprocess

from buildathon import Robot, RobotError

from .apps import App
from .simcheck import sim_check

REMOTE_REPO = "/opt/buildathon/repo"
REMOTE_APPS = "/opt/buildathon/apps"
COMPOSE = "docker compose -f docker/compose.robot.yaml --profile app"


def _ssh(target: str, command: str, check: bool = True) -> int:
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", target, command])
    if check and result.returncode != 0:
        raise SystemExit(f"remote command failed ({result.returncode}): {command}")
    return result.returncode


def _rpc(host: str, token: str, request: dict) -> dict:
    try:
        reply, _ = Robot(host, timeout=4.0)._rpc({**request, "token": token})
        return reply
    except RobotError as exc:
        raise SystemExit(f"robot host at {host} refused {request['op']!r}: {exc}") from None


def stop_app(ssh_target: str, host: str, token: str) -> None:
    _ssh(ssh_target, f"cd {REMOTE_REPO} && {COMPOSE} rm -sf app", check=False)
    _rpc(host, token, {"op": "session_stop"})


def deploy(
    app: App,
    *,
    ssh_target: str,
    host: str | None = None,
    token: str = "",
    no_base: bool = False,
    skip_check: bool = False,
    full_speed: bool = False,
    max_runtime: float = 180.0,
    follow: bool = True,
) -> int:
    host = host or ssh_target.split("@")[-1]
    arm_only = no_base or not app.needs_base
    if app.interactive:
        raise SystemExit(f"{app.name} is interactive (keyboard); run it tethered from a laptop instead of deploying it.")

    print(f"== 1/5 sim-check {app.name}")
    if skip_check:
        print("   SKIPPED by organizer (--skip-check)")
    elif sim_check(app, no_base=no_base) != 0:
        print("Not deployed: the app must pass sim-check first.")
        return 1

    print("== 2/5 stop the previous app")
    stop_app(ssh_target, host, token)

    print("== 3/5 copy the code")
    remote_dir = f"{REMOTE_APPS}/{app.name}"
    _ssh(ssh_target, f"mkdir -p {shlex.quote(remote_dir)}")
    rsync = [
        "rsync",
        "-az",
        "--delete",
        "--exclude",
        "__pycache__",
        "--exclude",
        ".git",
        f"{app.path}/",
        f"{ssh_target}:{remote_dir}/",
    ]
    if subprocess.run(rsync).returncode != 0:
        raise SystemExit("rsync failed")

    print(f"== 4/5 robot settings: base {'OFF (arm-only)' if arm_only else 'on'}, {'FULL speed' if full_speed else 'safe mode'}")
    status = _rpc(host, token, {"op": "status"})["status"]
    if not arm_only and not status.get("base_present", True):
        raise SystemExit("this app needs the base, but robot.yaml on the robot says no wheels are fitted")
    if status.get("base_present", True):
        _rpc(host, token, {"op": "set_base", "enabled": not arm_only})
    _rpc(host, token, {"op": "set_safe_mode", "enabled": not full_speed})
    session = f"{app.name}-{secrets.token_hex(3)}"
    reply = _rpc(host, token, {"op": "session_start", "session": session, "max_runtime_s": max_runtime})
    print(f"   session {session}, {reply['max_runtime_s']:.0f}s limit")

    print("== 5/5 start the app")
    env = f"APP_DIR={shlex.quote(remote_dir)} ROBOT_SESSION={shlex.quote(session)}"
    _ssh(ssh_target, f"cd {REMOTE_REPO} && {env} {COMPOSE} up -d --force-recreate app")
    print(f"\nDeployed. The robot moves only while an organizer runs:  robot enable --host {host}")
    print(f"Stop it:  robot estop --host {host}     End the run:  robot stop-app")
    if follow:
        print("-- app output (Ctrl-C stops watching, not the app) --")
        try:
            _ssh(ssh_target, "docker logs -f buildathon-app", check=False)
        except KeyboardInterrupt:
            pass
    return 0


def ssh_target_from(args) -> str:
    target = getattr(args, "ssh", None) or os.environ.get("ROBOT_SSH")
    if not target:
        raise SystemExit("give the Pi's ssh address with --ssh user@address, or set ROBOT_SSH")
    return target
