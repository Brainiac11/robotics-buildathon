import pytest
from buildathon import protocol as P
from buildathon_host.config import Limits
from buildathon_host.safety import SafetyFilter

DT = 1 / 30


def make():
    f = SafetyFilter(Limits(), DT, watchdog_timeout_s=0.5)
    f.reset(dict.fromkeys(P.ALL_KEYS, 0.0))
    return f


def run(f, seconds, t0=0.0, **kw):
    kw = {"base_active": True, "motion_ok": True, **kw}
    out, t = None, t0
    for _ in range(round(seconds / DT)):
        t += DT
        out = f.tick(t, **kw)
    return out, t


def test_joint_target_is_clamped_and_counted():
    f = make()
    f.accept({"arm_shoulder_pan.pos": 500}, 0.0, True)
    assert f.arm_goal["arm_shoulder_pan.pos"] == 100
    assert f.events["joint_limit"] == 1


def test_arm_speed_is_per_second_not_per_message():
    f = make()
    f.accept({"arm_elbow_flex.pos": 90}, 0.0, True)
    out, _ = run(f, 0.25)
    assert out["arm_elbow_flex.pos"] == pytest.approx(120 * 0.25, rel=0.15)
    out, _ = run(f, 1.0, t0=0.25)
    assert out["arm_elbow_flex.pos"] == 90


def test_base_speed_clamped_and_ramped():
    f = make()
    f.accept({"x.vel": 5.0, "y.vel": 0.0, "theta.vel": 0.0}, 0.0, True)
    assert f.events["base_speed"] == 1
    first = f.tick(DT, base_active=True, motion_ok=True)
    assert 0 < first["x.vel"] <= 0.6 * DT + 1e-9
    f.accept({"x.vel": 5.0}, 0.4, True)
    out, _ = run(f, 0.4, t0=0.4)
    assert out["x.vel"] <= 0.30 + 1e-9


def test_watchdog_stops_base_but_arm_holds():
    f = make()
    f.accept({"x.vel": 0.2, "arm_elbow_flex.pos": 30}, 0.0, True)
    out, t = run(f, 0.45)
    assert out["x.vel"] > 0.1
    out, _ = run(f, 1.5, t0=t)
    assert out["x.vel"] == 0 and out["arm_elbow_flex.pos"] == 30
    assert f.events["watchdog"] == 1


def test_motion_blocked_zeroes_base_immediately_and_freezes_arm():
    f = make()
    f.accept({"x.vel": 0.2, "arm_elbow_flex.pos": 90}, 0.0, True)
    out, t = run(f, 0.3)
    moving_to = out["arm_elbow_flex.pos"]
    out = f.tick(t + DT, base_active=True, motion_ok=False)
    assert out["x.vel"] == 0
    assert out["arm_elbow_flex.pos"] == moving_to
    out, _ = run(f, 1.0, t0=t + DT)  # motion allowed again: nothing resumes without a new command
    assert out["x.vel"] == 0 and out["arm_elbow_flex.pos"] == moving_to


def test_base_disabled_zeroes_drive_and_counts():
    f = make()
    f.accept({"x.vel": 0.2, "y.vel": 0.0, "theta.vel": 30.0}, 0.0, base_active=False)
    out, _ = run(f, 0.3, base_active=False)
    assert (out["x.vel"], out["y.vel"], out["theta.vel"]) == (0, 0, 0)
    assert f.events["base_disabled"] == 1


def test_non_finite_values_are_ignored():
    f = make()
    f.accept({"arm_elbow_flex.pos": float("nan"), "x.vel": float("inf")}, 0.0, True)
    out, _ = run(f, 0.2)
    assert out["arm_elbow_flex.pos"] == 0 and out["x.vel"] == 0
    assert f.events["invalid_value"] == 2


def test_switching_base_off_while_driving_stops_it_at_once():
    f = make()
    f.accept({"x.vel": 0.2, "y.vel": 0.0, "theta.vel": 30.0}, 0.0, base_active=True)
    out, t = run(f, 0.3)
    assert out["x.vel"] > 0.1
    out = f.tick(t + DT, base_active=False, motion_ok=True)  # base switched off mid-drive
    assert (out["x.vel"], out["y.vel"], out["theta.vel"]) == (0, 0, 0)


def test_drive_command_sent_while_base_off_does_not_come_alive_when_switched_on():
    f = make()
    f.accept({"x.vel": 0.2, "y.vel": 0.0, "theta.vel": 0.0}, 0.0, base_active=False)
    out, _ = run(f, 0.3, base_active=True)  # base switched back on within the watchdog window
    assert out["x.vel"] == 0
