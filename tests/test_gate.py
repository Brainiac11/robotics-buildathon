"""The sim-check gate, end to end: it starts a private lockstep simulator and runs a tiny app."""

import json

import pytest

pytest.importorskip("mujoco")

from buildathon_cli.apps import find_app  # noqa: E402
from buildathon_cli.simcheck import sim_check  # noqa: E402

GOOD = """
from buildathon import Robot
with Robot.connect() as robot:
    if robot.base_enabled:
        robot.drive(vx=0.2)
        robot.sleep(1.0)
    robot.arm.move_to("ready", tolerance=4)
"""
CRASH = """
from buildathon import Robot
with Robot.connect() as robot:
    robot.sleep(0.5)
    raise ValueError("boom")
"""
OVER_LIMIT = """
from buildathon import Robot
with Robot.connect() as robot:
    robot.arm.set_joints(elbow_flex=170)
    robot.sleep(1.0)
"""
DRIVES_BLIND = """
from buildathon import Robot
with Robot.connect() as robot:
    robot._send({"x.vel": 0.2, "y.vel": 0.0, "theta.vel": 0.0})
    robot.sleep(1.0)
"""
LEAVES_DRIVING = """
from buildathon import Robot
robot = Robot.connect()
robot.drive(vx=0.25)
robot.observe()
"""


def gate(tmp_path, monkeypatch, code, manifest="duration_s: 5\nneeds_base: true\nscene: empty\n", **kw):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text(code)
    (app_dir / "app.yaml").write_text(manifest)
    monkeypatch.chdir(tmp_path)
    code = sim_check(find_app(str(app_dir)), **kw)
    if code == 2:
        pytest.skip("the simulator could not start here (no OpenGL for rendering)")
    return code, json.loads((tmp_path / ".simcheck" / "app.json").read_text())


def test_good_app_passes_and_final_state_is_at_rest(tmp_path, monkeypatch):
    code, report = gate(tmp_path, monkeypatch, GOOD)
    assert code == 0 and report["passed"] and not report["problems"]
    assert abs(report["final_state"]["x.vel"]) < 0.01
    assert report["final_truth"]["x"] > 0.1


def test_crash_fails_and_reports_the_last_output_line(tmp_path, monkeypatch):
    code, report = gate(tmp_path, monkeypatch, CRASH)
    assert code == 1 and "ValueError: boom" in report["problems"][0]


def test_out_of_limit_request_fails(tmp_path, monkeypatch):
    code, report = gate(tmp_path, monkeypatch, OVER_LIMIT)
    assert code == 1 and report["events"]["joint_limit"] >= 1


def test_arm_only_app_that_drives_fails(tmp_path, monkeypatch):
    code, report = gate(tmp_path, monkeypatch, DRIVES_BLIND, manifest="duration_s: 5\nneeds_base: false\n")
    assert code == 1 and report["base_enabled"] is False
    assert report["final_truth"]["x"] == pytest.approx(0, abs=0.005)


def test_app_that_exits_while_driving_is_recorded_at_rest(tmp_path, monkeypatch):
    code, report = gate(tmp_path, monkeypatch, LEAVES_DRIVING)
    assert abs(report["final_state"]["x.vel"]) < 0.01  # the watchdog stopped it during settling
    assert code == 0 and any("watchdog" in w for w in report["warnings"])


SLEEPS_INSTEAD_OF_STEPPING = """
import time
from buildathon import Robot
with Robot.connect() as robot:
    robot.drive(vx=0.1)
    time.sleep(3)
    robot.stop()
"""


def test_app_that_waits_with_time_sleep_gets_a_clear_warning(tmp_path, monkeypatch):
    code, report = gate(tmp_path, monkeypatch, SLEEPS_INSTEAD_OF_STEPPING)
    assert report["simulated_s"] < 0.5
    assert any("time.sleep()" in w for w in report["warnings"])
    assert code == 0  # a warning, not a failure: slow computation looks the same from outside


def test_reset_without_a_seed_matches_the_gate_layout(start_host):
    from buildathon import Robot

    _, address = start_host(backend="sim", lockstep=True)
    with Robot.connect(address, handle_signals=False) as robot:

        def layout(seed):
            robot._rpc({"op": "reset", **({} if seed is None else {"seed": seed})})
            return robot.observe().info["truth"]["objects"]

        assert layout(None) == layout(None)
