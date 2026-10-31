import numpy as np
import pytest

from microduck_eyes.behaviour import Behaviour
from microduck_eyes.eye.animator import Animator
from microduck_eyes.eye.renderer import EyeRenderer
from microduck_eyes.eye.scenes import SceneRenderer
from microduck_eyes.eye.state import EyeState
from microduck_eyes.eye.themes import GAMES, GLANCES, ThemeController
from microduck_eyes.sensors import SensorHub


def make(cfg, now=0.0, seed=0):
    anim = Animator(cfg, now, seed=seed)
    anim.set_idle(False, now)
    anim.next_blink_at = 1e9
    hub = SensorHub()
    hub.set(now, hour=14.0)                       # daytime, so circadian effects stay out of the way
    beh = Behaviour(cfg, anim, hub, now, seed=seed)
    return anim, hub, beh


def run(anim, beh, t0, t1, step=1 / 30):
    l = r = None
    for t in np.arange(t0, t1, step):
        beh.update(float(t))
        l, r, _ = anim.update(float(t))
        l, r, _, _ = beh.modify(float(t), l, r)
    return l, r


def test_sensor_hub_emits_transition_events():
    hub = SensorHub(low_battery=15)
    hub.set(1.0, touch=True)
    hub.set(2.0, touch=False)
    hub.set(3.0, battery=10.0)
    hub.set(4.0, wifi=0)
    hub.set(5.0, camera_covered=True)
    kinds = [e.kind for e in hub.events]
    assert kinds == ["touch_start", "touch_end", "battery_low", "wifi_lost", "covered"]
    hub.face(6.0, 10, 20, 300)
    assert hub.last("face_found") is not None and hub.state.face.z_mm == 300
    hub.integrate(6.0)
    hub.integrate(9.0)                             # face not seen for a while -> lost
    assert hub.state.face is None and hub.last("face_lost") is not None


def test_pupils_adapt_to_light(cfg):
    anim, hub, beh = make(cfg)
    hub.set(0.0, light=0.0)
    l_dark, _ = run(anim, beh, 0.0, 4.0)
    hub.set(4.0, light=1.0)
    l_bright, _ = run(anim, beh, 4.0, 8.0)
    assert l_dark.pupil_scale > 1.15 and l_bright.pupil_scale < 0.9


def test_startle_dilates_and_blinks(cfg):
    anim, hub, beh = make(cfg)
    run(anim, beh, 0.0, 1.0)
    base = anim.update(1.0)[0]
    beh.sound("loud", 1.0)
    l, _ = run(anim, beh, 1.0, 1.4)
    assert l.pupil_scale > base.pupil_scale and anim.blink_t0 >= 1.0


def test_vestibular_counter_rotation_and_recentre(cfg):
    anim, hub, beh = make(cfg)
    hub.set(0.0, head_yaw_rate=90.0)              # head turns right
    l, _ = run(anim, beh, 0.0, 0.5)
    assert l.pupil_x < -5                          # eyes swing left to hold the gaze
    hub.set(0.5, head_yaw_rate=0.0)
    l, _ = run(anim, beh, 0.5, 3.0)
    assert abs(l.pupil_x) <= 1                     # recentred


def test_eye_contact_with_face_and_glance_away(cfg):
    anim, hub, beh = make(cfg)
    hub.face(0.0, 150.0, 0.0, 300.0)
    l, r = run(anim, beh, 0.0, 1.0)
    assert beh.attention == "track" and l.pupil_x > 10 and r.pupil_x > 10
    glanced = False
    for t in np.arange(1.0, 12.0, 1 / 30):
        hub.face(float(t), 150.0, 0.0, 300.0)
        beh.update(float(t))
        if beh.glance_away_until > t:
            glanced = True
        anim.update(float(t))
    assert glanced


def test_attention_glances_at_motion_then_returns(cfg):
    anim, hub, beh = make(cfg, seed=5)
    run(anim, beh, 0.0, 0.5)
    hub.event("motion", 0.5, dx=0.8, dy=0.0, magnitude=0.2)   # small, uninteresting motion
    beh.rng.random = lambda: 0.99                              # force "not interesting"
    states = []
    for t in np.arange(0.5, 3.0, 1 / 30):
        beh.update(float(t))
        states.append(beh.attention)
    assert "glance" in states and "evaluate" in states and states[-1] == "idle"


def test_speech_cues_and_thinking_look(cfg):
    anim, hub, beh = make(cfg)
    beh.speak("Hello there! I am Microduck", 0.0)
    assert hub.state.speaking and len(beh.syllables) >= 6
    l, _ = run(anim, beh, 0.0, 0.5)                # thinking phase first
    assert l.pupil_x < -10 and l.pupil_y < -10
    squeezed = False
    for t in np.arange(0.8, 3.5, 1 / 60):
        beh.update(float(t))
        l, r, _ = anim.update(float(t))
        l, r, _, _ = beh.modify(float(t), l, r)
        if l.lid_upper > 0.02:
            squeezed = True
    assert squeezed
    run(anim, beh, 3.5, 5.0)
    assert not hub.state.speaking


def test_mood_ring_warms_iris_and_decays(cfg):
    anim, hub, beh = make(cfg)
    hub.set(0.0, touch=True)
    l, _ = run(anim, beh, 0.0, 6.0)
    assert beh.mood > 0.8 and l.iris_colour is not None and l.iris_colour != tuple(cfg.iris.colour)
    hub.set(6.0, touch=False)
    run(anim, beh, 6.0, 60.0, step=0.1)
    assert beh.mood < 0.1


def test_tears_pool_when_sad(cfg):
    anim, hub, beh = make(cfg)
    anim.set_expression("sad", 0.0, dur_ms=0)
    beh.set_expression_name("sad", 0.0)
    seen = False
    for t in np.arange(0.0, 5.0, 1 / 15):
        beh.update(float(t))
        l, r, _ = anim.update(float(t))
        _, _, ol, orr = beh.modify(float(t), l, r)
        if ol or orr:
            seen = True
    assert seen


def test_circadian_phases_and_brightness(cfg):
    anim, hub, beh = make(cfg)
    hub.set(0.0, hour=1.0)                         # night
    l, _ = run(anim, beh, 0.0, 2.0)
    assert beh.phase == "night" and l.lid_upper == 1.0 and beh.brightness < 0.7
    hub.set(2.0, hour=7.0)                         # morning -> a stretch (yawn) is requested
    run(anim, beh, 2.0, 3.0)
    assert any(r.theme == "yawn" for r in beh.requests)
    hub.set(3.0, hour=21.0)
    l, _ = run(anim, beh, 3.0, 4.0)
    assert beh.phase == "evening" and l.lid_upper > 0.05


def test_status_glances_are_requested(cfg):
    anim, hub, beh = make(cfg)
    run(anim, beh, 0.0, 0.2)
    hub.set(0.2, battery=10.0)
    hub.set(0.3, wifi=0)
    hub.set(0.4, listening=True)
    run(anim, beh, 0.2, 0.6)
    names = [r.theme for r in beh.requests]
    assert "battery" in names and "wifi" in names and "listening" in names


@pytest.mark.parametrize("name", GLANCES + GAMES + ["yawn", "flash"])
def test_glances_and_games_render(name, cfg):
    anim, hub, beh = make(cfg)
    hub.set(0.0, battery=42.0, wifi=2, weather="rain", heading=90.0, sound=0.5)
    scenes = SceneRenderer(cfg)
    renderers = [EyeRenderer(cfg, "left"), EyeRenderer(cfg, "right")]
    tc = ThemeController(cfg, seed=0, anim=anim, scenes=scenes, hub=hub)
    tc.start(name, 10.0, params={"level": 42} if name == "battery" else None)
    s = EyeState()
    for t in np.linspace(10.0, 13.0, 12):
        if name == "peekaboo" and 11.0 < t < 11.3:
            hub.set(float(t), camera_covered=True)
        if name == "peekaboo" and t > 12.0 and hub.state.camera_covered:
            hub.set(float(t), camera_covered=False)
        if name == "followdot":
            hub.face(float(t), -160.0, 0.0, 300.0)
        sl, sr, _ = tc.apply(float(t), s, s)
        for i, spec in enumerate((sl, sr)):
            frame, _ = renderers[i].render(spec.state, spec.overlays)
            assert frame.shape == (240, 240, 3)
    tc.stop(14.0)
    assert anim.blinks_enabled


def test_followdot_rewards_when_face_reaches_target(cfg):
    anim, hub, beh = make(cfg)
    tc = ThemeController(cfg, seed=0, anim=anim, hub=hub)
    tc.start("followdot", 0.0)
    s = EyeState()
    won = False
    for t in np.arange(0.0, 3.0, 1 / 15):
        hub.face(float(t), -160.0, 0.0, 300.0)      # the first target is left
        sl, _, _ = tc.apply(float(t), s, s)
        if tc.theme is not None and tc.theme.result == "win":
            won = True
    assert won


def test_staring_contest_loses_or_wins(cfg):
    anim, hub, beh = make(cfg)
    tc = ThemeController(cfg, seed=1, anim=anim, hub=hub)
    tc.start("staring", 0.0)
    s = EyeState()
    assert anim.blinks_enabled is False
    hub.event("user_blink", 2.0)
    sl, _, _ = tc.apply(2.1, s, s)
    assert tc.theme.user_blinked_at is not None and sl.state.lid_lower > 0.3   # smug win
    for t in np.arange(2.2, 6.0, 0.5):
        tc.apply(float(t), s, s)
    assert tc.active is None                       # ended itself


def test_peekaboo_closes_when_covered(cfg):
    anim, hub, beh = make(cfg)
    tc = ThemeController(cfg, seed=1, anim=anim, hub=hub)
    tc.start("peekaboo", 0.0)
    s = EyeState()
    hub.set(0.5, camera_covered=True)
    sl, _, _ = tc.apply(0.6, s, s)
    assert sl.state.lid_upper == 1.0
    hub.set(1.0, camera_covered=False)
    sl, _, _ = tc.apply(1.1, s, s)
    assert sl.state.pupil_scale < 0.8               # surprised


def test_mirror_copies_blink_and_gaze(cfg):
    anim, hub, beh = make(cfg)
    tc = ThemeController(cfg, seed=1, anim=anim, hub=hub)
    tc.start("mirror", 0.0)
    hub.face(0.0, 120.0, 0.0, 300.0)
    hub.event("user_blink", 0.5)
    sl, _, _ = tc.apply(0.55, EyeState(), EyeState())
    assert sl.state.pupil_x > 20 and anim.blink_t0 >= 0.5


def test_brows_and_iris_render_and_dirty(cfg):
    r = EyeRenderer(cfg, "left")
    f0, _ = r.render(EyeState())
    f0 = f0.copy()
    f1, dirty = r.render(EyeState(brow_y=8, brow_tilt=12))
    changed = np.any(f1 != f0, axis=2)
    ys, xs = np.nonzero(changed)
    assert len(ys) > 50
    assert ys.min() >= dirty[1] and ys.max() < dirty[3] and xs.min() >= dirty[0] and xs.max() < dirty[2]
    f2, dirty2 = r.render(EyeState(brow_y=8, brow_tilt=12, pupil_x=4))
    assert (dirty2[2] - dirty2[0]) < 200             # only the pupil group moved, brows excluded


def test_wink_and_lazy_eye(cfg):
    anim = Animator(cfg, 0.0, seed=0)
    anim.set_idle(False, 0.0)
    anim.next_blink_at = 1e9
    anim.blink(0.0, side="left")
    l, r, _ = anim.update(0.11)
    assert l.lid_upper == 1.0 and r.lid_upper == 0.0
    cfg2 = __import__("copy").deepcopy(cfg)
    cfg2.personality.lazy_eye = 1.0
    anim2 = Animator(cfg2, 0.0, seed=0)
    anim2.set_idle(False, 0.0)
    anim2.next_blink_at = 1e9
    l, r, _ = anim2.update(0.0)
    assert r.pupil_x > l.pupil_x + 8


def test_camera_detector_with_synthetic_frames(cfg):
    pytest.importorskip("cv2")
    from microduck_eyes.camera import FaceDetector
    det = FaceDetector(cfg.camera)
    dark = np.zeros((240, 320, 3), np.uint8)
    out = det.process(dark, 0.0)
    assert out["covered"] is True and out["face"] is None
    bright = np.full((240, 320, 3), 128, np.uint8)
    det.process(bright, 0.1)
    moving = bright.copy()
    moving[:, 240:] = 255
    out = det.process(moving, 0.2)
    assert out["covered"] is False and out["motion"] is not None and out["motion"][0] < 0   # motion on the image right = viewer's left
