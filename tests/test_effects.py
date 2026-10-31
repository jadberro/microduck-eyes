import numpy as np

from microduck_eyes.display import effects


def test_rgb565_round_trip_is_close_and_idempotent():
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    q = effects.rgb565_quantize(frame)
    assert np.abs(q.astype(int) - frame.astype(int)).max() <= 8
    assert np.array_equal(effects.rgb565_quantize(q), q)


def test_rgb565_bytes_pack_known_colours():
    frame = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], np.uint8)
    assert effects.to_rgb565_bytes(frame) == bytes.fromhex("f800 07e0 001f ffff")


def test_orient_rect_matches_orient():
    size = 10
    frame = np.zeros((size, size, 3), np.uint8)
    frame[1:3, 2:5] = 255
    rect = (2, 1, 5, 3)
    for rot, mir in ((True, False), (False, True), (True, True)):
        out = effects.orient(frame, rot, mir)
        x0, y0, x1, y1 = effects.orient_rect(rect, size, rot, mir)
        ys, xs = np.nonzero(out[..., 0])
        assert ys.min() == y0 and ys.max() == y1 - 1 and xs.min() == x0 and xs.max() == x1 - 1
