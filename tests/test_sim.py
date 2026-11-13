"""Physics smoke tests for the MuJoCo backend (no rendering, so no GPU or display needed)."""

import pytest

pytest.importorskip("mujoco")

from buildathon import Robot


def test_sim_drives_and_moves_arm(start_host):
    _, address = start_host(backend="sim", lockstep=True)
    with Robot.connect(address, handle_signals=False) as robot:
        assert robot.mode == "sim"
        start = robot.observe()
        assert start.joints["shoulder_lift"] == pytest.approx(-90, abs=3)  # starts in the home pose
        robot.drive(vx=0.2)
        obs = robot.sleep(2.0)
        truth = obs.info["truth"]
        assert truth["x"] == pytest.approx(0.2 * 2.0, rel=0.2)
        assert obs.odom[0] == pytest.approx(truth["x"], abs=0.02)  # odometry agrees with ground truth
        robot.stop()
        assert robot.arm.move_to("ready", tolerance=4) is True


def test_sim_strafes_and_turns(start_host):
    _, address = start_host(backend="sim", lockstep=True)
    with Robot.connect(address, handle_signals=False) as robot:
        robot.drive(vy=0.15)
        obs = robot.sleep(1.5)
        assert obs.info["truth"]["y"] > 0.12 and abs(obs.info["truth"]["x"]) < 0.02
        robot.drive(wz=45)
        obs = robot.sleep(2.0)
        assert obs.info["truth"]["theta"] == pytest.approx(90, abs=15)


def test_sim_arm_only_stays_put(start_host):
    _, address = start_host(backend="sim", lockstep=True, no_base=True)
    with Robot.connect(address, handle_signals=False) as robot:
        robot._send({"x.vel": 0.2, "y.vel": 0.0, "theta.vel": 0.0})
        robot.arm.set_joints(shoulder_pan=40)
        obs = robot.sleep(1.5)
        assert abs(obs.info["truth"]["x"]) < 0.005
        assert obs.joints["shoulder_pan"] == pytest.approx(40, abs=4)
