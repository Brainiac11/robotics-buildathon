import numpy as np
import pytest
from buildathon_host.kinematics import STEPS_PER_DEG, BaseKinematics


def lekiwi_matrix(base_radius=0.125):
    """The matrix from lerobot v0.7.0 LeKiwi._body_to_wheel_raw (left, back, right)."""
    angles = np.radians(np.array([240, 0, 120]) - 90)
    return np.array([[np.cos(a), np.sin(a), base_radius] for a in angles])


def default_kin(**kw):
    args = dict(wheel_radius_m=0.05, base_radius_m=0.125, wheel_positions_deg=[60, 180, -60])
    args.update(kw)
    return BaseKinematics(**args)


def test_default_geometry_matches_lekiwi():
    assert np.allclose(default_kin().matrix, lekiwi_matrix(), atol=1e-12)


@pytest.mark.parametrize("body", [(0.1, 0, 0), (0, 0.1, 0), (0, 0, 45), (0.07, -0.05, 20)])
def test_raw_commands_match_lekiwi(body):
    vx, vy, wz = body
    surface = lekiwi_matrix() @ np.array([vx, vy, np.radians(wz)])
    expected = [int(round(np.degrees(s / 0.05) * STEPS_PER_DEG)) for s in surface]
    assert default_kin().body_to_wheel_raw(vx, vy, wz) == expected


def test_round_trip():
    kin = default_kin()
    body = (0.12, -0.04, 25.0)
    assert np.allclose(kin.wheel_degps_to_body(kin.body_to_wheel_degps(*body)), body, atol=1e-9)


def test_saturation_scales_all_wheels_together():
    kin = default_kin(max_wheel_raw=1000)
    degps = kin.body_to_wheel_degps(1.0, 0.0, 0.0)
    assert np.max(np.abs(degps)) * STEPS_PER_DEG == pytest.approx(1000)
    vx, vy, wz = kin.wheel_degps_to_body(degps)
    assert vy == pytest.approx(0, abs=1e-9) and wz == pytest.approx(0, abs=1e-9) and 0 < vx < 1.0


def test_reversed_wheel_sign_round_trips():
    kin = default_kin(wheel_direction=[1, -1, 1])
    body = (0.1, 0.05, 10.0)
    assert np.allclose(kin.wheel_degps_to_body(kin.body_to_wheel_degps(*body)), body, atol=1e-9)
    assert kin.body_to_wheel_degps(0, 0.1, 0)[1] == -default_kin().body_to_wheel_degps(0, 0.1, 0)[1]


def test_mecanum_rollers_still_holonomic():
    kin = default_kin(roller_angle_deg=[45, 45, 45])
    body = (0.1, 0.05, 10.0)
    assert np.allclose(kin.wheel_degps_to_body(kin.body_to_wheel_degps(*body)), body, atol=1e-9)


def test_singular_layout_is_rejected():
    with pytest.raises(ValueError, match="cannot move in every direction"):
        default_kin(wheel_positions_deg=[0, 180, 0], roller_angle_deg=[0, 0, 0], base_radius_m=0.0)
