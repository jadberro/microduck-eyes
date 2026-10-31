"""Budget gates. Generous on CI machines; the Radxa is measured separately in Phase 6."""
import time

from microduck_eyes.display import effects
from microduck_eyes.eye.renderer import EyeRenderer
from microduck_eyes.eye.state import EyeState


def _best_ms(fn, n=30):
    best = 1e9
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - t0) * 1000.0)
    return best


def test_renderer_setup_is_fast(cfg):
    assert _best_ms(lambda: EyeRenderer(cfg, "left"), n=3) < 200


def test_full_render_under_budget(cfg):
    r = EyeRenderer(cfg, "left")
    r.render(EyeState(lid_upper=0.3))
    state = EyeState(pupil_x=20, pupil_y=5, lid_upper=0.3)
    assert _best_ms(lambda: r.render(state)) < 3.0


def test_pupil_update_bytes_under_budget(cfg):
    r = EyeRenderer(cfg, "left")
    r.render(EyeState(pupil_x=0))
    _, (x0, y0, x1, y1) = r.render(EyeState(pupil_x=3))
    assert (x1 - x0) * (y1 - y0) * 2 < 40_000   # bytes over SPI for a small pupil move (iris included)


def test_rgb565_pack_is_fast(cfg):
    r = EyeRenderer(cfg, "left")
    frame, _ = r.render(EyeState())
    assert _best_ms(lambda: effects.to_rgb565_bytes(frame)) < 3.0
