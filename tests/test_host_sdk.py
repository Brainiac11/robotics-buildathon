"""SDK <-> host over real sockets, using the mock backend."""

import time

import pytest
from buildathon import BaseDisabledError, Robot, RobotError


def connect(address, **kw):
    return Robot.connect(address, handle_signals=False, timeout=3.0, **kw)


def test_lockstep_drive_and_observe(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        assert robot.lockstep and robot.mode == "mock"
        first = robot.observe()
        assert first.cameras == ["camera"] and first.image().shape == (480, 640, 3)
        robot.drive(vx=0.2)
        obs = robot.sleep(2.0)
        assert obs.t == pytest.approx(first.t + 2.0, abs=0.1)
        assert obs.odom[0] == pytest.approx(0.2 * 2.0, rel=0.15)  # minus the acceleration ramp
        robot.stop()
        assert robot.sleep(1.0).base_velocity == (0.0, 0.0, 0.0)


def test_lockstep_is_deterministic(start_host):
    def one_run():
        _, address = start_host(lockstep=True)
        with connect(address) as robot:
            robot.drive(vx=0.1, wz=20)
            robot.arm.set_joints(elbow_flex=40)
            return robot.sleep(1.5).info["state"], robot.observe().odom

    assert one_run() == one_run()


def test_drive_expires_without_refresh(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        robot.drive(vx=0.2)
        for _ in range(45):  # 1.5 s of plain observing: nothing refreshes the drive command
            obs = robot.observe()
        assert obs.base_velocity[0] == 0
        assert obs.info["events"].get("watchdog") == 1


def test_arm_move_to_named_pose(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        assert robot.arm.move_to("ready") is True
        joints = robot.observe().joints
        assert joints["shoulder_lift"] == pytest.approx(-30) and joints["elbow_flex"] == pytest.approx(40)
        with pytest.raises(KeyError):
            robot.arm.pose("no-such-pose")
        with pytest.raises(KeyError, match="available: home"):
            robot.arm.move_to("no-such-pose")
        with pytest.raises(ValueError):
            robot.send_action({"arm_elbow.pos": 1})


def test_arm_only_mode_blocks_driving(start_host):
    host, address = start_host(lockstep=True, no_base=True)
    with connect(address) as robot:
        assert robot.base_enabled is False
        with pytest.raises(BaseDisabledError):
            robot.drive(vx=0.1)
        robot.arm.set_joints(elbow_flex=20)  # the arm still works
        assert robot.sleep(1.0).joints["elbow_flex"] == pytest.approx(20)
        # Even a client that bypasses the SDK check cannot move the base.
        robot._send({"x.vel": 0.2, "y.vel": 0.0, "theta.vel": 0.0})
        obs = robot.sleep(0.5)
        assert obs.base_velocity == (0.0, 0.0, 0.0) and obs.odom[0] == 0
        assert obs.info["events"]["base_disabled"] >= 1


def test_base_can_be_switched_at_run_time(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        robot._rpc({"op": "set_base", "enabled": False})
        assert robot.observe().base_enabled is False
        with pytest.raises(BaseDisabledError):
            robot.drive(vx=0.1)
        robot._rpc({"op": "set_base", "enabled": True})
        robot.observe()
        robot.drive(vx=0.1)
        assert robot.sleep(1.0).odom[0] > 0.05


def test_no_wheels_fitted_cannot_be_enabled(start_host):
    _, address = start_host(lockstep=True, base_present=False)
    with connect(address) as robot:
        assert robot.base_enabled is False
        with pytest.raises(RobotError, match="no wheels"):
            robot._rpc({"op": "set_base", "enabled": True})


def test_estop_latches_until_cleared(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        robot.drive(vx=0.2)
        robot.sleep(1.0)
        robot.estop()
        obs = robot.observe()
        assert obs.estop and not obs.motion_enabled and obs.base_velocity[0] == 0
        robot.drive(vx=0.2)
        assert robot.sleep(0.5).base_velocity[0] == 0
        robot._rpc({"op": "clear_estop"})
        robot.drive(vx=0.2)
        assert robot.sleep(1.0).base_velocity[0] > 0.1


def test_organizer_ops_need_the_token(start_host):
    _, address = start_host(lockstep=True, organizer_token="secret")
    with connect(address) as robot:
        robot.estop()  # anyone may stop
        with pytest.raises(RobotError, match="organizer token"):
            robot._rpc({"op": "clear_estop"})
        with pytest.raises(RobotError, match="organizer token"):
            robot._rpc({"op": "set_base", "enabled": False, "token": "wrong"})
        robot._rpc({"op": "clear_estop", "token": "secret"})


def test_session_gates_commands_and_expires(start_host):
    _, address = start_host(lockstep=True, session_required=True)
    with connect(address) as robot:  # no session id
        assert robot.observe().info["inhibit"] == ["no_active_session"]
        reply, _ = robot._rpc({"op": "session_start", "session": "team-a", "max_runtime_s": 2.0})
        assert reply["session"] == "team-a"
        robot.drive(vx=0.2)  # wrong (empty) session id: ignored
        assert robot.sleep(0.5).base_velocity[0] == 0
    with connect(address, session="team-a") as robot:
        robot.drive(vx=0.2)
        assert robot.sleep(1.0).base_velocity[0] > 0.1
        obs = robot.sleep(2.0)  # past the 2 s limit
        assert obs.base_velocity[0] == 0 and "session_time_limit" in obs.info["inhibit"]


def test_heartbeat_required_blocks_motion_until_sent(start_host):
    _, address = start_host(lockstep=True, heartbeat_required=True)
    with connect(address) as robot:
        robot.drive(vx=0.2)
        obs = robot.sleep(0.5)
        assert obs.base_velocity[0] == 0 and obs.info["inhibit"] == ["no_organizer_heartbeat"]
        robot._rpc({"op": "heartbeat"})
        robot.drive(vx=0.2)
        assert robot.sleep(0.5).base_velocity[0] > 0


def test_realtime_mode_streams_and_watchdog_stops(start_host):
    _, address = start_host(lockstep=False)
    with connect(address) as robot:
        assert not robot.lockstep
        a = robot.observe()
        b = robot.observe()
        assert b.seq > a.seq and b.cameras == ["camera"]
        robot.drive(vx=0.2)
        assert robot.sleep(0.6).base_velocity[0] > 0.1
        time.sleep(1.0)  # the app "hangs": no commands
        assert robot.observe().base_velocity[0] == 0


def test_switching_base_off_mid_drive_stops_the_robot(start_host):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        robot.drive(vx=0.2)
        assert robot.sleep(1.0).base_velocity[0] > 0.1
        robot._rpc({"op": "set_base", "enabled": False})
        x_before = robot.observe().odom[0]
        robot._send({"x.vel": 0.2, "y.vel": 0.0, "theta.vel": 0.0})  # a client ignoring the SDK check
        obs = robot.sleep(0.5)
        assert obs.base_velocity == (0.0, 0.0, 0.0)
        assert obs.odom[0] == pytest.approx(x_before, abs=0.01)


def test_malformed_messages_do_not_stop_the_host(start_host):
    import zmq

    host, address = start_host(lockstep=False)
    port = int(address.split(":")[1])
    ctx = zmq.Context.instance()
    push = ctx.socket(zmq.PUSH)
    push.connect(f"tcp://localhost:{port + 1}")
    for raw in [
        b"\xff\xfe",
        b"[1,2,3]",
        b'"text"',
        b"null",
        b"5",
        b"{}",
        b'{"action": 5}',
        b'{"action": {"x.vel": null, "bogus": [1]}}',
    ]:
        push.send(raw)
    req = ctx.socket(zmq.REQ)
    req.setsockopt(zmq.RCVTIMEO, 2000)
    req.connect(f"tcp://localhost:{port + 2}")
    for raw in [
        b"\xff",
        b"[]",
        b"null",
        b'"x"',
        b"{}",
        b'{"op": 5}',
        b'{"op": "set_base"}',
        b'{"op": "session_start", "max_runtime_s": "x"}',
    ]:
        req.send(raw)
        assert b'"ok":false' in req.recv_multipart()[0]
    push.close(linger=0)
    req.close(linger=0)
    time.sleep(0.3)
    with connect(address) as robot:  # still alive, still controllable, base still on
        assert robot.base_enabled
        robot.drive(vx=0.2)
        assert robot.sleep(0.6).base_velocity[0] > 0.1
    assert host.stats["rejected"] >= 7


def test_safe_mode_slows_an_honest_request_without_counting_it_as_a_violation(start_host):
    _, address = start_host(lockstep=True, safe_mode=True)
    with connect(address) as robot:
        assert robot.limits["max_linear_m_s"] == pytest.approx(0.15)  # the limits reported are the active ones
        robot.drive(vx=0.25)  # legal at full speed, above the safe-mode limit
        obs = robot.sleep(1.5)
        assert obs.base_velocity[0] == pytest.approx(0.15, abs=0.005)
        assert not obs.info["events"].get("base_speed")
        robot.drive(vx=0.6)  # beyond the robot's real limit: that is still an app bug
        assert robot.sleep(0.3).info["events"]["base_speed"] >= 1


def test_gripper_wait_returns_when_the_jaws_arrive(start_host):
    _, address = start_host(lockstep=True, safe_mode=True)  # safe mode: full travel takes a second
    with connect(address) as robot:
        t0 = robot.observe().t
        assert robot.gripper.open(wait=True) is True
        obs = robot.observe()
        assert obs.gripper >= 97 and 0.8 < obs.t - t0 < 2.0
        assert robot.gripper.set(40, wait=True) is True
        assert robot.observe().gripper == pytest.approx(40, abs=3)


def test_blocked_motion_is_reported_once(start_host, capsys):
    _, address = start_host(lockstep=True)
    with connect(address) as robot:
        robot.drive(vx=0.1)
        robot.sleep(0.3)
        assert "not moving" not in capsys.readouterr().err
        robot.estop()
        robot.observe()
        for _ in range(5):
            robot.drive(vx=0.1)
            robot.observe()
        err = capsys.readouterr().err
        assert err.count("motion is blocked (estop)") == 1
        robot._rpc({"op": "clear_estop"})
        robot.observe()
        robot.drive(vx=0.1)
        robot.sleep(0.3)
        assert "not moving" not in capsys.readouterr().err
