"""What the host needs from a robot, real or simulated."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Backend(ABC):
    mode = "mock"  # reported to apps: "sim", "real" or "mock"
    realtime = True  # False: time only advances through step()

    @abstractmethod
    def connect(self) -> None: ...

    def close(self) -> None: ...

    @abstractmethod
    def read(self) -> dict[str, float]:
        """Measured state with all nine LeKiwi keys (base velocities are 0 if there is no base)."""

    @abstractmethod
    def write(self, action: dict[str, float]) -> None:
        """Send a full, already safety-filtered action (all nine keys)."""

    def step(self, dt: float) -> None:
        """Advance simulated time. Real hardware does nothing here."""

    @abstractmethod
    def now(self) -> float:
        """Robot time in seconds: simulation time in the sim, monotonic clock otherwise."""

    def capture(self) -> dict[str, bytes]:
        """One JPEG per camera, by camera name."""
        return {}

    def overview(self) -> bytes | None:
        """A third-person JPEG for the dashboard (sim only)."""
        return None

    def stop_base(self) -> None:
        """Stop the wheels immediately, bypassing the normal command path."""

    def set_base_enabled(self, enabled: bool) -> None:
        """Called when the base is switched on or off at run time."""

    def reset(self, seed: int | None = None) -> None:
        """Put the world back to its start state (sim only)."""

    def extras(self) -> dict:
        """Extra fields for the observation header: health readings, ground truth in sim."""
        return {}
