import numpy as np

from microduck_eyes.eye.animator import Animator
from microduck_eyes.eye.expressions import ORDER
from microduck_eyes.eye.renderer import EyeRenderer
from microduck_eyes.eye.state import EyeState


def test_all_presets_render(cfg):
    r = EyeRenderer(cfg, "left")
    anim = Animator(cfg, 0.0, seed=0)
    for name in ORDER:
        anim.set_expression(name, 0.0, dur_ms=0)
        left, _, _ = anim.update(0.0)
        frame, dirty = r.render(left)
        assert frame.shape == (240, 240, 3) and frame.dtype == np.uint8
        assert dirty[2] > dirty[0] and dirty[3] > dirty[1]


def test_dirty_rect_contains_every_changed_pixel(cfg):
    r = EyeRenderer(cfg, "right")
    prev, _ = r.render(EyeState())
    prev = prev.copy()
    cases = [
        EyeState(pupil_x=30, pupil_y=-10),
        EyeState(pupil_x=-25, pupil_y=20, pupil_scale=0.8),
        EyeState(lid_upper=0.5),
        EyeState(lid_upper=0.2, lid_lower=0.4, lid_tilt=0.3),
        EyeState(),
    ]
    for state in cases:
        frame, (x0, y0, x1, y1) = r.render(state)
        changed = np.any(frame != prev, axis=2)
        ys, xs = np.nonzero(changed)
        if len(ys):
            assert ys.min() >= y0 and ys.max() < y1
            assert xs.min() >= x0 and xs.max() < x1
        prev = frame.copy()


def test_closed_eye_shows_no_white(cfg):
    r = EyeRenderer(cfg, "left")
    frame, _ = r.render(EyeState(lid_upper=1.0, lid_lower=1.0))
    white = np.all(frame == 255, axis=2)
    assert white.sum() == 0


def test_corners_are_face_colour(cfg):
    r = EyeRenderer(cfg, "left")
    frame, _ = r.render(EyeState(pupil_x=40, lid_upper=0.3))
    for y, x in ((0, 0), (0, 239), (239, 0), (239, 239)):
        assert tuple(frame[y, x]) == cfg.colours.face
