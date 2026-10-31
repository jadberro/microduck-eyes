import math

from microduck_eyes.eye.state import EyeState, clamp


def test_pupil_stays_inside_sclera(cfg):
    e = cfg.eye
    for scale in (0.5, 1.0, 1.5):
        s = clamp(EyeState(pupil_x=500, pupil_y=-300, pupil_scale=scale), cfg)
        limit = e.sclera_r - e.outline_w - e.pupil_margin - e.pupil_r * s.pupil_scale
        assert math.hypot(s.pupil_x, s.pupil_y) <= limit + 1e-6


def test_lids_and_tilt_clamped(cfg):
    s = clamp(EyeState(lid_upper=3, lid_lower=-1, lid_tilt=9), cfg)
    assert (s.lid_upper, s.lid_lower, s.lid_tilt) == (1.0, 0.0, 1.0)


def test_small_offset_unchanged(cfg):
    s = clamp(EyeState(pupil_x=10, pupil_y=-5), cfg)
    assert (s.pupil_x, s.pupil_y) == (10, -5)
