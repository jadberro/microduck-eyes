from microduck_eyes.eye.animator import Animator, Param


def test_param_eases_to_target():
    p = Param(0.0)
    p.set(10.0, now=0.0, dur=1.0)
    assert p.value(0.0) == 0.0
    assert 4.0 < p.value(0.5) < 6.0
    assert p.value(1.0) == 10.0 and not p.animating(1.0)


def test_blink_closes_and_reopens(cfg):
    a = Animator(cfg, 0.0, seed=1)
    a.set_idle(False, 0.0)
    a.next_blink_at = 1e9
    a.blink(0.0)
    closed = a.update(0.11)[0]
    assert closed.lid_upper == 1.0 and closed.lid_lower == 1.0
    assert a.animating(0.2)
    reopened = a.update(0.5)[0]
    assert reopened.lid_upper == 0.0
    assert not a.animating(0.5)


def test_scheduled_blink_happens_within_interval(cfg):
    a = Animator(cfg, 0.0, seed=3)
    a.set_idle(False, 0.0)
    lo, hi = cfg.animation.blink_interval_s
    assert lo <= a.next_blink_at <= hi
    t = a.next_blink_at
    a.update(t)                      # the app loop wakes exactly at next_wake(), which is next_blink_at
    left, _, _ = a.update(t + 0.11)
    assert left.lid_upper == 1.0


def test_gaze_converges_for_near_target(cfg):
    a = Animator(cfg, 0.0, seed=0)
    a.set_idle(False, 0.0)
    a.look_at(0.0, 0.0, 0.0, z_mm=60.0, dur_ms=0)
    left, right, _ = a.update(0.0)
    assert left.pupil_x > 0 and right.pupil_x < 0   # both pupils turn inwards


def test_update_reports_change_only_when_state_changes(cfg):
    a = Animator(cfg, 0.0, seed=0)
    a.set_idle(False, 0.0)
    a.next_blink_at = 1e9
    assert a.update(0.0)[2] is True
    assert a.update(0.01)[2] is False
    a.set_expression("happy", 0.02)
    assert a.update(0.1)[2] is True


def test_idle_wake_is_next_scheduled_event(cfg):
    a = Animator(cfg, 0.0, seed=0)
    a.set_idle(False, 0.0)
    a.update(0.0)
    assert a.next_wake(0.0) == a.next_blink_at
