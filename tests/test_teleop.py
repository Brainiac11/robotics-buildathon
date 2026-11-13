"""Keyboard teleop logic, against the mock host (no terminal involved)."""

import pytest
from buildathon import Robot
from buildathon_cli.teleop import RELEASE_S, Organizer, Teleop


def connect(address, **kw):
    return Robot.connect(address, handle_signals=False, timeout=3.0, **kw)


def hold(robot, teleop, key, seconds, clock):
    """Press `key` repeatedly for `seconds` of robot time, as a held key does."""
    obs = robot.observe()
    end = obs.t + seconds
    while obs.t < end:
        teleop.handle_key(key, obs, clock[0])
        teleop.tick(clock[0])
        obs = robot.observe()
        clock[0] += 1 / 30
    return obs


def idle(robot, teleop, seconds, clock):
    obs = robot.observe()
    end = obs.t + seconds
    while obs.t < end:
        teleop.tick(clock[0])
        obs = robot.observe()
        clock[0] += 1 / 30
    return obs


def test_base_moves_while_key_held_and_stops_on_release(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        teleop, clock = Teleop(robot, linear=0.1, angular=30), [100.0]
        assert hold(robot, teleop, "w", 1.0, clock).base_velocity[0] == pytest.approx(0.1, abs=0.01)
        obs = idle(robot, teleop, RELEASE_S + 0.6, clock)
        assert obs.base_velocity == (0.0, 0.0, 0.0)
        assert hold(robot, teleop, "a", 1.0, clock).base_velocity[1] == pytest.approx(0.1, abs=0.01)
        assert hold(robot, teleop, "e", 1.0, clock).base_velocity[2] == pytest.approx(-30, abs=2)
        teleop.handle_key(" ", robot.observe(), clock[0])
        assert idle(robot, teleop, 0.6, clock).base_velocity == (0.0, 0.0, 0.0)


def test_arm_keys_jog_from_the_measured_pose_and_respect_limits(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        robot.arm.move_to(shoulder_lift=-40)
        teleop, clock = Teleop(robot, step_deg=5), [0.0]
        obs = robot.observe()
        teleop.handle_key("f", obs, 0.0)  # shoulder lift +5 from where it is, not from zero
        assert robot.sleep(0.5).joints["shoulder_lift"] == pytest.approx(-35, abs=0.5)
        for _ in range(60):  # far past the limit
            teleop.handle_key("c", robot.observe(), 0.0)
        obs = robot.sleep(4.0)
        assert obs.joints["shoulder_pan"] == pytest.approx(100)
        assert not obs.info["events"].get("joint_limit")  # teleop clamps before sending
        teleop.handle_key("o", obs, 0.0)
        assert robot.sleep(0.5).gripper == pytest.approx(10)
        idle(robot, teleop, 0.1, clock)


def test_speed_keys_stay_within_limits_and_arm_only_blocks_driving(start_host):
    _, address = start_host(lockstep=True, no_base=True)
    with connect(address) as robot:
        teleop, clock = Teleop(robot), [0.0]
        for _ in range(50):
            teleop.handle_key("+", robot.observe(), 0.0)
        assert teleop.linear == pytest.approx(robot.limits["max_linear_m_s"])
        obs = hold(robot, teleop, "w", 0.5, clock)  # base is off: no error, no motion
        assert obs.base_velocity[0] == 0 and "arm-only" in teleop.message
        teleop.handle_key("x", obs, 0.0)
        assert teleop.quit


def test_estop_key_latches(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        teleop, clock = Teleop(robot), [0.0]
        teleop.handle_key("p", robot.observe(), 0.0)
        assert hold(robot, teleop, "w", 0.5, clock).estop


def test_organizer_gated_host_moves_only_while_teleop_holds_it(start_host):
    _, address = start_host(lockstep=False, heartbeat_required=True, session_required=True, organizer_token="tok")
    with pytest.raises(Exception, match="organizer token"):
        Organizer(address, "wrong", None).start()
    organizer = Organizer(address, "tok", None)
    session = organizer.start()
    try:
        with connect(address, session=session) as robot:
            robot.drive(vx=0.1)
            assert robot.sleep(0.6).base_velocity[0] > 0.05
            organizer.stop()  # teleop exits: heartbeat stops and the session closes
            robot.drive(vx=0.1)
            obs = robot.sleep(1.5)
            assert obs.base_velocity[0] == 0 and not obs.motion_enabled
    finally:
        organizer.stop()


def test_slot_runs_an_app_on_a_gated_host_and_logs_it(start_host, tmp_path, monkeypatch):
    """The supervisor's `robot slot`, against a host that needs heartbeat + session + token."""
    from buildathon_cli.apps import find_app
    from buildathon_cli.slot import run_slot

    _, address = start_host(lockstep=False, heartbeat_required=True, session_required=True, organizer_token="tok")
    app = tmp_path / "rockets"
    app.mkdir()
    (app / "main.py").write_text(
        "from buildathon import Robot\n"
        "with Robot.connect() as robot:\n"
        "    ok = robot.arm.move_to(shoulder_pan=20, tolerance=3)\n"
        "    print('arrived' if ok else 'BLOCKED', round(robot.observe().joints['shoulder_pan']))\n"
        "    print('limit', robot.limits['max_joint_speed_deg_s'])\n"
    )
    monkeypatch.chdir(tmp_path)
    code = run_slot(find_app(str(app)), host=address, token="tok", skip_check=True, note="looked fine")
    assert code == 0
    output = next((tmp_path / "slots").glob("*-rockets.log")).read_text()
    assert "arrived 20" in output and "limit 60" in output  # it moved, in safe mode (half of 120)
    log = (tmp_path / "slots" / "slot-log.md").read_text()
    assert "| rockets | safe | finished" in log and "looked fine" in log
    with connect(address) as robot:  # afterwards nothing can move the robot
        obs = robot.observe()
        assert not obs.motion_enabled  # the session has ended (and the heartbeat stops within a second)
        assert "stopped_by_organizer" in obs.info["inhibit"]
