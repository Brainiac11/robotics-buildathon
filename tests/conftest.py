import threading
import time

import pytest
from buildathon import Robot
from buildathon_host.backends import make_backend
from buildathon_host.config import load_config
from buildathon_host.server import Host


def free_port_block() -> int:
    from buildathon_cli.simcheck import _free_port_block

    return _free_port_block()


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def start_host(config):
    """Start a host in a background thread. Returns (host, 'localhost:port')."""
    running = []

    def _start(backend="mock", lockstep=True, no_base=False, base_present=True, **host_kw):
        cfg = load_config()
        port = free_port_block()
        cfg.network.port_obs, cfg.network.port_cmd, cfg.network.port_rpc = port, port + 1, port + 2
        cfg.network.port_dashboard = 0
        cfg.base.enabled = not no_base
        cfg.base.present = base_present
        be = make_backend(backend, cfg, realtime=not lockstep, scene="empty", render=False)
        host = Host(cfg, be, lockstep=lockstep, dashboard=False, **host_kw)
        thread = threading.Thread(target=host.run, daemon=True)
        thread.start()
        address = f"localhost:{port}"
        probe = Robot(address, timeout=0.5)
        for _ in range(40):
            try:
                probe._rpc({"op": "status"})
                break
            except Exception:
                time.sleep(0.05)
        running.append((host, thread))
        return host, address

    yield _start
    for host, thread in running:
        host.stop()
        thread.join(timeout=3)
