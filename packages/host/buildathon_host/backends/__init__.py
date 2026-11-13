from .base import Backend


def make_backend(name: str, config, **kw) -> Backend:
    """Create a backend by name. Imports are lazy so each image only needs its own dependencies."""
    if name == "mock":
        from .mock import MockBackend

        return MockBackend(config, **kw)
    if name == "sim":
        from .mujoco_sim import MujocoBackend

        return MujocoBackend(config, **kw)
    if name == "mirror":
        from .mirror import MirrorBackend

        return MirrorBackend(config, **kw)
    if name == "real":
        from .real_lekiwi import RealBackend

        return RealBackend(config, **kw)
    raise ValueError(f"unknown backend {name!r}; choose sim, real, mirror or mock")
