"""Behaviour engine: the layer that makes the eyes feel alive.

Reads the SensorHub, drives the Animator (gaze, blinks) and post-processes the EyeStates:
  attention model   peripheral motion -> glance -> evaluate -> track or return; boredom
  eye contact       a face becomes the gaze target with convergence, broken by natural glance-aways
  pupil light       slow adaptation to light level, startle dilation on loud sounds
  vestibular reflex eyes counter-rotate when the head turns, then recentre
  circadian         morning stretch, evening sleepiness, night sleep with stirs
  speech cues       syllable squeezes and pupil bounces, brow raise on emphasis, a think-look first
  sound motion      chirp double-bounce, sigh drift
  mood ring         petting softens the eyes and warms the iris, decaying over time
  tears pooling     a sad face slowly pools a tear that falls
  brightness        backlight breathing when asleep, dim at night, flash on startle
  reflections       a window reflection on the sclera that follows head movement and light direction
Every quantity is a filter or a timer, so when nothing changes the output stops changing.
"""
from __future__ import annotations

import math
import random
import re
import time as _time
from dataclasses import dataclass, replace

from .config import Config
from .eye import pupil_sprites
from .eye.animator import Animator
from .eye.state import EyeState
from .eye.themes import Overlay, sprite_at
from .sensors import SensorHub

SIDES = ("left", "right")


def _approach(cur: float, target: float, dt: float, tau: float) -> float:
    if tau <= 0:
        return target
    k = 1.0 - math.exp(-dt / tau)
    return cur + (target - cur) * k


@dataclass
class Request:
    theme: str
    hold: float | None = None
    params: dict | None = None


class Behaviour:
    def __init__(self, cfg: Config, anim: Animator, hub: SensorHub, now: float, seed: int | None = None):
        self.cfg = cfg
        self.anim = anim
        self.hub = hub
        self.rng = random.Random(seed)
        self.enabled = cfg.behaviour.enabled
        self.reflections = True
        self.last = now
        self.C = cfg.panel.size / 2.0
        e = cfg.eye
        self.max_off = e.sclera_r - e.outline_w - e.pupil_margin - e.pupil_r
        # filters
        self.pupil_light = 1.0
        self.startle = 0.0
        self.vor = [0.0, 0.0]
        self.mood = 0.0
        self.brightness = 1.0
        self._brightness_target = 1.0
        # attention
        self.attention = "idle"            # idle | glance | evaluate | track | return
        self.att_until = now
        self.att_target = (0.0, 0.0, 300.0)
        self.interest = 0.0
        self.next_glance_away = now + self.rng.uniform(*cfg.personality.glance_away_s)
        self.glance_away_until = 0.0
        self._last_event_t = now
        # speech and sounds
        self.syllables: list[tuple[float, bool]] = []   # (time, emphasis)
        self.think_until = 0.0
        self.chirp_t0 = -1.0
        self.sigh_t0 = -1.0
        # circadian
        self.phase = "day"
        self.phase_since = now
        self.stretch_done = False
        self.next_stir = 0.0
        self.sad_since: float | None = None
        self.tear_t0 = -1.0
        self.tear_side = "left"
        self.requests: list[Request] = []
        self._auto_glanced: dict[str, float] = {}
        self.weather_shown_day: int | None = None
        self.user_expression = "neutral"

    # ---- commands -----------------------------------------------------
    def speak(self, text: str, now: float, think: bool = True):
        words = re.findall(r"[A-Za-z']+[!?]?", text)
        t = now + (0.8 if think else 0.1)
        if think:
            self.think_until = now + 0.8
        self.syllables = []
        for w in words:
            emph = w.endswith("!") or (w[:-1].isupper() and len(w) > 2) or w.isupper() and len(w) > 2
            n = max(1, len(re.findall(r"[aeiouy]+", w.lower())))
            for _ in range(n):
                self.syllables.append((t, emph))
                t += 0.17
            t += 0.09
        self.hub.set(now, speaking=True)
        self.speak_until = t

    def sound(self, kind: str, now: float, level: float = 1.0):
        if kind == "chirp":
            self.chirp_t0 = now
        elif kind == "sigh":
            self.sigh_t0 = now
        else:  # loud / bang / noise
            self.startle = max(self.startle, min(level, 1.0))
            self.anim.blink(now)
            self._brightness_target = 1.0

    def set_expression_name(self, name: str, now: float):
        self.user_expression = name
        if name == "sad":
            self.sad_since = now
        else:
            self.sad_since = None
            self.tear_t0 = -1.0

    def pop_request(self) -> Request | None:
        return self.requests.pop(0) if self.requests else None

    # ---- helpers ------------------------------------------------------
    def _hour(self) -> float:
        if self.hub.state.hour is not None:
            return self.hub.state.hour % 24
        t = _time.localtime()
        return t.tm_hour + t.tm_min / 60.0

    def _update_phase(self, now: float):
        b = self.cfg.behaviour
        h = self._hour()
        if h >= b.night_hour or h < b.morning_hour:
            phase = "night"
        elif h < b.morning_hour + 3:
            phase = "morning"
        elif h >= b.evening_hour:
            phase = "evening"
        else:
            phase = "day"
        if phase != self.phase:
            self.phase, self.phase_since = phase, now
            self.stretch_done = False
            if phase == "night":
                self.next_stir = now + self.rng.uniform(20, 50)
        if phase == "morning" and not self.stretch_done and now - self.phase_since > 0.5:
            self.stretch_done = True
            self.requests.append(Request("yawn"))

    def _auto_glance(self, what: str, now: float, params=None, every: float = 60.0, hold: float | None = None):
        last = self._auto_glanced.get(what, -1e9)
        if now - last >= every:
            self._auto_glanced[what] = now
            self.requests.append(Request(what, hold, params))

    # ---- main update ----------------------------------------------------
    def update(self, now: float):
        dt = min(max(now - self.last, 0.0), 0.1)
        self.last = now
        s = self.hub.state
        b = self.cfg.behaviour
        if not self.enabled:
            return
        self._update_phase(now)

        # pupil response to light, startle decay
        target = b.pupil_dark + (b.pupil_bright - b.pupil_dark) * min(max(s.light, 0.0), 1.0)
        self.pupil_light = _approach(self.pupil_light, target, dt, b.light_adapt_s)
        self.startle = max(0.0, self.startle - dt / 1.1)
        for ev in self.hub.recent("sound", self._last_event_t):
            if ev.data.get("kind") == "loud":
                self.sound("loud", now, ev.data.get("level", 1.0))

        # vestibular: counter-rotate against head rate, then recentre
        self.vor[0] += -s.head_yaw_rate * b.vor_gain * dt
        self.vor[1] += -s.head_pitch_rate * b.vor_gain * dt
        decay = math.exp(-dt / b.vor_decay_s) if (abs(s.head_yaw_rate) < 1 and abs(s.head_pitch_rate) < 1) else 1.0
        self.vor[0] *= decay
        self.vor[1] *= decay
        lim = self.max_off * 0.9
        self.vor = [max(-lim, min(lim, v)) for v in self.vor]

        # mood ring: petting
        self.mood = _approach(self.mood, 1.0 if s.touch else 0.0, dt, 3.0 if s.touch else 20.0)

        # attention and eye contact
        self._attention(now)

        # speech bookkeeping
        if s.speaking and self.syllables and now > self.syllables[-1][0] + 0.3:
            self.hub.set(now, speaking=False)
            self.syllables = []

        # status glances and reactions to transitions
        for ev in self.hub.recent("battery_low", self._last_event_t):
            self._auto_glance("battery", now, {"level": s.battery}, every=0, hold=2.5)
        for ev in self.hub.recent("charging_start", self._last_event_t):
            self._auto_glance("battery", now, {"level": s.battery, "charging": True}, every=0, hold=2.5)
        for ev in self.hub.recent("wifi_lost", self._last_event_t):
            self._auto_glance("wifi", now, {"bars": 0}, every=0, hold=2.5)
        for ev in self.hub.recent("listening_start", self._last_event_t):
            self.requests.append(Request("listening", 60.0))
        for ev in self.hub.recent("listening_stop", self._last_event_t) + self.hub.recent("thinking_stop", self._last_event_t):
            self.requests.append(Request("off"))
        for ev in self.hub.recent("thinking_start", self._last_event_t):
            self.requests.append(Request("thinking", 60.0))
        if s.battery <= b.low_battery and not s.charging:
            self._auto_glance("battery", now, {"level": s.battery}, every=60.0, hold=2.5)
        h = self._hour()
        day = _time.localtime().tm_yday
        if s.weather and 7 <= h < 9.5 and self.weather_shown_day != day:
            self.weather_shown_day = day
            self.requests.append(Request("weather", 3.0, {"kind": s.weather}))

        # circadian: evening sleepiness and night sleep handled in modify(); night stirs
        if self.phase == "night" and now >= self.next_stir:
            self.next_stir = now + self.rng.uniform(20, 50)
            self.anim.blink(now)

        # brightness: dim at night, breathe when asleep, otherwise follow light a little
        if self.phase == "night":
            self._brightness_target = 0.45 + 0.12 * math.sin(now * 2 * math.pi * 0.18)
        else:
            self._brightness_target = 0.75 + 0.25 * min(max(s.light, 0.0), 1.0)
        if self.startle > 0.3:
            self._brightness_target = 1.0
        self.brightness = round(_approach(self.brightness, self._brightness_target, dt, 0.4), 2)

        # tears pooling when sad for a while
        if self.sad_since is not None and now - self.sad_since > 2.5 and self.tear_t0 < 0:
            self.tear_t0 = now
            self.tear_side = self.rng.choice(SIDES)
        if self.tear_t0 >= 0 and now - self.tear_t0 > 4.0:
            self.tear_t0 = now if self.sad_since is not None else -1.0
            self.tear_side = self.rng.choice(SIDES)

        self._last_event_t = now

    def _attention(self, now: float):
        s = self.hub.state
        a = self.cfg.animation
        face = s.face
        motions = self.hub.recent("motion", self._last_event_t)

        if face is not None:
            # Eye contact, broken by brief natural glance-aways.
            if self.attention != "track":
                self.attention = "track"
                self.anim.set_idle(False, now)
            if now >= self.next_glance_away and now >= self.glance_away_until:
                self.glance_away_until = now + self.rng.uniform(0.4, 0.9)
                self.next_glance_away = now + self.rng.uniform(*self.cfg.personality.glance_away_s)
                ang = self.rng.uniform(0, 2 * math.pi)
                self.anim.look_at(face.x_mm + 120 * math.cos(ang), face.y_mm + 80 * math.sin(ang), now,
                                  z_mm=face.z_mm, dur_ms=140, hold_s=1.0)
            elif now >= self.glance_away_until:
                self.anim.look_at(face.x_mm, face.y_mm, now, z_mm=face.z_mm, dur_ms=160, hold_s=1.0)
            return

        if motions and self.attention in ("idle", "return"):
            m = max(motions, key=lambda e: e.data.get("magnitude", 0))
            mag = m.data.get("magnitude", 0.3)
            self.att_target = (m.data.get("dx", 0) * 250, m.data.get("dy", 0) * 150, 400.0)
            self.attention = "glance"
            self.att_until = now + 0.4
            self.interest = min(1.0, 0.3 + mag)
            self.anim.set_idle(False, now)
            self.anim.look_at(*self.att_target[:2], now, z_mm=self.att_target[2], dur_ms=120, hold_s=1.0)
        elif self.attention == "glance" and now >= self.att_until:
            self.attention = "evaluate"
            self.att_until = now + 0.6
        elif self.attention == "evaluate" and now >= self.att_until:
            if self.rng.random() < self.interest:
                self.attention = "track"
                self.att_until = now + self.rng.uniform(2.0, 5.0)
            else:
                self.attention = "return"
                self.att_until = now + 0.3
                self.anim.look_at(0.0, 0.0, now, dur_ms=250, hold_s=0.5)
        elif self.attention == "track":
            if motions:
                m = motions[-1]
                self.att_target = (m.data.get("dx", 0) * 250, m.data.get("dy", 0) * 150, 400.0)
                self.anim.look_at(*self.att_target[:2], now, z_mm=400.0, dur_ms=200, hold_s=1.0)
                self.att_until = max(self.att_until, now + 1.5)
            if now >= self.att_until:                 # boredom
                self.attention = "return"
                self.att_until = now + 0.3
                self.anim.look_at(0.0, 0.0, now, dur_ms=300, hold_s=0.5)
        elif self.attention == "return" and now >= self.att_until:
            self.attention = "idle"
            self.anim.set_idle(True, now)

    # ---- output -------------------------------------------------------
    def modify(self, now: float, left: EyeState, right: EyeState) -> tuple[EyeState, EyeState, list[Overlay], list[Overlay]]:
        if not self.enabled:
            return left, right, [], []
        s = self.hub.state
        out = []
        ovs: list[list[Overlay]] = [[], []]
        # speech cues
        squeeze, bounce, brow_raise = 0.0, 0.0, 0.0
        for t, emph in self.syllables:
            d = now - t
            if 0 <= d < 0.12:
                k = math.sin(math.pi * d / 0.12)
                squeeze = max(squeeze, 0.05 * k)
                bounce = max(bounce, 3.0 * k)
                if emph:
                    brow_raise = max(brow_raise, 6.0 * k)
        thinking = now < self.think_until
        # sounds
        chirp_dy = 0.0
        if self.chirp_t0 >= 0:
            d = now - self.chirp_t0
            if d < 0.36:
                chirp_dy = -6.0 * abs(math.sin(2 * math.pi * d / 0.18)) * (1 - d / 0.36)
        sigh_lid, sigh_dy = 0.0, 0.0
        if self.sigh_t0 >= 0:
            d = now - self.sigh_t0
            if d < 1.8:
                k = math.sin(math.pi * d / 1.8)
                sigh_lid, sigh_dy = 0.3 * k, 8.0 * k
        # circadian
        sleepy = 0.0
        asleep = self.phase == "night"
        if self.phase == "evening":
            sleepy = min(0.25, (now - self.phase_since) / 60.0 * 0.25 + 0.1)
        # mood colour
        iris_colour = None
        if self.mood > 0.02:
            base, warm = self.cfg.iris.colour, self.cfg.iris.mood_colour
            iris_colour = tuple(int(b + (w - b) * self.mood) for b, w in zip(base, warm))

        for i, (side, st) in enumerate(zip(SIDES, (left, right))):
            scale = st.pupil_scale * self.pupil_light * (1 + 0.3 * self.startle) * (1 + 0.1 * self.mood)
            px = st.pupil_x + self.vor[0]
            py = st.pupil_y + self.vor[1] + bounce + chirp_dy + sigh_dy
            if thinking:
                px, py = -22 if side == "left" else -18, -26
            lid_u = max(st.lid_upper, squeeze, sleepy, sigh_lid) if not asleep else 1.0
            lid_l = max(st.lid_lower, squeeze * 0.6, 0.2 * self.mood) if not asleep else 1.0
            if self.startle > 0.2:
                lid_u = min(lid_u, 0.0) if st.lid_upper < 0.5 else lid_u
            brow_y = st.brow_y - brow_raise - 6.0 * self.startle
            new = replace(st, pupil_x=round(px), pupil_y=round(py), pupil_scale=round(scale, 2),
                          lid_upper=round(lid_u, 3), lid_lower=round(lid_l, 3), brow_y=round(brow_y, 1),
                          iris_colour=iris_colour if st.iris_colour is None else st.iris_colour)
            out.append(new)
            # reflections: a window reflection on the sclera, shifting with head angles and light direction
            if self.reflections and not asleep and st.pupil_sprite == "disc":
                lx, ly = s.light_dir
                rx = self.C + 48 * lx - 1.2 * s.head_yaw
                ry = self.C + 48 * ly - 1.2 * s.head_pitch
                ovs[i] += sprite_at("reflection", 52, rx, ry)
            # pooled tear: grows at the lower inner corner, then falls
            if self.tear_t0 >= 0 and side == self.tear_side and st.pupil_sprite == "disc":
                d = now - self.tear_t0
                e = self.cfg.eye
                inner = 1.0 if side == "left" else -1.0
                x0 = self.C + inner * 0.55 * e.sclera_r
                y0 = self.C + 0.72 * e.sclera_r
                if d < 2.0:
                    r = 2.0 + 7.0 * d / 2.0
                    ovs[i] += sprite_at("tear", r, x0, y0 - 2)
                elif d < 3.0:
                    fall = (d - 2.0) / 1.0
                    ovs[i] += sprite_at("tear", 8.0, x0 + inner * 4 * fall, y0 + 90 * fall * fall, fade=1 - fall * 0.7)
        return out[0], out[1], ovs[0], ovs[1]

    def animating(self, now: float) -> bool:
        if not self.enabled:
            return False
        s = self.hub.state
        return (self.startle > 0.01 or abs(self.vor[0]) > 0.3 or abs(self.vor[1]) > 0.3 or
                abs(s.head_yaw_rate) > 0 or abs(s.head_pitch_rate) > 0 or
                bool(self.syllables and now < self.syllables[-1][0] + 0.2) or now < self.think_until or
                (0 <= now - self.chirp_t0 < 0.4) or (0 <= now - self.sigh_t0 < 1.9) or
                (0.02 < self.mood < 0.98 and (s.touch or self.mood > 0.02)) or
                self.tear_t0 >= 0 or self.phase == "night" or self.phase == "evening" or
                abs(self.brightness - self._brightness_target) > 0.02 or
                abs(self.pupil_light - (self.cfg.behaviour.pupil_dark + (self.cfg.behaviour.pupil_bright - self.cfg.behaviour.pupil_dark) * s.light)) > 0.01)

    def next_wake(self, now: float) -> float:
        if not self.enabled:
            return float("inf")
        if self.animating(now):
            return now + 1.0 / 30.0
        t = min(self.att_until if self.attention != "idle" else float("inf"), self.next_glance_away if self.hub.state.face else float("inf"))
        if self.phase == "night":
            t = min(t, self.next_stir)
        return max(t, now + 0.01)
