"""Wire protocol shared by the SDK and the robot host.

Three ZeroMQ sockets on the host:

* observations  PUB   multipart: [b"obs", JSON header, JPEG, JPEG, ...]
* commands      PULL  one JSON message per command
* requests      REP   JSON request -> multipart reply [JSON, JPEG, ...]

Key names follow LeRobot's LeKiwi robot so that data is interchangeable.
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = 1

DEFAULT_PORT_OBS = 5560
DEFAULT_PORT_CMD = 5561
DEFAULT_PORT_RPC = 5562
DEFAULT_PORT_DASHBOARD = 8080

OBS_TOPIC = b"obs"

ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
GRIPPER = "gripper"
ARM_KEYS = tuple(f"arm_{j}.pos" for j in ARM_JOINTS)
GRIPPER_KEY = "arm_gripper.pos"
POS_KEYS = ARM_KEYS + (GRIPPER_KEY,)
BASE_KEYS = ("x.vel", "y.vel", "theta.vel")
ALL_KEYS = POS_KEYS + BASE_KEYS


def joint_key(joint: str) -> str:
    """'shoulder_pan' -> 'arm_shoulder_pan.pos' (also accepts the full key)."""
    if joint in POS_KEYS:
        return joint
    key = f"arm_{joint}.pos"
    if key not in POS_KEYS:
        raise KeyError(f"unknown joint {joint!r}; valid joints: {', '.join(ARM_JOINTS + (GRIPPER,))}")
    return key


def dumps(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


def loads(raw: bytes) -> Any:
    return json.loads(raw.decode())


def encode_obs(header: dict, images: dict[str, bytes]) -> list[bytes]:
    """Observation as multipart frames. `images` maps camera name -> JPEG bytes."""
    header = dict(header)
    header["cams"] = list(images)
    return [OBS_TOPIC, dumps(header), *images.values()]


def decode_obs(frames: list[bytes]) -> tuple[dict, dict[str, bytes]]:
    if frames and frames[0] == OBS_TOPIC:
        frames = frames[1:]
    header = loads(frames[0])
    cams = header.get("cams", [])
    return header, dict(zip(cams, frames[1:]))


def parse_host(host: str | None, default: str = "localhost") -> tuple[str, int, int, int]:
    """'pi.local' or 'pi.local:5560' -> (hostname, obs port, cmd port, rpc port).

    A port, when given, is the observation port; command and request ports follow it.
    """
    host = host or default
    name, _, port = host.partition(":")
    base = int(port) if port else DEFAULT_PORT_OBS
    return name, base, base + 1, base + 2
