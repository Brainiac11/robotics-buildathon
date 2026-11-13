"""Locate an app and read its optional app.yaml."""

from __future__ import annotations

import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class App:
    name: str
    path: Path  # directory the app runs in
    entry: Path  # the Python file to run
    needs_base: bool = False  # the event runs arm-only: an app must ask for the wheels
    scene: str = "table"
    camera: str = ""  # workspace | wrist | base_front; empty = whatever robot.yaml says
    duration_s: float = 20.0
    interactive: bool = False  # needs a person at a keyboard: cannot be gated automatically

    def command(self) -> list[str]:
        """How to start the app. With a requirements.txt and uv available, uv adds those
        packages for this run only (cached after the first time), on top of the project's own."""
        if (self.path / "requirements.txt").is_file() and shutil.which("uv"):
            return ["uv", "run", "--with-requirements", "requirements.txt", "python", self.entry.name]
        return [sys.executable, self.entry.name]

    def code_hash(self) -> str:
        """Hash of every file in the app directory, so a gate result is tied to exact code."""
        digest = hashlib.sha256()
        for f in sorted(self.path.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and not f.name.startswith("."):
                digest.update(f.relative_to(self.path).as_posix().encode())
                digest.update(f.read_bytes())
        return digest.hexdigest()[:16]


def find_app(target: str) -> App:
    p = Path(target)
    if p.is_file() and p.suffix == ".py":
        path, entry = p.resolve().parent, p.resolve()
    elif p.is_dir() and (p / "main.py").exists():
        path, entry = p.resolve(), (p / "main.py").resolve()
    else:
        raise FileNotFoundError(
            f"{target!r} is not an app: expected a directory containing main.py, or a .py file. "
            "Copy apps/_template to start a new one."
        )
    app = App(name=path.name, path=path, entry=entry)
    manifest = path / "app.yaml"
    if manifest.exists():
        data = yaml.safe_load(manifest.read_text()) or {}
        app.needs_base = bool(data.get("needs_base", False))
        app.camera = str(data.get("camera", ""))
        app.scene = str(data.get("scene", app.scene))
        app.duration_s = float(data.get("duration_s", app.duration_s))
        app.interactive = bool(data.get("interactive", False))
    return app
