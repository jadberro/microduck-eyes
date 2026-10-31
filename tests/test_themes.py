import numpy as np
import pytest

from microduck_eyes.eye import pupil_sprites
from microduck_eyes.eye.animator import Animator
from microduck_eyes.eye.font import text_mask, text_size
from microduck_eyes.eye.renderer import EyeRenderer
from microduck_eyes.eye.scenes import SceneRenderer
from microduck_eyes.eye.state import EyeState
from microduck_eyes.eye.themes import REGISTRY, THEMES, ThemeController


def test_pupil_sprites_have_sensible_area():
    r = 46.0
    d = pupil_sprites.dollar(r, 0).sum()
    h = pupil_sprites.heart(r).sum()
    disc, band = pupil_sprites.spiral(r, 3)
    assert 0.15 * np.pi * r * r < d < 0.6 * np.pi * r * r
    assert 0.6 * np.pi * r * r < h < 1.6 * np.pi * r * r
    assert 0.3 < band.sum() / disc.sum() < 0.6
    assert pupil_sprites.dollar(r, 2).sum() < d


@pytest.mark.parametrize("name", sorted(pupil_sprites.FRAMES))
def test_every_pupil_sprite_builds_and_draws_something(name, cfg):
    if name == "disc":
        return
    for frame in range(pupil_sprites.FRAMES[name]):
        layers = pupil_sprites.layers(name, frame, 50.0)
        assert layers
        total = sum(float(a.sum()) for a, _ in layers)
        assert total > 20, f"{name} frame {frame} is empty"
        for alpha, colour in layers:
            assert alpha.dtype == np.float32 and alpha.ndim == 2
            assert 0.0 <= alpha.min() and alpha.max() <= 1.0 + 1e-6
            assert len(colour) == 3


def test_font_renders_known_glyphs():
    m = text_mask("A", 1)
    assert m.shape == (7, 5) and m[0, 2] == 1.0 and m[3].sum() == 5
    assert text_size("HELLO", 2) == (2 * (5 * 5 + 4), 14)
    assert text_mask("ab", 3).shape == (21, 33)


def test_renderer_draws_each_pupil_sprite(cfg):
    r = EyeRenderer(cfg, "left")
    base, _ = r.render(EyeState())
    base = base.copy()
    for name in ("dollar", "heart", "spiral", "duck", "eightball", "battery"):
        frame, dirty = r.render(EyeState(pupil_sprite=name, pupil_scale=1.2))
        assert np.any(frame != base)
        assert dirty[2] > dirty[0]


def test_overlays_are_inside_dirty_rect(cfg):
    r = EyeRenderer(cfg, "left")
    prev, _ = r.render(EyeState())
    prev = prev.copy()
    mask = pupil_sprites.heart(8.0)
    frame, (x0, y0, x1, y1) = r.render(EyeState(), overlays=[(mask, pupil_sprites.RED, 20, 30)])
    ys, xs = np.nonzero(np.any(frame != prev, axis=2))
    assert ys.min() >= y0 and ys.max() < y1 and xs.min() >= x0 and xs.max() < x1


def test_scenes_render(cfg):
    sc = SceneRenderer(cfg)
    f0, _ = sc.hal(0)
    f4, _ = sc.hal(4)
    assert f0[120, 120, 0] > 200 and f0[5, 5].max() == 0
    assert f4[120, 60, 0] > f0[120, 60, 0]
    source = np.full((240, 240, 3), 180, np.uint8)
    n = sc.prepare_crt(source)
    assert n >= 10 and np.array_equal(sc.crt(0)[0], source) and sc.crt(n - 1)[0].max() == 0
    for name, frame, extra in (("terminator", 3, (10, -5)), ("pirate", 0, ()), ("bsod", 5, ()), ("boot", 2, (0,)),
                               ("boot", 12, (1,)), ("eve", 0, (0.2, 0.1))):
        f, dirty = sc.render(name, frame, extra)
        assert f.shape == (240, 240, 3) and f.dtype == np.uint8 and f.max() > 0
    base = np.full((240, 240, 3), 200, np.uint8)
    open_ = sc.render("aperture", 0, (), base=base)[0].copy()     # the scene reuses its buffer
    closed = sc.render("aperture", 11, (), base=base)[0].copy()
    assert open_[120, 120].tolist() == [200, 200, 200]          # fully open shows the eye
    assert closed[120, 120].tolist() != [200, 200, 200]         # fully closed hides it


@pytest.mark.parametrize("name", THEMES)
def test_every_theme_runs_renders_and_times_out(name, cfg):
    anim = Animator(cfg, 0.0, seed=0)
    anim.set_idle(False, 0.0)
    scenes = SceneRenderer(cfg)
    renderers = [EyeRenderer(cfg, "left"), EyeRenderer(cfg, "right")]
    tc = ThemeController(cfg, seed=1, anim=anim, scenes=scenes)
    l, r, _ = anim.update(0.0)
    sources = [renderers[0].render(l)[0].copy(), renderers[1].render(r)[0].copy()]
    hold = REGISTRY[name].hold
    tc.start(name, 10.0, sources=sources, params={"level": 40} if name == "battery" else None)
    assert tc.active == name and tc.needs_full_redraw
    tc.needs_full_redraw = False
    drew = 0
    for t in np.linspace(10.0, 10.0 + hold - 0.05, 24):
        sl, sr, changed = tc.apply(float(t), l, r)
        for i, spec in enumerate((sl, sr)):
            if spec.scene is not None and not spec.over_eye:
                frame, dirty = scenes.render(*spec.scene)
            elif spec.scene is not None:
                base, _ = renderers[i].render(spec.state, spec.overlays)
                frame, dirty = scenes.render(*spec.scene, base=base)
            else:
                frame, dirty = renderers[i].render(spec.state, spec.overlays)
            assert frame.shape == (240, 240, 3) and frame.dtype == np.uint8
            assert dirty[2] >= dirty[0] and dirty[3] >= dirty[1]
        drew += changed
    assert drew >= 1
    tc.apply(10.0 + hold + 0.1, l, r)
    assert tc.active is None and tc.needs_full_redraw
    assert anim.blinks_enabled is True and anim.blink_interval is None   # restored after the theme


def test_theme_quiet_when_static(cfg):
    tc = ThemeController(cfg, seed=0)
    s = EyeState()
    tc.start("pirate", 0.0)
    tc.needs_full_redraw = False
    tc.apply(1.0, s, s)
    assert tc.apply(1.1, s, s)[2] is False
    assert tc.animating(1.1) is False
    assert tc.next_wake(1.1) == tc.ends_at


def test_filibuster_cancels_on_input(cfg):
    tc = ThemeController(cfg, seed=0)
    tc.start("filibuster", 0.0)
    tc.on_input(1.0)
    assert tc.active is None
    tc.start("hal", 2.0)
    tc.on_input(3.0)
    assert tc.active == "hal"


def test_surprise_mode_fires(cfg):
    tc = ThemeController(cfg, seed=2)
    s = EyeState()
    tc.set_surprise(True, 0.0, interval_s=10.0)
    tc.apply(0.0, s, s)
    assert tc.active is None
    tc.apply(16.0, s, s)
    assert tc.active in THEMES


def test_googly_reacts_to_impulse(cfg):
    tc = ThemeController(cfg, seed=0)
    s = EyeState()
    tc.start("googly", 0.0)
    a = tc.apply(0.02, s, s)[0].state
    tc.impulse(900, 0)                          # a hard shove to the right
    b = tc.apply(0.04, s, s)[0].state
    assert b.pupil_x > a.pupil_x + 5
