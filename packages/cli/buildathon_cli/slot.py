"""`robot slot`: run one team's app on the real arm, from the laptop the arm is plugged into.

For the supervisor of a testing slot. One command does what the event playbook asks for:
gate the code, first run at reduced speed, keep the robot enabled only while the app runs,
stop cleanly, and log a one-line note.

The robot host must already be running (scripts/start-robot-host.sh). The robot can move only
while this command is running: Ctrl-C stops the app and blocks motion.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from buildathon import Robot, RobotError

from .apps import App
from .simcheck import sim_check
from .teleop import Organizer

LOG_DIR = Path("slots")


def run_slot(
    app: App,
    *,
    host: str | None,
    token: str,
    full_speed: bool = False,
    allow_base: bool = False,
    skip_check: bool = False,
    max_runtime: float = 180.0,
    note: str | None = None,
) -> int:
    if app.interactive:
        raise SystemExit(f"{app.name} is interactive (needs a keyboard); use `robot teleop` instead.")

    print(f"== 1/4 gate: {app.name}")
    if skip_check:
        print("   SKIPPED (--skip-check)")
    elif sim_check(app) != 0:
        print("\nNot run on the robot: the app must pass the gate first.")
        return 1

    try:
        info, _ = Robot(host, timeout=3.0)._rpc({"op": "hello"})
    except RobotError:
        raise SystemExit("No robot host answered. Start it first: ./scripts/start-robot-host.sh") from None
    if info.get("mode") != "real":
        print(f"   note: this host is the {info.get('mode')} one, not the real robot")

    want_base = app.needs_base and allow_base
    if app.needs_base and not allow_base:
        print("   this app asks for the wheels, but they stay OFF unless you add --base")
    print(f"== 2/4 robot: {'safe mode (half speed)' if not full_speed else 'FULL speed'}, "
          f"wheels {'ON' if want_base else 'off'}, limit {max_runtime:.0f}s")  # fmt: skip
    organizer = Organizer(host, token, safe_mode=not full_speed)
    try:
        if info.get("base_present", True):
            organizer._call({"op": "set_base", "enabled": want_base})
        organizer._call({"op": "clear_estop"})
        session = organizer.start(max_runtime_s=max_runtime)
    except RobotError as exc:
        raise SystemExit(f"The robot host refused: {exc}") from None

    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = LOG_DIR / f"{stamp}-{app.name}.log"
    print(f"== 3/4 running {app.name}  (Ctrl-C stops it; output also in {out_path})\n")
    env = dict(os.environ, ROBOT_SESSION=session, PYTHONUNBUFFERED="1")
    if host:
        env["ROBOT_HOST"] = host
    started = time.monotonic()
    stopped_by = "finished"
    proc = subprocess.Popen(app.command(), cwd=app.path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        with out_path.open("w") as log:
            for line in proc.stdout:  # type: ignore[union-attr]
                sys.stdout.write("   | " + line)
                sys.stdout.flush()
                log.write(line)
        proc.wait()
    except KeyboardInterrupt:
        stopped_by = "stopped by supervisor"
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    finally:
        organizer.stop()  # heartbeat and session end here: nothing can move the robot now
    elapsed = time.monotonic() - started

    try:
        status = Robot(host, timeout=3.0)._rpc({"op": "status"})[0]["status"]
        events = status.get("events", {})
    except RobotError:
        events = {"host_unreachable": 1}
    if proc.returncode not in (0, None) and stopped_by == "finished":
        stopped_by = f"exit code {proc.returncode}"
    print(f"\n== 4/4 {app.name}: {stopped_by} after {elapsed:.0f}s. Motion is blocked again. Safety events: {events or 'none'}")
    print("   The arm holds its last pose. Use `uv run robot teleop` to move it back if needed.")

    if note is None and sys.stdin.isatty():
        try:
            note = input("   One-line note for the log (what ran, what broke, calibration state): ").strip()
        except (EOFError, KeyboardInterrupt):
            note = ""
    summary = (
        f"| {datetime.now():%a %H:%M} | {app.name} | {'safe' if not full_speed else 'full'} | "
        f"{stopped_by}, {elapsed:.0f}s | {events or 'none'} | {note or ''} |\n"
    )
    log_file = LOG_DIR / "slot-log.md"
    if not log_file.exists():
        log_file.write_text("| When | Team | Speed | Result | Safety events | Note |\n|---|---|---|---|---|---|\n")
    with log_file.open("a") as f:
        f.write(summary)
    print(f"   logged in {log_file}")
    return 0 if proc.returncode == 0 else 1
