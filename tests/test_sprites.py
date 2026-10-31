import math

import numpy as np

from microduck_eyes.eye import sprites


def test_disc_area_matches_circle():
    for r in (5, 20, 46, 106):
        area = sprites.disc(r).sum()
        assert abs(area - math.pi * r * r) / (math.pi * r * r) < 0.02


def test_disc_is_symmetric():
    m = sprites.disc(30)
    assert np.allclose(m, m[::-1]) and np.allclose(m, m[:, ::-1])


def test_lid_masks_cover_expected_region(cfg):
    e = cfg.eye
    lids = sprites.LidMasks(240, e.sclera_r, e.outline_w, e.lid_curve, e.lid_edge_w, e.lid_meet_y)
    a_open, _, _ = lids.get("upper", 0.0, 0.0)
    assert a_open.sum() < 50            # open lid barely touches the eye
    a_closed, _, row0 = lids.get("upper", 1.0, 0.0)
    lo_closed, _, lrow0 = lids.get("lower", 1.0, 0.0)
    # Closed upper + lower lids together cover the whole sclera.
    full = np.zeros((240, 240), np.float32)
    full[row0:row0 + a_closed.shape[0]] += a_closed
    full[lrow0:lrow0 + lo_closed.shape[0]] += lo_closed
    disc = sprites.disc(e.sclera_r)
    half = disc.shape[0] // 2
    c = 120
    covered = full[c - half:c + half + 1, c - half:c + half + 1]
    assert np.all(covered[disc > 0.5] > 0.95)


def test_blend_returns_clipped_bbox():
    frame = np.zeros((50, 50, 3), np.uint8)
    rect = sprites.blend(frame, -5, 40, np.ones((20, 20), np.float32), (255, 0, 0))
    assert rect == (0, 40, 15, 50)
    assert frame[45, 5].tolist() == [255, 0, 0]
    assert frame[30, 5].tolist() == [0, 0, 0]
