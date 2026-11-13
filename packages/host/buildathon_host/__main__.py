"""Start the robot host:  python -m buildathon_host --backend sim|real|mock"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys


def _choose_renderer(backend: str) -> None:
    """Pick a headless OpenGL backend for MuJoCo before it is imported.

    Linux: try EGL (GPU), fall back to OSMesa (software). macOS/Windows use their native default.
    Set MUJOCO_GL yourself to override.
    """
    if backend not in ("sim", "mirror") or os.environ.get("MUJOCO_GL") or not sys.platform.startswith("linux"):
        return
    os.environ["MUJOCO_GL"] = "egl"
    try:
        import mujoco

        mujoco.GLContext(64, 64).free()
    except Exception:
        # The failed EGL import cannot be undone in this process: start again with OSMesa.
        os.environ["MUJOCO_GL"] = "osmesa"
        os.execv(sys.executable, [sys.executable, "-m", "buildathon_host", *sys.argv[1:]])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="buildathon-host", description=__doc__)
    ap.add_argument("--backend", choices=["sim", "real", "mirror", "mock"], default="sim")
    ap.add_argument("--config", help="path to robot.yaml (default: config/robot.yaml in the repo)")
    ap.add_argument("--scene", default="table", help="simulation scene from config/scenes/")
    ap.add_argument("--lockstep", action="store_true", help="sim advances only when a client steps it")
    ap.add_argument("--no-base", action="store_true", help="arm-only mode: the base cannot be driven")
    ap.add_argument("--base", action="store_true", help="enable the wheeled base (off by default in robot.yaml)")
    ap.add_argument("--safe-mode", action="store_true", help="reduced speed limits")
    ap.add_argument(
        "--rehearse",
        action="store_true",
        help="sim/mock only: require the organizer heartbeat and a session, exactly like the real robot",
    )
    ap.add_argument("--no-render", action="store_true", help="sim without camera images (fastest)")
    ap.add_argument("--port", type=int, help="first of three consecutive ports (obs, cmd, rpc)")
    ap.add_argument("--dashboard-port", type=int, help="0 disables the dashboard")
    ap.add_argument("--camera-mount", choices=["workspace", "wrist", "base_front"])
    ap.add_argument(
        "--preflight-only",
        action="store_true",
        help="real robot: run the read-only checks made before torque is enabled, then exit",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("OpenGL.acceleratesupport").setLevel(logging.WARNING)  # an optional speed-up is absent: not a problem
    _choose_renderer(args.backend)

    from .backends import make_backend
    from .config import load_config
    from .server import Host

    cfg = load_config(args.config)
    if args.base:
        cfg.base.enabled = True
    if args.no_base:
        cfg.base.enabled = False
    if args.camera_mount:
        cfg.camera.mount = args.camera_mount
    if args.port:
        cfg.network.port_obs, cfg.network.port_cmd, cfg.network.port_rpc = args.port, args.port + 1, args.port + 2
    if args.dashboard_port is not None:
        cfg.network.port_dashboard = args.dashboard_port

    backend = make_backend(args.backend, cfg, realtime=not args.lockstep, scene=args.scene, render=not args.no_render)
    if args.preflight_only:
        if args.backend != "real":
            ap.error("--preflight-only is for --backend real")
        try:
            backend.preflight()
        except (RuntimeError, ConnectionError) as exc:
            raise SystemExit(f"PRE-FLIGHT FAILED: {exc}") from None
        print("pre-flight passed: the host can be started")
        return
    host = Host(
        cfg,
        backend,
        lockstep=args.lockstep,
        dashboard=bool(cfg.network.port_dashboard),
        organizer_token=os.environ.get("BUILDATHON_ORGANIZER_TOKEN", ""),
        safe_mode=args.safe_mode,
        heartbeat_required=True if args.rehearse else None,
        session_required=True if args.rehearse else None,
    )

    def _stop(signum, frame):
        host.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        host.run()
    except (RuntimeError, ConnectionError) as exc:
        # Pre-flight refusals and lost hardware: say what happened, without a traceback.
        raise SystemExit(f"HOST STOPPED: {exc}") from None


if __name__ == "__main__":
    main()
