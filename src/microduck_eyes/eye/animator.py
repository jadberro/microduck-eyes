"""Tweens, blinking, gaze and idle behaviour. Produces an EyeState per eye.

Everything is time-driven from a `now` value the caller supplies, so it is
deterministic in tests and sleeps cleanly in the app loop.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..config import Config
from .expressions import ORDER, PRESETS, EyeParams, Expression, inner_sign, screen_brow_tilt, screen_tilt
from .state import EyeState, clamp

SIDES = ("left", "right")


def ease_in_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def ease_in(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t


def ease_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1.0 - (1.0 - t) * (1.0 - t)


class Param:
    """A float that eases towards a target over a duration."""

    __slots__ = ("start", "end", "t0", "dur")

    def __init__(self, value: float):
        self.start = self.end = value
        self.t0 = 0.0
        self.dur = 0.0

    def set(self, target: float, now: float, dur: float):
        if target == self.end and (self.dur == 0.0 or now >= self.t0 + self.dur):
            return
        self.start = self.value(now)
        self.end = target
        self.t0 = now
        self.dur = max(dur, 0.0)

    def value(self, now: float) -> float:
        if self.dur <= 0.0 or now >= self.t0 + self.dur:
            return self.end
        t = (now - self.t0) / self.dur
        return self.start + (self.end - self.start) * ease_in_out(t)

    def animating(self, now: float) -> bool:
        return self.dur > 0.0 and now < self.t0 + self.dur


@dataclass
class _EyeParams:
    lid_upper: Param
    lid_lower: Param
    tilt: Param
    pupil_scale: Param
    gaze_dx: Param
    gaze_dy: Param
    brow_y: Param
    brow_tilt: Param

    def all(self):
        return (self.lid_upper, self.lid_lower, self.tilt, self.pupil_scale, self.gaze_dx, self.gaze_dy, self.brow_y, self.brow_tilt)


class Animator:
    def __init__(self, cfg: Config, now: float = 0.0, seed: int | None = None):
        self.cfg = cfg
        self.rng = random.Random(seed)
        a = cfg.animation
        self.params = {
            s: _EyeParams(Param(0), Param(0), Param(0), Param(1), Param(0), Param(0), Param(0), Param(0)) for s in SIDES
        }
        self.expression: Expression = PRESETS["neutral"]
        # Gaze in head space, mm. Origin midway between the eyes, +x right, +y down, z forward.
        self.target = [0.0, 0.0, cfg.layout.gaze_depth_mm]
        self.gaze_gain = 2.5
        self.idle = True
        self.idle_resume_at = 0.0
        self.next_saccade_at = now + self.rng.uniform(*a.saccade_interval_s)
        # Blink state (themes may disable blinks or change the interval; the controller restores them)
        self.blinks_enabled = True
        self.blink_interval: tuple[float, float] | None = None
        self.blink_t0 = -1.0
        self.blink_side: str | None = None       # a wink closes only this side
        self.next_blink_at = now + self.rng.uniform(*a.blink_interval_s)
        self.pending_double = False
        self._last_states: tuple[EyeState, EyeState] | None = None

    # ---- commands -----------------------------------------------------
    def set_expression(self, name: str, now: float, dur_ms: float | None = None):
        if name not in PRESETS:
            raise KeyError(name)
        self.expression = PRESETS[name]
        dur = (self.cfg.animation.expression_ms if dur_ms is None else dur_ms) / 1000.0
        for side in SIDES:
            p: EyeParams = self.expression.for_side(side)
            ep = self.params[side]
            ep.lid_upper.set(p.lid_upper, now, dur)
            ep.lid_lower.set(p.lid_lower, now, dur)
            ep.tilt.set(screen_tilt(p, side), now, dur)
            ep.pupil_scale.set(p.pupil_scale, now, dur)
            ep.gaze_dx.set(p.gaze_dx_inner * inner_sign(side), now, dur)
            ep.gaze_dy.set(p.gaze_dy, now, dur)
            ep.brow_y.set(p.brow_y, now, dur)
            ep.brow_tilt.set(screen_brow_tilt(p, side), now, dur)

    def cycle_expression(self, now: float, step: int = 1) -> str:
        i = (ORDER.index(self.expression.name) + step) % len(ORDER)
        self.set_expression(ORDER[i], now)
        return ORDER[i]

    def blink(self, now: float, side: str | None = None):
        if self.blink_t0 < 0 or now > self.blink_t0 + self._blink_total():
            self.blink_t0 = now
            self.blink_side = side

    def look_at(self, x_mm: float, y_mm: float, now: float, z_mm: float | None = None,
                dur_ms: float | None = None, hold_s: float = 0.0):
        self.target = [x_mm, y_mm, self.target[2] if z_mm is None else z_mm]
        self._apply_gaze(now, dur_ms)
        if hold_s > 0:
            self.idle_resume_at = max(self.idle_resume_at, now + hold_s)
            self.next_saccade_at = max(self.next_saccade_at, self.idle_resume_at)

    def set_idle(self, on: bool, now: float):
        self.idle = on
        if on:
            self.next_saccade_at = now + self.rng.uniform(*self.cfg.animation.saccade_interval_s)

    # ---- internals ----------------------------------------------------
    def _blink_total(self) -> float:
        a = self.cfg.animation
        return (a.blink_close_ms + a.blink_hold_ms + a.blink_open_ms) / 1000.0

    def _blink_amount(self, now: float) -> float:
        if self.blink_t0 < 0:
            return 0.0
        a = self.cfg.animation
        t = now - self.blink_t0
        close = a.blink_close_ms / 1000.0
        hold = a.blink_hold_ms / 1000.0
        open_ = a.blink_open_ms / 1000.0
        if t < 0:
            return 0.0
        if t < close:
            return ease_in(t / close)
        if t < close + hold:
            return 1.0
        if t < close + hold + open_:
            return 1.0 - ease_out((t - close - hold) / open_)
        return 0.0

    def _blinking(self, now: float) -> bool:
        return self.blink_t0 >= 0 and now < self.blink_t0 + self._blink_total()

    def _eyes_closed(self) -> bool:
        p = self.expression.both
        return p.lid_upper >= 0.95 and p.lid_lower >= 0.95

    def _pupil_offset(self, side: str) -> tuple[float, float]:
        e = self.cfg.eye
        spacing = self.cfg.layout.eye_spacing_mm
        ex = -spacing / 2.0 if side == "left" else spacing / 2.0
        tx, ty, tz = self.target
        tz = max(tz, 20.0)
        dx = (tx - ex) / tz
        dy = ty / tz
        max_off = e.sclera_r - e.outline_w - e.pupil_margin - e.pupil_r
        ox = max_off * max(min(dx * self.gaze_gain, 1.0), -1.0)
        oy = max_off * max(min(dy * self.gaze_gain, 1.0), -1.0)
        return ox, oy

    def _apply_gaze(self, now: float, dur_ms: float | None = None):
        dur = (self.cfg.animation.gaze_move_ms if dur_ms is None else dur_ms) / 1000.0
        for side in SIDES:
            ox, oy = self._pupil_offset(side)
            ep = self.params[side]
            ep.gaze_dx.set(ox + self.expression.for_side(side).gaze_dx_inner * inner_sign(side), now, dur)
            ep.gaze_dy.set(oy + self.expression.for_side(side).gaze_dy, now, dur)

    def _schedule(self, now: float):
        a = self.cfg.animation
        # Blinks
        if now >= self.next_blink_at and not self._blinking(now):
            if not self._eyes_closed() and self.blinks_enabled:
                self.blink_t0 = now
                wink = self.rng.random() < self.cfg.personality.wink_chance
                self.blink_side = self.rng.choice(SIDES) if wink else None
            interval = self.blink_interval or a.blink_interval_s
            if self.pending_double:
                self.pending_double = False
                self.next_blink_at = now + self._blink_total() + 0.12
            else:
                self.pending_double = self.rng.random() < a.double_blink_chance
                self.next_blink_at = now + self.rng.uniform(*interval)
        # Idle saccades
        if self.idle and now >= self.idle_resume_at and now >= self.next_saccade_at:
            r = a.saccade_range_mm
            depth = self.cfg.layout.gaze_depth_mm
            # Mostly small moves with the odd larger glance.
            big = self.rng.random() < 0.25
            scale = 1.0 if big else 0.4
            self.target = [self.rng.uniform(-r, r) * scale, self.rng.uniform(-r * 0.6, r * 0.6) * scale, depth]
            self._apply_gaze(now, a.gaze_move_ms * (1.4 if big else 1.0))
            self.next_saccade_at = now + self.rng.uniform(*a.saccade_interval_s)

    # ---- output -------------------------------------------------------
    def update(self, now: float) -> tuple[EyeState, EyeState, bool]:
        self._schedule(now)
        b = self._blink_amount(now)
        states = []
        lazy = self.cfg.personality.lazy_eye
        for side in SIDES:
            ep = self.params[side]
            bs = b if (self.blink_side is None or self.blink_side == side) else 0.0
            up = max(ep.lid_upper.value(now), bs)
            lo = max(ep.lid_lower.value(now), bs)
            gx, gy = ep.gaze_dx.value(now), ep.gaze_dy.value(now)
            if lazy > 0 and side == "right":
                gx = gx * (1 - 0.5 * lazy) + 14 * lazy      # lags and drifts outward
                gy = gy * (1 - 0.3 * lazy) + 4 * lazy
            states.append(clamp(EyeState(
                pupil_x=round(gx),
                pupil_y=round(gy),
                pupil_scale=round(ep.pupil_scale.value(now), 2),
                lid_upper=round(up, 3),
                lid_lower=round(lo, 3),
                lid_tilt=round(ep.tilt.value(now), 3),
                brow_y=round(ep.brow_y.value(now), 1),
                brow_tilt=round(ep.brow_tilt.value(now), 1),
            ), self.cfg))
        out = (states[0], states[1])
        changed = out != self._last_states
        self._last_states = out
        return out[0], out[1], changed

    def animating(self, now: float) -> bool:
        if self._blinking(now):
            return True
        return any(p.animating(now) for side in SIDES for p in self.params[side].all())

    def next_wake(self, now: float) -> float:
        """Earliest time something will change if no input arrives."""
        if self.animating(now):
            return now + 1.0 / 60.0
        t = self.next_blink_at
        if self.idle:
            t = min(t, max(self.next_saccade_at, self.idle_resume_at))
        return max(t, now + 0.001)
