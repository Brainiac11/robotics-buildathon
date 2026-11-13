"""Check the Raspberry Pi, the servo bus and the camera, and say what to fix.

    python -m buildathon_host.tools.doctor            # read-only checks
    python -m buildathon_host.tools.doctor --fix-camera   # also set manual exposure / no autofocus

Safe to run at any time: it never moves a motor. NOT YET RUN ON HARDWARE.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from ..config import load_config

RESULTS: list[tuple[str, str, str]] = []
THROTTLE_BITS = {
    0: "under-voltage NOW",
    1: "CPU frequency capped NOW",
    2: "throttled NOW",
    3: "soft temperature limit NOW",
    16: "under-voltage has occurred since boot",
    17: "frequency capping has occurred since boot",
    18: "throttling has occurred since boot",
    19: "soft temperature limit has occurred since boot",
}


def report(level: str, name: str, detail: str) -> None:
    RESULTS.append((level, name, detail))
    print(f"[{level:4s}] {name}: {detail}")


def run(cmd: list[str], timeout: float = 5.0) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_system() -> None:
    model = Path("/proc/device-tree/model")
    report("INFO", "board", model.read_text().strip("\x00\n") if model.exists() else "not a Raspberry Pi (or /proc not visible)")
    try:
        mem_kb = int(next(l for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal")).split()[1])
        report(
            "OK" if mem_kb > 3_500_000 else "WARN",
            "memory",
            f"{mem_kb / 1e6:.1f} GB" + ("" if mem_kb > 3_500_000 else " (under 4 GB: LeRobot + PyTorch will be tight)"),
        )
    except Exception:
        pass
    temp = Path("/sys/class/thermal/thermal_zone0/temp")
    if temp.exists():
        c = int(temp.read_text()) / 1000
        if c > 0:  # some machines expose a dummy sensor
            report(
                "OK" if c < 70 else "WARN",
                "CPU temperature",
                f"{c:.0f} C" + ("" if c < 70 else " (throttles at 80 C: add a heatsink or fan)"),
            )
    out = run(["vcgencmd", "get_throttled"])
    if out and "=" in out:
        flags = int(out.strip().split("=")[1], 16)
        active = [text for bit, text in THROTTLE_BITS.items() if flags & (1 << bit)]
        if not active:
            report("OK", "power/throttle flags", "0x0")
        else:
            level = "FAIL" if flags & 0x1 else "WARN"
            report(
                level,
                "power/throttle flags",
                f"{hex(flags)}: {'; '.join(active)}. Under-voltage causes random servo timeouts: "
                "use a 5 V / 3 A+ supply for the Pi and short, thick wires.",
            )
    else:
        report("INFO", "power/throttle flags", "vcgencmd not available here (run `vcgencmd get_throttled` on the Pi itself)")
    usage = shutil.disk_usage("/")
    report("OK" if usage.free > 2e9 else "WARN", "disk", f"{usage.free / 1e9:.1f} GB free")
    report("INFO", "hostname", socket.gethostname())


def check_serial(cfg) -> bool:
    port = cfg.real.serial_port
    candidates = sorted(glob.glob("/dev/serial/by-id/*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    if os.path.exists(port):
        report("OK", "servo bus port", f"{port} -> {os.path.realpath(port)}")
        if not os.access(port, os.R_OK | os.W_OK):
            report(
                "FAIL",
                "servo bus permissions",
                f"no read/write access to {port}. Run scripts/pi/bootstrap.sh, or add the user to the dialout group.",
            )
            return False
        return True
    report(
        "FAIL",
        "servo bus port",
        f"{port} does not exist. Serial devices found: {', '.join(candidates) or 'none'}. "
        "If one is listed, the udev rule is missing (run scripts/pi/bootstrap.sh) or the board is unplugged. "
        "If none: check the USB cable, and that `brltty` is not installed.",
    )
    return False


def check_motors(cfg) -> None:
    try:
        from lerobot.motors import Motor, MotorNormMode, SerialMotorsBus
    except ImportError as exc:
        report("WARN", "motors", f"LeRobot is not importable here ({exc}); run the doctor inside the host container")
        return
    names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
    motors = {n: Motor(i + 1, "sts3215", MotorNormMode.RANGE_M100_100) for i, n in enumerate(names)}
    if cfg.base.present:
        motors.update(
            {
                n: Motor(i, "sts3215", MotorNormMode.RANGE_M100_100)
                for n, i in (("left_wheel", 7), ("back_wheel", 8), ("right_wheel", 9))
            }
        )
    bus = SerialMotorsBus(port=cfg.real.serial_port, motors=motors)
    try:
        bus.connect(handshake=False)
    except Exception as exc:
        report("FAIL", "servo bus", f"could not open the port: {exc}")
        return
    try:
        missing = []
        for name, motor in motors.items():
            if bus.ping(name, num_retry=2) is None:
                missing.append(f"{name} (ID {motor.id})")
                continue
            detail = f"ID {motor.id} answers"
            try:
                volts = bus.read("Present_Voltage", name, normalize=False) / 10.0
                temp = bus.read("Present_Temperature", name, normalize=False)
                detail += f", {volts:.1f} V, {temp} C"
                level = "WARN" if temp >= 60 else "OK"
            except Exception as exc:
                level, detail = "WARN", detail + f" (could not read voltage/temperature: {exc})"
            report(level, f"motor {name}", detail)
        if missing:
            report(
                "FAIL",
                "motors missing",
                f"{', '.join(missing)}. A new servo ships as ID 1: IDs must be set one at a time "
                "with the setup-motors tool. Otherwise check the daisy-chain cable to the first missing motor, and servo power.",
            )
        else:
            report("OK", "motors", f"all {len(motors)} answer")
    finally:
        bus.disconnect(disable_torque=False)


def check_camera(cfg, fix: bool) -> None:
    import cv2

    by_id = sorted(glob.glob("/dev/v4l/by-id/*"))
    device = cfg.camera.device
    if not device or not os.path.exists(device):
        report(
            "FAIL",
            "camera device",
            f"{device!r} does not exist. Cameras found: {', '.join(by_id) or 'none'}. "
            "Put the path ending in '-video-index0' into camera.device in config/robot.yaml.",
        )
        return
    report("OK", "camera device", f"{device} -> {os.path.realpath(device)}")
    if shutil.which("v4l2-ctl"):
        controls = run(["v4l2-ctl", "-d", device, "-l"]) or ""
        if fix:
            wanted = {
                "auto_exposure": "1",
                "exposure_dynamic_framerate": "0",
                "focus_automatic_continuous": "0",
                "exposure_auto": "1",
                "exposure_auto_priority": "0",
                "focus_auto": "0",
            }
            applied = [
                f"{k}={v}"
                for k, v in wanted.items()
                if f"{k} " in controls and run(["v4l2-ctl", "-d", device, "-c", f"{k}={v}"]) is not None
            ]
            report("INFO", "camera controls", f"set {', '.join(applied) or 'nothing (no matching controls)'}")
        elif "auto_exposure" in controls or "exposure_auto" in controls:
            report(
                "INFO",
                "camera controls",
                "auto-exposure can halve the frame rate in dim light; re-run with --fix-camera to set manual exposure",
            )
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    try:
        if cfg.camera.fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*cfg.camera.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.camera.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.camera.height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        for _ in range(5):
            cap.read()
        frames, start = 0, time.monotonic()
        while time.monotonic() - start < 2.0:
            ok, frame = cap.read()
            frames += bool(ok)
        fps = frames / (time.monotonic() - start)
        if frames == 0:
            report("FAIL", "camera stream", "opened but delivered no frames (is another program using it?)")
        else:
            size = f"{frame.shape[1]}x{frame.shape[0]}"
            level = "OK" if fps >= cfg.camera.fps else "WARN"
            report(
                level,
                "camera stream",
                f"{size} at {fps:.0f} fps (apps get {cfg.camera.fps:.0f})"
                + ("" if level == "OK" else ": too slow; try --fix-camera, more light, or a lower camera.fps"),
            )
    finally:
        cap.release()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix-camera", action="store_true", help="set manual exposure and disable autofocus")
    ap.add_argument("--skip-motors", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    print(
        f"Doctor for {cfg.name}  (base {'present' if cfg.base.present else 'NOT fitted'}, "
        f"{'enabled' if cfg.base.enabled else 'disabled: arm-only'})\n"
    )
    for check in (
        check_system,
        lambda: check_serial(cfg) and not args.skip_motors and check_motors(cfg),
        lambda: check_camera(cfg, args.fix_camera),
    ):
        try:
            check()
        except Exception as exc:  # one broken check must not hide the others
            report("FAIL", "doctor", f"a check crashed: {type(exc).__name__}: {exc}")
    fails = sum(1 for level, _, _ in RESULTS if level == "FAIL")
    warns = sum(1 for level, _, _ in RESULTS if level == "WARN")
    print(f"\n{fails} failing, {warns} warnings.")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
