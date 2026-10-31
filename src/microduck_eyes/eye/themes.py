"""Themed takeovers of the eyes, for comedy.

Each theme is a small class that turns the animator's EyeStates into a PanelSpec per panel:
either a scene (full-panel frame, optionally drawn over the eye) or an eye state with an
optional pupil sprite and particle overlays. The ThemeController owns timing, timeouts,
change detection and the "surprise me" scheduler. Everything is driven by `now`.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

import numpy as np

from ..config import Config
from . import pupil_sprites, scenes as scenes_mod, sprites
from .state import EyeState

Overlay = tuple[np.ndarray, tuple[int, int, int], int, int]  # alpha, colour, x, y (top-left)


@dataclass
class PanelSpec:
    state: EyeState
    scene: tuple | None = None          # (name, frame, extra)
    over_eye: bool = False              # scene draws on top of the rendered eye
    overlays: list[Overlay] = field(default_factory=list)


@dataclass
class Ctx:
    cfg: Config
    rng: random.Random
    anim: object | None
    scenes: object | None
    sources: list | None
    params: dict
    now: float = 0.0
    hub: object | None = None          # SensorHub, for games and glances


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _q(s: EyeState) -> EyeState:
    """Quantise so equal-looking states compare equal."""
    return replace(s, pupil_x=round(s.pupil_x), pupil_y=round(s.pupil_y), pupil_scale=round(s.pupil_scale, 2),
                   lid_upper=round(min(max(s.lid_upper, 0), 1), 3), lid_lower=round(min(max(s.lid_lower, 0), 1), 3),
                   lid_tilt=round(s.lid_tilt, 3))


def sprite_at(name: str, r: float, cx: float, cy: float, frame: int = 0, fade: float = 1.0) -> list[Overlay]:
    out: list[Overlay] = []
    for alpha, colour in pupil_sprites.layers(name, frame, round(r)):
        if fade < 1.0:
            alpha = (alpha * fade).astype(np.float32)
        h, w = alpha.shape
        out.append((alpha, colour, int(round(cx)) - w // 2, int(round(cy)) - h // 2))
    return out


@dataclass
class Particle:
    sprite: str
    r: float
    x0: float
    y0: float
    vx: float
    vy: float
    born: float
    life: float
    ax: float = 0.0
    ay: float = 0.0
    sway: float = 0.0
    phase: float = 0.0
    grow: float = 0.0
    fade_from: float = 0.6


class Particles:
    def __init__(self):
        self.items: list[Particle] = []

    def overlays(self, now: float) -> list[Overlay]:
        out: list[Overlay] = []
        alive = []
        for p in self.items:
            age = now - p.born
            if age < 0 or age > p.life:
                continue
            alive.append(p)
            x = p.x0 + p.vx * age + 0.5 * p.ax * age * age + p.sway * math.sin(p.phase + age * 4.0)
            y = p.y0 + p.vy * age + 0.5 * p.ay * age * age
            fade = 1.0 if age < p.life * p.fade_from else 1.0 - (age - p.life * p.fade_from) / (p.life * (1 - p.fade_from))
            out += sprite_at(p.sprite, p.r + p.grow * age, x, y, fade=fade)
        self.items = alive
        return out


# =============================================================================
class Theme:
    name = ""
    hold = 5.0
    rate = 12.0            # frames per second for frame-stepped content
    continuous = True      # keeps animating for the whole hold
    duration: float | None = None   # if set, animating only this long
    cancel_on_input = False

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.rng = ctx.rng
        self.anim = ctx.anim
        self.hub = ctx.hub
        self.done = False              # a theme may end itself early
        self.C = ctx.cfg.panel.size / 2.0
        e = ctx.cfg.eye
        self.max_off = e.sclera_r - e.outline_w - e.pupil_margin - e.pupil_r

    def start(self):
        pass

    def stop(self):
        pass

    def frame(self, t: float) -> int:
        return int(t * self.rate)

    def animating(self, t: float) -> bool:
        if self.duration is not None:
            return t < self.duration
        return self.continuous

    def impulse(self, dx: float, dy: float):
        pass

    def apply(self, t: float, left: EyeState, right: EyeState) -> tuple[PanelSpec, PanelSpec]:
        return PanelSpec(left), PanelSpec(right)

    # helpers
    def tilt_for(self, side: str, tilt_inner: float) -> float:
        return tilt_inner if side == "left" else -tilt_inner

    def outer_sign(self, side: str) -> float:
        """+1 if the outer corner is in +x for this panel."""
        return -1.0 if side == "left" else 1.0


# ---- movie and sci-fi --------------------------------------------------------

class Hal(Theme):
    name, hold, rate = "hal", 8.0, 4.0

    def apply(self, t, left, right):
        f = self.frame(t) % scenes_mod.HAL_FRAMES
        return PanelSpec(left, ("hal", f, ())), PanelSpec(right, ("hal", f, ()))


class Terminator(Theme):
    name, hold, rate = "terminator", 8.0, 6.0

    def apply(self, t, left, right):
        f = self.frame(t)
        return (PanelSpec(left, ("terminator", f, (round(left.pupil_x), round(left.pupil_y)))),
                PanelSpec(right, ("terminator", f, (round(right.pupil_x), round(right.pupil_y)))))


class Aperture(Theme):
    name, hold, rate = "aperture", 8.0, 15.0
    CYCLE = 3.0

    def apply(self, t, left, right):
        u = t % self.CYCLE
        n = scenes_mod.APERTURE_FRAMES - 1
        if u < 0.8:
            f = int(ease(u / 0.8) * n)
        elif u < 1.3:
            f = n
        elif u < 2.1:
            f = int((1 - ease((u - 1.3) / 0.8)) * n)
        else:
            f = 0
        return (PanelSpec(left, ("aperture", f, ()), over_eye=True),
                PanelSpec(right, ("aperture", f, ()), over_eye=True))


class Eve(Theme):
    name, hold, rate = "eve", 8.0, 10.0

    def apply(self, t, left, right):
        sway = 0.25 * math.sin(t * 1.1)
        out = []
        for s, sign in ((left, 1), (right, -1)):
            closure = max(s.lid_upper, s.lid_lower)
            tilt = round(s.lid_tilt + sway * sign, 2)
            out.append(PanelSpec(s, ("eve", 0, (tilt, round(closure, 2)))))
        return out[0], out[1]


class Matrix(Theme):
    name, hold, rate = "matrix", 6.0, 10.0

    def apply(self, t, left, right):
        f = self.frame(t)
        m = lambda s: replace(s, pupil_sprite="matrix", pupil_frame=f, pupil_scale=1.3)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Spiral(Theme):
    name, hold, rate = "spiral", 6.0, 12.0

    def apply(self, t, left, right):
        f = self.frame(t) % pupil_sprites.FRAMES["spiral"]
        m = lambda s: replace(s, pupil_sprite="spiral", pupil_frame=f, pupil_scale=1.45, lid_upper=max(s.lid_upper, 0.22))
        return PanelSpec(m(left)), PanelSpec(m(right))


class Pirate(Theme):
    name, hold, continuous = "pirate", 6.0, False

    def apply(self, t, left, right):
        r = replace(right, lid_upper=max(right.lid_upper, 0.5), lid_lower=max(right.lid_lower, 0.25),
                    lid_tilt=self.tilt_for("right", 0.25))
        return PanelSpec(left, ("pirate", 0, ())), PanelSpec(r)


class Sunglasses(Theme):
    name, hold, rate, duration = "sunglasses", 6.0, 30.0, 0.8

    def start(self):
        e = self.cfg.eye
        R = e.sclera_r + e.outline_w + 2
        size = pupil_sprites.size_for(R)
        self.lens = pupil_sprites.shape_mask(size, lambda x, y: np.hypot(x, y) < R)
        self.streak = pupil_sprites.shape_mask(size, lambda x, y: (np.abs(x - y * 0.6 + 0.35 * R) < 0.09 * R) & (np.hypot(x, y) < R - 6)) * 0.35
        self.half = size // 2
        self.R = R

    def apply(self, t, left, right):
        p = ease(t / 0.7)
        y = self.C - 2.4 * self.R * (1 - p)
        ov = [(self.lens, (22, 22, 28), int(self.C) - self.half, int(round(y)) - self.half),
              (self.streak.astype(np.float32), (255, 255, 255), int(self.C) - self.half, int(round(y)) - self.half)]
        return PanelSpec(left, overlays=list(ov)), PanelSpec(right, overlays=list(ov))


class Laser(Theme):
    name, hold, continuous = "laser", 5.0, False

    def apply(self, t, left, right):
        m = lambda s: replace(s, pupil_sprite="laser", pupil_x=0, pupil_y=0, pupil_scale=1.0, lid_upper=max(s.lid_upper, 0.12))
        return PanelSpec(m(left)), PanelSpec(m(right))


# ---- money and games -------------------------------------------------------------

class Dollar(Theme):
    name, hold, rate, duration = "dollar", 4.0, 14.0, 2.2

    def apply(self, t, left, right):
        if t < 1.1:
            frame, scale = self.frame(t), 1.2
        else:
            b = t - 1.1
            frame, scale = 0, 1.2 + 0.25 * math.exp(-b * 6.0) * math.cos(b * 18.0)
        m = lambda s: replace(s, pupil_sprite="dollar", pupil_frame=frame, pupil_scale=scale)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Slot(Theme):
    name, hold, rate = "slot", 6.0, 15.0
    SYMBOLS = ["cherry", "seven", "duck", "bread"]
    STOP = (1.6, 2.6)

    def start(self):
        self.jackpot = self.rng.random() < 0.3
        if self.jackpot:
            self.result = ["duck", "duck"]
        else:
            self.result = [self.rng.choice(self.SYMBOLS), self.rng.choice(self.SYMBOLS)]
            if self.result[0] == self.result[1] == "duck":
                self.result[1] = "bread"
        self.coins = Particles()
        self.next_coin = self.STOP[1] + 0.2

    def animating(self, t):
        return t < self.STOP[1] + 0.3 or (self.jackpot and t < self.hold)

    def apply(self, t, left, right):
        out = []
        for i, s in enumerate((left, right)):
            if t < self.STOP[i]:
                f = self.frame(t) // 2
                sym = self.SYMBOLS[(f + i) % 4]
                jitter = 5 if f % 2 == 0 else -5
                st = replace(s, pupil_sprite=sym, pupil_scale=1.25, pupil_x=0, pupil_y=s.pupil_y + jitter)
            else:
                b = t - self.STOP[i]
                bounce = 1.25 + 0.2 * math.exp(-b * 5) * math.cos(b * 16)
                st = replace(s, pupil_sprite=self.result[i], pupil_scale=bounce, pupil_x=0, pupil_y=0)
            if t > self.STOP[1]:
                if self.jackpot:
                    st = replace(st, lid_lower=max(st.lid_lower, 0.42))
                else:
                    st = replace(st, lid_upper=max(st.lid_upper, 0.18), lid_tilt=self.tilt_for("left" if i == 0 else "right", -0.2))
            out.append(st)
        overlays_l, overlays_r = [], []
        if self.jackpot and t > self.STOP[1]:
            now = self.ctx.now
            while t >= self.next_coin:
                born = now - (t - self.next_coin)
                for i in range(2):
                    self.coins.items.append(Particle("coin", self.rng.uniform(6, 10), self.C + self.rng.uniform(-70, 70), self.C - 118,
                                                     self.rng.uniform(-10, 10), self.rng.uniform(40, 80), born, 1.8, ay=220, fade_from=0.8))
                self.next_coin += 0.25
            ovs = self.coins.overlays(now)
            overlays_l, overlays_r = ovs[0::2], ovs[1::2]
        return PanelSpec(out[0], overlays=overlays_l), PanelSpec(out[1], overlays=overlays_r)


class Dice(Theme):
    name, hold, rate, duration = "dice", 5.0, 12.0, 1.3

    def start(self):
        self.faces = [self.rng.randint(1, 6), self.rng.randint(1, 6)]
        if self.rng.random() < 0.25:
            self.faces = [1, 1]

    def apply(self, t, left, right):
        out = []
        for i, s in enumerate((left, right)):
            side = "left" if i == 0 else "right"
            if t < 1.2:
                f = self.frame(t)
                face = (f * 7 + i * 3) % 6
                jx, jy = self.rng.choice((-6, 6)) if False else (6 if f % 2 else -6), (4 if (f // 2) % 2 else -4)
                st = replace(s, pupil_sprite="die", pupil_frame=face, pupil_scale=1.15, pupil_x=jx, pupil_y=jy)
            else:
                st = replace(s, pupil_sprite="die", pupil_frame=self.faces[i] - 1, pupil_scale=1.15, pupil_x=0, pupil_y=0)
                if self.faces == [1, 1]:
                    st = replace(st, lid_upper=max(st.lid_upper, 0.3), lid_tilt=self.tilt_for(side, -0.35), pupil_y=6)
                elif self.faces == [6, 6]:
                    st = replace(st, lid_lower=max(st.lid_lower, 0.45))
            out.append(st)
        return PanelSpec(out[0]), PanelSpec(out[1])


class EightBall(Theme):
    name, hold, rate, duration = "eightball", 6.0, 15.0, 0.9

    def start(self):
        self.answer = self.rng.randrange(len(pupil_sprites.EIGHTBALL_ANSWERS))

    def apply(self, t, left, right):
        if t < 0.8:
            f = self.frame(t)
            jx = 8 if f % 2 else -8
            jy = 5 if (f // 3) % 2 else -5
            m = lambda s: replace(s, pupil_sprite="disc", pupil_scale=1.3, pupil_x=jx, pupil_y=jy, highlights=False)
        else:
            m = lambda s: replace(s, pupil_sprite="eightball", pupil_frame=self.answer, pupil_scale=1.3, pupil_x=0, pupil_y=0)
        return PanelSpec(m(left)), PanelSpec(m(right))


class PokerFace(Theme):
    name, hold, rate, continuous = "poker", 8.0, 30.0, False

    def start(self):
        if self.anim:
            self.anim.blinks_enabled = False
            self.anim.set_idle(False, self.ctx.now)

    def animating(self, t):
        return self.hold - 1.3 < t < self.hold

    def apply(self, t, left, right):
        squint = 0.4 * ease((t - (self.hold - 1.2)) / 1.0) if t > self.hold - 1.2 else 0.0
        m = lambda s: replace(s, pupil_x=0, pupil_y=0, lid_upper=squint, lid_lower=0.0, lid_tilt=0.0, pupil_scale=1.0)
        return PanelSpec(m(left)), PanelSpec(m(right))


# ---- politics, non-partisan -------------------------------------------------

class Debate(Theme):
    name, hold, rate = "debate", 6.0, 20.0
    DART_UNTIL = 3.0

    def start(self):
        self.targets = []
        for _ in range(8):
            ang = self.rng.uniform(0, 2 * math.pi)
            if abs(math.cos(ang)) < 0.5:          # never straight up/down, always "away"
                ang += math.pi / 2
            self.targets.append((self.max_off * 0.9 * math.cos(ang), self.max_off * 0.6 * math.sin(ang)))

    def animating(self, t):
        return t < self.DART_UNTIL + 0.4

    def apply(self, t, left, right):
        if t < self.DART_UNTIL:
            i = int(t / 0.45)
            a = self.targets[i % len(self.targets)]
            b = self.targets[(i + 1) % len(self.targets)]
            k = ease(((t % 0.45) - 0.3) / 0.15)
            px, py = a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
            m = lambda s, side: replace(s, pupil_x=px, pupil_y=py, lid_upper=max(s.lid_upper, 0.08))
        else:
            k = ease((t - self.DART_UNTIL) / 0.4)
            m = lambda s, side: replace(s, pupil_x=s.pupil_x * (1 - k), pupil_y=-3 * k, lid_upper=0.08, lid_lower=0.0,
                                        lid_tilt=self.tilt_for(side, 0.12) * k)
        return PanelSpec(m(left, "left")), PanelSpec(m(right, "right"))


class Campaign(Theme):
    name, hold, rate = "campaign", 6.0, 30.0

    def animating(self, t):
        return t < 3.3

    def _wink(self, t, t0):
        if t0 <= t < t0 + 0.5:
            u = (t - t0) / 0.5
            return math.sin(math.pi * u)
        return 0.0

    def apply(self, t, left, right):
        out = []
        for i, s in enumerate((left, right)):
            w = self._wink(t, 1.0 if i == 0 else 2.5)
            st = replace(s, pupil_sprite="star", pupil_scale=1.2, lid_upper=max(s.lid_upper, w),
                         lid_lower=max(s.lid_lower, 0.5 * w))
            ov = sprite_at("rosette", 15, self.C + (52 if i == 1 else -52), self.C + 64)
            out.append(PanelSpec(st, overlays=ov))
        return out[0], out[1]


class Election(Theme):
    name, hold, rate, duration = "election", 8.0, 4.0, 6.0

    def start(self):
        self.share = round(self.rng.uniform(0.35, 0.65), 2)

    def apply(self, t, left, right):
        n = pupil_sprites.FRAMES["pie"] - 1
        f = min(int(t / 6.0 * n), n)
        name = f"pie:{self.share}"
        out = []
        for side, s in (("left", left), ("right", right)):
            st = replace(s, pupil_sprite=name, pupil_frame=f, pupil_scale=1.3)
            if t < 5.5:
                st = replace(st, lid_upper=0.0, lid_lower=0.0, pupil_y=min(s.pupil_y, -2))
            elif self.share > 0.5:
                st = replace(st, lid_lower=max(st.lid_lower, 0.45))
            else:
                st = replace(st, lid_upper=max(st.lid_upper, 0.3), lid_tilt=self.tilt_for(side, -0.35), pupil_y=6)
            out.append(st)
        return PanelSpec(out[0]), PanelSpec(out[1])


class Filibuster(Theme):
    name, hold, rate, cancel_on_input = "filibuster", 20.0, 2.0, True

    def animating(self, t):
        return t < self.hold * 0.8

    def apply(self, t, left, right):
        p = ease(min(t / (self.hold * 0.8), 1.0))
        m = lambda s: replace(s, pupil_x=s.pupil_x * (1 - p), pupil_y=-self.max_off * p, lid_upper=max(s.lid_upper, 0.6 * p))
        return PanelSpec(m(left)), PanelSpec(m(right))


class Diplomat(Theme):
    name, hold, rate, duration = "diplomat", 5.0, 30.0, 1.4

    def apply(self, t, left, right):
        dip = 12 * math.sin(math.pi * (t - 0.3)) if 0.3 <= t < 1.3 else 0.0
        m = lambda s: replace(s, pupil_x=0, pupil_y=dip, lid_upper=0.04, lid_lower=0.0, lid_tilt=0.0, pupil_scale=1.0)
        return PanelSpec(m(left)), PanelSpec(m(right))


class TaxSeason(Theme):
    name, hold, rate = "tax", 6.0, 15.0

    def start(self):
        self.p = Particles()
        self.next_spawn = [0.0, 0.2]

    def apply(self, t, left, right):
        now = self.ctx.now
        e = self.cfg.eye
        out = []
        for i, (side, s) in enumerate((("left", left), ("right", right))):
            st = replace(s, lid_upper=max(s.lid_upper, 0.3), lid_tilt=self.tilt_for(side, -0.35), pupil_y=max(s.pupil_y, 6))
            while t >= self.next_spawn[i]:
                born = now - (t - self.next_spawn[i])
                x = self.C + self.outer_sign(side) * 0.55 * e.sclera_r
                self.p.items.append(Particle("dollar", self.rng.uniform(7, 10), x, self.C + 0.5 * e.sclera_r,
                                             self.outer_sign(side) * self.rng.uniform(5, 15), 30, born, 1.3, ay=160, fade_from=0.7))
                self.p.items[-1].phase = float(i)
                self.next_spawn[i] += self.rng.uniform(0.3, 0.5)
            out.append(st)
        ovs = self.p.overlays(now)
        # particles tagged by phase: 0 for left, 1 for right
        l_ov = [o for o, p in zip(ovs, self.p.items) if p.phase == 0.0]
        r_ov = [o for o, p in zip(ovs, self.p.items) if p.phase == 1.0]
        return PanelSpec(out[0], overlays=l_ov), PanelSpec(out[1], overlays=r_ov)


# ---- computer and robot gags ------------------------------------------------------

class Boot(Theme):
    name, hold = "boot", 5.5
    T_TEXT = scenes_mod.BOOT_TEXT_FRAMES / 3.0
    T_BAR = scenes_mod.BOOT_BAR_FRAMES / 10.0

    def _frame(self, t):
        if t < self.T_TEXT:
            return int(t * 3)
        return scenes_mod.BOOT_TEXT_FRAMES + int((t - self.T_TEXT) * 10)

    def animating(self, t):
        return t < self.T_TEXT + self.T_BAR + 0.9

    def apply(self, t, left, right):
        t_end = self.T_TEXT + self.T_BAR
        if t < t_end:
            f = self._frame(t)
            return PanelSpec(left, ("boot", f, (0,))), PanelSpec(right, ("boot", f, (1,)))
        k = 1.0 - ease((t - t_end) / 0.8)
        m = lambda s: replace(s, lid_upper=max(s.lid_upper, k), lid_lower=max(s.lid_lower, k), pupil_x=0, pupil_y=0)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Crt(Theme):
    name, hold, rate = "crt", 4.0, 15.0

    def start(self):
        self.n = 1
        if self.ctx.scenes is not None and self.ctx.sources:
            self.n = self.ctx.scenes.prepare_crt(self.ctx.sources[0])

    def animating(self, t):
        return self.frame(t) < self.n

    def apply(self, t, left, right):
        f = min(self.frame(t), self.n - 1)
        return PanelSpec(left, ("crt", f, ())), PanelSpec(right, ("crt", f, ()))


class Buffering(Theme):
    name, hold, rate = "buffering", 5.0, 12.0

    def apply(self, t, left, right):
        f = self.frame(t)
        m = lambda s, sign: replace(s, pupil_sprite="beachball", pupil_frame=f, pupil_scale=1.15, pupil_x=sign * 8, pupil_y=-10)
        return PanelSpec(m(left, -1)), PanelSpec(m(right, 1))


class BlueScreen(Theme):
    name, hold, rate = "bsod", 8.0, 6.0

    def apply(self, t, left, right):
        f = self.frame(t)
        tremble = 1 if f % 2 else -1
        r = replace(right, pupil_scale=0.6, lid_upper=0.0, lid_lower=0.0, pupil_x=-self.max_off * 0.8 + tremble, pupil_y=tremble)
        return PanelSpec(left, ("bsod", f // 3, ())), PanelSpec(r)


class NotFound(Theme):
    name, hold, rate = "notfound", 6.0, 15.0

    def start(self):
        self.targets = [(self.rng.uniform(-1, 1) * self.max_off * 0.8, self.rng.uniform(-1, 1) * self.max_off * 0.6) for _ in range(10)]

    def apply(self, t, left, right):
        i = int(t / 0.6)
        a, b = self.targets[i % 10], self.targets[(i + 1) % 10]
        k = ease(((t % 0.6) - 0.45) / 0.15)
        l = replace(left, pupil_x=a[0] + (b[0] - a[0]) * k, pupil_y=a[1] + (b[1] - a[1]) * k, lid_upper=max(left.lid_upper, 0.1))
        r = replace(right, pupil_sprite="notfound", pupil_scale=1.25, pupil_x=0, pupil_y=0)
        return PanelSpec(l), PanelSpec(r)


class Battery(Theme):
    name, hold, rate = "battery", 8.0, 2.0

    def start(self):
        self.charging = bool(self.ctx.params.get("charging", False))
        self.level = self.ctx.params.get("level")

    def apply(self, t, left, right):
        level = (self.level / 100.0) if self.level is not None else max(1.0 - t / (self.hold * 0.9), 0.0)
        if self.charging:
            level = (t * 0.25) % 1.0 if self.level is None else level
        f = int(round(level * 10))
        name = "battery_charging" if self.charging else "battery"
        droop = 0.0 if self.charging else 0.55 * (1.0 - level)
        m = lambda s: replace(s, pupil_sprite=name, pupil_frame=f, pupil_scale=1.3, lid_upper=max(s.lid_upper, droop),
                              pupil_y=max(s.pupil_y, 10 * (1 - level)) if not self.charging else s.pupil_y)
        return PanelSpec(m(left)), PanelSpec(m(right))


class EyeRoll(Theme):
    name, hold, rate, duration = "roll", 3.0, 30.0, 1.4

    def apply(self, t, left, right):
        if t < 1.2:
            p = ease(t / 1.2)
            th = -math.pi / 2 + 2 * math.pi * p
            px, py = 0.9 * self.max_off * math.cos(th), 0.9 * self.max_off * math.sin(th)
            lid = 0.12
        else:
            px, py, lid = 0, -6, 0.35
        m = lambda s: replace(s, pupil_x=px, pupil_y=py, lid_upper=max(s.lid_upper, lid))
        return PanelSpec(m(left)), PanelSpec(m(right))


class Googly(Theme):
    name, hold, rate = "googly", 10.0, 30.0
    G = 420.0

    def start(self):
        self.pos = [[0.0, 0.0], [0.0, 0.0]]
        self.vel = [[self.rng.uniform(-150, 150), -200.0], [self.rng.uniform(-150, 150), -200.0]]
        self.last = self.ctx.now
        self.next_kick = 1.0 + self.rng.uniform(0.5, 1.5)

    def impulse(self, dx, dy):
        for v in self.vel:
            v[0] += dx
            v[1] += dy

    def apply(self, t, left, right):
        now = self.ctx.now
        dt = min(max(now - self.last, 0.0), 0.05)
        self.last = now
        if t >= self.next_kick:                       # the duck waddles
            self.impulse(self.rng.uniform(-250, 250), self.rng.uniform(-350, -120))
            self.next_kick = t + self.rng.uniform(0.8, 2.0)
        limit = self.max_off + 0.1 * self.cfg.eye.pupil_r
        for p, v in zip(self.pos, self.vel):
            v[1] += self.G * dt
            p[0] += v[0] * dt
            p[1] += v[1] * dt
            d = math.hypot(p[0], p[1])
            if d > limit:
                nx, ny = p[0] / d, p[1] / d
                p[0], p[1] = nx * limit, ny * limit
                vn = v[0] * nx + v[1] * ny
                if vn > 0:
                    v[0] -= (1 + 0.55) * vn * nx
                    v[1] -= (1 + 0.55) * vn * ny
                    v[0] *= 0.92
                    v[1] *= 0.92
        m = lambda s, i: replace(s, pupil_x=self.pos[i][0], pupil_y=self.pos[i][1], pupil_scale=0.9)
        return PanelSpec(m(left, 0)), PanelSpec(m(right, 1))


# ---- cartoon classics -------------------------------------------------------------

class Hearts(Theme):
    name, hold, rate = "hearts", 5.0, 15.0

    def start(self):
        self.p = [Particles(), Particles()]
        self.next_spawn = [0.0, 0.2]

    def apply(self, t, left, right):
        now = self.ctx.now
        beat = 1.12 + 0.10 * math.sin(2 * math.pi * 1.3 * t) + (0.08 if (t * 1.3) % 1.0 < 0.12 else 0.0)
        out = []
        for i, s in enumerate((left, right)):
            st = replace(s, pupil_sprite="heart", pupil_scale=beat, lid_lower=max(s.lid_lower, 0.22))
            while t >= self.next_spawn[i]:
                born = now - (t - self.next_spawn[i])
                self.p[i].items.append(Particle("heart", self.rng.uniform(5, 10), self.C + s.pupil_x + self.rng.uniform(-30, 30),
                                                 self.C + s.pupil_y - self.cfg.eye.pupil_r * 0.6, self.rng.uniform(-6, 6),
                                                 -self.rng.uniform(45, 70), born, 1.6, sway=6, phase=self.rng.uniform(0, 6.28)))
                self.next_spawn[i] += self.rng.uniform(0.35, 0.6)
            out.append(PanelSpec(st, overlays=self.p[i].overlays(now)))
        return out[0], out[1]


class KnockedOut(Theme):
    name, hold, rate = "knockout", 6.0, 15.0

    def apply(self, t, left, right):
        out = []
        for s in (left, right):
            st = replace(s, pupil_sprite="x", pupil_scale=1.2, pupil_x=0, pupil_y=4, lid_upper=max(s.lid_upper, 0.1))
            ov = []
            for k in range(3):
                a = 2.2 * t + k * 2 * math.pi / 3
                ov += sprite_at("star", 7, self.C + 55 * math.cos(a), self.C - 72 + 13 * math.sin(a))
            out.append(PanelSpec(st, overlays=ov))
        return out[0], out[1]


class Dizzy(Theme):
    name, hold, rate = "dizzy", 6.0, 18.0

    def apply(self, t, left, right):
        f = self.frame(t) % pupil_sprites.FRAMES["spiral"]
        m = lambda s: replace(s, pupil_sprite="spiral", pupil_frame=f, pupil_scale=1.25,
                              pupil_x=14 * math.sin(2.5 * t), pupil_y=10 * math.cos(2.5 * t), lid_upper=max(s.lid_upper, 0.12))
        return PanelSpec(m(left)), PanelSpec(m(right))


class LaughCry(Theme):
    name, hold, rate = "laughcry", 5.0, 15.0

    def start(self):
        self.p = [Particles(), Particles()]
        self.next_spawn = [0.0, 0.1]

    def apply(self, t, left, right):
        now = self.ctx.now
        e = self.cfg.eye
        out = []
        for i, (side, s) in enumerate((("left", left), ("right", right))):
            st = replace(s, lid_lower=max(s.lid_lower, 0.5), lid_upper=max(s.lid_upper, 0.1), pupil_y=min(s.pupil_y, -4))
            while t >= self.next_spawn[i]:
                born = now - (t - self.next_spawn[i])
                sign = self.outer_sign(side)
                self.p[i].items.append(Particle("tear", self.rng.uniform(5, 8), self.C + sign * 0.8 * e.sclera_r, self.C + 5,
                                                 sign * self.rng.uniform(5, 18), 110, born, 0.8, ay=180, fade_from=0.75))
                self.next_spawn[i] += self.rng.uniform(0.12, 0.25)
            out.append(PanelSpec(st, overlays=self.p[i].overlays(now)))
        return out[0], out[1]


class Sweat(Theme):
    name, hold, rate = "sweat", 5.0, 15.0

    def start(self):
        self.targets = [(self.rng.uniform(-1, 1) * 14, self.rng.uniform(-1, 1) * 8) for _ in range(12)]

    def apply(self, t, left, right):
        i = int(t / 0.35)
        tx, ty = self.targets[i % 12]
        out = []
        for side, s in (("left", left), ("right", right)):
            st = replace(s, pupil_x=tx, pupil_y=ty, lid_upper=max(s.lid_upper, 0.15), lid_tilt=self.tilt_for(side, -0.2))
            ov = []
            if t < 1.9:
                p = (t / 1.9) ** 1.8
                y = self.C - 50 + 105 * p
                ov = sprite_at("tear", 11, self.C + self.outer_sign(side) * 93, y)
            out.append(PanelSpec(st, overlays=ov))
        return out[0], out[1]


class Anime(Theme):
    name, hold, rate = "anime", 6.0, 3.0

    def apply(self, t, left, right):
        f = self.frame(t)
        out = []
        for s in (left, right):
            st = replace(s, pupil_sprite="anime", pupil_scale=1.35, lid_lower=max(s.lid_lower, 0.08))
            ov = sprite_at("blush", 22, self.C, self.C + 72)
            if f % 2 == 0:
                ov += sprite_at("sparkle", 9, self.C - 60, self.C - 55)
            else:
                ov += sprite_at("sparkle", 7, self.C + 65, self.C - 40)
            out.append(PanelSpec(st, overlays=ov))
        return out[0], out[1]


class CatEyes(Theme):
    name, hold, rate = "cateyes", 8.0, 4.0

    def apply(self, t, left, right):
        light = self.ctx.params.get("light")
        light = float(light) if light is not None else 0.5 + 0.5 * math.sin(t * 0.8)
        f = int(round((1.0 - light) * (pupil_sprites.FRAMES["slit"] - 1)))
        m = lambda s: replace(s, pupil_sprite="slit", pupil_frame=f, pupil_scale=1.15)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Zzz(Theme):
    name, hold, rate = "zzz", 8.0, 12.0

    def start(self):
        self.p = [Particles(), Particles()]
        self.next_spawn = [0.0, 0.45]
        if self.anim:
            self.anim.blinks_enabled = False

    def apply(self, t, left, right):
        now = self.ctx.now
        out = []
        for i, s in enumerate((left, right)):
            st = replace(s, lid_upper=1.0, lid_lower=1.0, pupil_x=0, pupil_y=0)
            while t >= self.next_spawn[i]:
                born = now - (t - self.next_spawn[i])
                self.p[i].items.append(Particle("z", 7, self.C + 28, self.C - 30, 12, -32, born, 2.2, sway=5,
                                                 phase=self.rng.uniform(0, 6.28), grow=3.0, fade_from=0.6))
                self.next_spawn[i] += 0.9
            out.append(PanelSpec(st, overlays=self.p[i].overlays(now)))
        return out[0], out[1]


class Monocle(Theme):
    name, hold, continuous = "monocle", 6.0, False

    def start(self):
        e = self.cfg.eye
        R = e.sclera_r + e.outline_w
        self.ring = sprites.ring(float(R + 8), float(R + 1))
        self.half = self.ring.shape[0] // 2

    def apply(self, t, left, right):
        l = replace(left, lid_upper=max(left.lid_upper, 0.4), lid_lower=max(left.lid_lower, 0.2))
        r = replace(right, lid_upper=0.0, lid_tilt=self.tilt_for("right", 0.1))
        ov = [(self.ring, (225, 165, 30), int(self.C) - self.half, int(self.C) - self.half)]
        return PanelSpec(l), PanelSpec(r, overlays=ov)


# ---- duck-specific -----------------------------------------------------------------

class Bread(Theme):
    name, hold, continuous = "bread", 5.0, False

    def start(self):
        if self.anim:
            self.anim.blink_interval = (0.35, 0.7)

    def apply(self, t, left, right):
        m = lambda s: replace(s, pupil_sprite="bread", pupil_scale=1.35, lid_lower=max(s.lid_lower, 0.35))
        return PanelSpec(m(left)), PanelSpec(m(right))


class CatAlert(Theme):
    name, hold, rate = "catalert", 6.0, 15.0

    def apply(self, t, left, right):
        f = self.frame(t)
        tremble = 1 if f % 2 else -1
        px = 25 * math.sin(0.7 * t) + tremble
        m = lambda s: replace(s, pupil_scale=0.35, pupil_x=px, pupil_y=-4, lid_upper=0.0, lid_lower=0.0)
        return PanelSpec(m(left)), PanelSpec(m(right))


class RubberDuck(Theme):
    name, hold, rate = "rubberduck", 8.0, 15.0

    def apply(self, t, left, right):
        nod = 8 * math.sin(2 * math.pi * 0.5 * t)
        m = lambda s: replace(s, pupil_sprite="duck", pupil_scale=1.3, pupil_y=nod, lid_upper=max(s.lid_upper, 0.1))
        return PanelSpec(m(left)), PanelSpec(m(right))


class Migration(Theme):
    name, hold, continuous = "migration", 8.0, False

    def start(self):
        if self.anim:
            self.anim.blink_interval = (4.0, 7.0)

    def apply(self, t, left, right):
        m = lambda s: replace(s, pupil_x=32, pupil_y=-30, lid_upper=max(s.lid_upper, 0.25))
        return PanelSpec(m(left)), PanelSpec(m(right))


# ---- status glances --------------------------------------------------------------

def _hub_state(theme, name, default):
    st = getattr(theme.hub, "state", None)
    v = getattr(st, name, None) if st is not None else None
    return default if v is None else v


class Clock(Theme):
    name, hold, continuous = "clock", 3.0, False

    def start(self):
        hour = self.ctx.params.get("hour")
        if hour is None:
            hour = _hub_state(self, "hour", None)
        if hour is None:
            import time as _t
            lt = _t.localtime()
            hh, mm = lt.tm_hour, lt.tm_min
        else:
            hh, mm = int(hour) % 24, int((float(hour) % 1) * 60)
        self.sprite = f"clock:{hh:02d}:{mm:02d}"

    def apply(self, t, left, right):
        m = lambda s: replace(s, pupil_sprite=self.sprite, pupil_scale=1.3, pupil_x=0, pupil_y=0)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Weather(Theme):
    name, hold, continuous = "weather", 3.0, False

    def start(self):
        kind = self.ctx.params.get("kind") or _hub_state(self, "weather", "sun")
        self.sprite = f"weather:{kind}"
        self.kind = kind

    def apply(self, t, left, right):
        lower = 0.3 if self.kind == "sun" else 0.0
        upper = 0.25 if self.kind in ("rain", "storm") else 0.0
        brow = -3 if self.kind == "sun" else 4 if self.kind in ("rain", "storm") else 0
        m = lambda s: replace(s, pupil_sprite=self.sprite, pupil_scale=1.35, pupil_x=0, pupil_y=0,
                              lid_lower=max(s.lid_lower, lower), lid_upper=max(s.lid_upper, upper), brow_y=brow)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Compass(Theme):
    name, hold, rate = "compass", 3.0, 10.0

    def start(self):
        self.heading = float(self.ctx.params.get("heading", _hub_state(self, "heading", 0.0)) or 0.0)

    def animating(self, t):
        return t < 1.0

    def apply(self, t, left, right):
        wobble = 25 * math.exp(-t * 3) * math.sin(t * 20) if t < 1.0 else 0.0
        name = f"compass:{int(round(self.heading + wobble)) % 360}"
        m = lambda s: replace(s, pupil_sprite=name, pupil_scale=1.3, pupil_x=0, pupil_y=0)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Wifi(Theme):
    name, hold, continuous = "wifi", 2.5, False

    def start(self):
        self.bars = int(self.ctx.params.get("bars", _hub_state(self, "wifi", 3)))

    def apply(self, t, left, right):
        sad = self.bars == 0
        m = lambda s, side: replace(s, pupil_sprite=f"wifi:{self.bars}", pupil_scale=1.3, pupil_x=0, pupil_y=0,
                                    lid_upper=max(s.lid_upper, 0.25 if sad else 0.0), brow_y=2 if sad else -2,
                                    brow_tilt=self.tilt_for(side, -10) if sad else 0.0)
        return PanelSpec(m(left, "left")), PanelSpec(m(right, "right"))


class Listening(Theme):
    name, hold, rate = "listening", 60.0, 15.0

    def apply(self, t, left, right):
        level = float(_hub_state(self, "sound", 0.0))
        scale = round(1.1 + 0.3 * level + 0.03 * math.sin(t * 6), 2)
        m = lambda s: replace(s, pupil_sprite="mic", pupil_scale=scale, pupil_x=0, pupil_y=-2, brow_y=-3)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Thinking(Theme):
    name, hold, rate = "thinking", 60.0, 6.0

    def apply(self, t, left, right):
        f = self.frame(t)
        m = lambda s, sign: replace(s, pupil_sprite="dots", pupil_frame=f, pupil_scale=1.15, pupil_x=-16, pupil_y=-20,
                                    lid_upper=max(s.lid_upper, 0.1), brow_y=-2 + (3 if sign > 0 else -3))
        return PanelSpec(m(left, -1)), PanelSpec(m(right, 1))


class Flash(Theme):
    name, hold, rate, duration = "flash", 0.7, 30.0, 0.65

    def start(self):
        c = self.ctx.params.get("colour") or (90, 200, 255)
        self.colour = tuple(int(v) for v in c)

    def apply(self, t, left, right):
        k = max(0.0, 1.0 - t / 0.6)
        base = self.cfg.iris.colour
        col = tuple(int(round(b + (c - b) * k)) for b, c in zip(base, self.colour))
        m = lambda s: replace(s, iris_colour=col)
        return PanelSpec(m(left)), PanelSpec(m(right))


# ---- interaction games --------------------------------------------------------------

class Staring(Theme):
    name, hold, rate = "staring", 20.0, 15.0

    def start(self):
        if self.anim:
            self.anim.blinks_enabled = False
        self.t_lose = self.rng.uniform(8.0, 14.0)
        self.user_blinked_at: float | None = None

    def animating(self, t):
        return True

    def apply(self, t, left, right):
        now = self.ctx.now
        if self.user_blinked_at is None and self.hub is not None and t < self.t_lose:
            ev = self.hub.recent("user_blink", self.ctx.now - t)
            if ev:
                self.user_blinked_at = ev[0].t - (now - t)
        f = self.frame(t)
        out = []
        for side, s in (("left", left), ("right", right)):
            if self.user_blinked_at is not None:            # the duck wins: smug
                st = replace(s, lid_upper=0.12, lid_lower=0.42, pupil_scale=1.0, pupil_x=0, pupil_y=-3, brow_y=-4,
                             brow_tilt=self.tilt_for(side, 6))
            elif t < self.t_lose:                            # tension builds
                k = t / self.t_lose
                tremble = (1 if f % 2 else -1) * int(1 + 3 * k * k)
                st = replace(s, lid_upper=0.0, lid_lower=0.0, pupil_scale=round(0.9 - 0.1 * k, 2), pupil_x=tremble,
                             pupil_y=0, brow_y=-4 - 4 * k, brow_tilt=self.tilt_for(side, 8 * k))
            else:                                            # the duck loses dramatically
                d = t - self.t_lose
                if d < 0.35 or 0.45 <= d < 0.75:
                    st = replace(s, lid_upper=1.0, lid_lower=1.0, brow_y=4)
                else:
                    st = replace(s, lid_upper=0.1, lid_lower=0.5, pupil_y=6, pupil_x=0, brow_y=-2)
            out.append(st)
        if self.user_blinked_at is not None and t > (self.user_blinked_at + 3.0):
            self.done = True
        if t > self.t_lose + 3.0:
            self.done = True
        return PanelSpec(out[0]), PanelSpec(out[1])


class FollowDot(Theme):
    name, hold, rate = "followdot", 60.0, 15.0
    TARGETS = [(-160.0, 0.0), (160.0, 0.0), (0.0, -130.0)]
    ROUND_S, HOLD_S = 8.0, 0.5

    def start(self):
        self.round = 0
        self.round_t0 = 0.0
        self.in_zone_since: float | None = None
        self.result: str | None = None       # "win" | "miss"
        self.result_t0 = 0.0
        self.hearts = Particles()

    def animating(self, t):
        return True

    def apply(self, t, left, right):
        now = self.ctx.now
        if self.round >= len(self.TARGETS):
            self.done = True
            return PanelSpec(left), PanelSpec(right)
        tx, ty = self.TARGETS[self.round]
        face = _hub_state(self, "face", None)
        if self.result is None:
            near = face is not None and math.hypot(face.x_mm - tx, face.y_mm - ty) < 80.0
            if near:
                self.in_zone_since = self.in_zone_since if self.in_zone_since is not None else t
                if t - self.in_zone_since >= self.HOLD_S:
                    self.result, self.result_t0 = "win", t
                    for i in range(2):
                        for _ in range(6):
                            self.hearts.items.append(Particle("heart", self.rng.uniform(4, 8), self.C + self.rng.uniform(-40, 40),
                                                              self.C + 20, self.rng.uniform(-20, 20), -self.rng.uniform(50, 90),
                                                              now, 1.2, sway=4, phase=float(i)))
            else:
                self.in_zone_since = None
            if t - self.round_t0 > self.ROUND_S and self.result is None:
                self.result, self.result_t0 = "miss", t
        else:
            if t - self.result_t0 > (1.4 if self.result == "win" else 1.0):
                self.round += 1
                self.round_t0 = t
                self.result = None
                self.in_zone_since = None
        # the duck looks at the target and waits; brows up as a cue
        max_off = self.max_off
        px = max(-max_off, min(max_off, tx / 3.0))
        py = max(-max_off, min(max_off, ty / 3.0))
        out = []
        for side, s in (("left", left), ("right", right)):
            if self.result == "win":
                st = replace(s, lid_lower=0.45, lid_upper=0.08, pupil_x=0, pupil_y=-4, brow_y=-4, pupil_scale=1.05)
            elif self.result == "miss":
                st = replace(s, lid_upper=0.3, pupil_x=0, pupil_y=6, brow_y=-1, brow_tilt=self.tilt_for(side, -12))
            else:
                pulse = 1.0 + 0.04 * math.sin(t * 5)
                st = replace(s, pupil_x=px, pupil_y=py, brow_y=-7, pupil_scale=round(pulse, 2), lid_upper=0.0)
            out.append(st)
        ovs = self.hearts.overlays(now) if self.result == "win" else []
        l_ov = [o for o, p in zip(ovs, self.hearts.items) if p.phase == 0.0]
        r_ov = [o for o, p in zip(ovs, self.hearts.items) if p.phase == 1.0]
        return PanelSpec(out[0], overlays=l_ov), PanelSpec(out[1], overlays=r_ov)


class Peekaboo(Theme):
    name, hold, rate = "peekaboo", 60.0, 15.0

    def start(self):
        self.uncovered_at: float | None = None

    def animating(self, t):
        return self.uncovered_at is not None and t - self.uncovered_at < 1.6

    def apply(self, t, left, right):
        covered = bool(_hub_state(self, "camera_covered", False))
        if self.hub is not None and self.uncovered_at is None:
            ev = self.hub.recent("uncovered", self.ctx.now - min(t, 0.2))
            if ev:
                self.uncovered_at = t
        if covered:
            self.uncovered_at = None
            m = lambda s: replace(s, lid_upper=1.0, lid_lower=1.0, brow_y=2)
        elif self.uncovered_at is not None and t - self.uncovered_at < 0.5:
            m = lambda s: replace(s, lid_upper=0.0, lid_lower=0.0, pupil_scale=0.7, brow_y=-10, pupil_x=0, pupil_y=0)
        elif self.uncovered_at is not None and t - self.uncovered_at < 1.6:
            d = t - self.uncovered_at - 0.5
            bounce = -8 * abs(math.sin(d * 9)) * max(0.0, 1 - d)
            m = lambda s: replace(s, lid_lower=0.45, lid_upper=0.08, pupil_y=bounce, pupil_x=0, brow_y=-4)
        else:
            m = lambda s: replace(s, brow_y=-2)
        return PanelSpec(m(left)), PanelSpec(m(right))


class Mirror(Theme):
    name, hold, rate = "mirror", 60.0, 15.0

    def start(self):
        self.last_blink_t = -1.0
        if self.anim:
            self.anim.blinks_enabled = False

    def animating(self, t):
        return True

    def apply(self, t, left, right):
        face = _hub_state(self, "face", None)
        if self.hub is not None and self.anim is not None:
            for ev in self.hub.recent("user_blink", self.ctx.now - 0.2):
                if ev.t > self.last_blink_t:
                    self.last_blink_t = ev.t
                    self.anim.blink(self.ctx.now)
        if face is not None:
            px = max(-self.max_off, min(self.max_off, face.x_mm / 3.0))
            py = max(-self.max_off, min(self.max_off, face.y_mm / 3.0))
            m = lambda s: replace(s, pupil_x=px, pupil_y=py)
        else:
            m = lambda s: s
        return PanelSpec(m(left)), PanelSpec(m(right))


class Yawn(Theme):
    name, hold, rate, duration = "yawn", 2.7, 15.0, 2.6

    def apply(self, t, left, right):
        f = self.frame(t)
        if t < 0.9:
            k = ease(t / 0.9)
            m = lambda s: replace(s, lid_upper=0.75 * k, lid_lower=0.6 * k, pupil_y=-20 * k, pupil_x=0, brow_y=-8 * k)
        elif t < 1.8:
            tr = 1 if f % 2 else -1
            m = lambda s: replace(s, lid_upper=0.75, lid_lower=0.6 + 0.02 * tr, pupil_y=-20, pupil_x=0, brow_y=-8)
        elif t < 2.2:
            k = ease((t - 1.8) / 0.4)
            m = lambda s: replace(s, lid_upper=0.75 * (1 - k), lid_lower=0.6 * (1 - k), pupil_y=-20 * (1 - k), pupil_x=0,
                                  pupil_scale=1.0 + 0.1 * k, brow_y=-8 + 6 * k)
        else:
            shake = (4 if f % 2 else -4) * (1 - (t - 2.2) / 0.4)
            m = lambda s: replace(s, pupil_x=shake, pupil_scale=1.1 - 0.1 * (t - 2.2) / 0.4)
        return PanelSpec(m(left)), PanelSpec(m(right))


# =============================================================================
THEME_CLASSES: list[type[Theme]] = [
    Hal, Terminator, Aperture, Eve, Matrix, Spiral, Pirate, Sunglasses, Laser,
    Dollar, Slot, Dice, EightBall, PokerFace,
    Debate, Campaign, Election, Filibuster, Diplomat, TaxSeason,
    Boot, Crt, Buffering, BlueScreen, NotFound, Battery, EyeRoll, Googly,
    Hearts, KnockedOut, Dizzy, LaughCry, Sweat, Anime, CatEyes, Zzz, Monocle,
    Bread, CatAlert, RubberDuck, Migration,
    Clock, Weather, Compass, Wifi, Listening, Thinking, Flash,
    Staring, FollowDot, Peekaboo, Mirror, Yawn,
]
GLANCES = ["clock", "weather", "compass", "wifi", "battery", "listening", "thinking"]
GAMES = ["staring", "followdot", "peekaboo", "mirror"]
REGISTRY: dict[str, type[Theme]] = {c.name: c for c in THEME_CLASSES}
THEMES: list[str] = [c.name for c in THEME_CLASSES]
SURPRISES = [n for n in THEMES if n not in GLANCES + GAMES + ["flash", "filibuster", "boot", "yawn"]]
DEFAULT_HOLD = {c.name: c.hold for c in THEME_CLASSES}


class ThemeController:
    def __init__(self, cfg: Config, seed: int | None = None, anim=None, scenes=None, hub=None):
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.anim = anim
        self.scenes = scenes
        self.hub = hub
        self.theme: Theme | None = None
        self.t0 = 0.0
        self.ends_at = 0.0
        self.needs_full_redraw = False   # set on start/stop; the app clears it after a full repaint
        self._last_key: tuple | None = None
        self._saved: tuple | None = None
        self.surprise = False
        self.surprise_interval = 90.0
        self.next_surprise = 0.0

    @property
    def active(self) -> str | None:
        return self.theme.name if self.theme else None

    # ---- commands -----------------------------------------------------
    def start(self, name: str, now: float, hold_s: float | None = None, params: dict | None = None, sources=None):
        if name in ("off", "none", ""):
            self.stop(now)
            return
        if name not in REGISTRY:
            raise KeyError(name)
        self.stop(now)
        if self.anim is not None:
            self._saved = (self.anim.idle, self.anim.blinks_enabled, self.anim.blink_interval)
        ctx = Ctx(self.cfg, self.rng, self.anim, self.scenes, sources, params or {}, now, self.hub)
        self.theme = REGISTRY[name](ctx)
        self.t0 = now
        self.ends_at = now + (self.theme.hold if hold_s is None else hold_s)
        self.theme.start()
        self.needs_full_redraw = True

    def stop(self, now: float):
        if self.theme is None:
            return
        self.theme.stop()
        self.theme = None
        if self.anim is not None and self._saved is not None:
            idle, blinks, interval = self._saved
            self.anim.set_idle(idle, now)
            self.anim.blinks_enabled = blinks
            self.anim.blink_interval = interval
            self._saved = None
        self.needs_full_redraw = True
        if self.surprise:
            self._schedule_surprise(now)

    def cycle(self, now: float, step: int = 1, **kw) -> str:
        names = THEMES + ["off"]
        i = names.index(self.active) if self.active in names else len(names) - 1
        name = names[(i + step) % len(names)]
        self.start(name, now, **kw)
        return name

    def on_input(self, now: float):
        if self.theme is not None and self.theme.cancel_on_input:
            self.stop(now)

    def impulse(self, dx: float, dy: float):
        if self.theme is not None:
            self.theme.impulse(dx, dy)

    def set_surprise(self, on: bool, now: float, interval_s: float | None = None):
        self.surprise = on
        if interval_s:
            self.surprise_interval = interval_s
        if on:
            self._schedule_surprise(now)

    def _schedule_surprise(self, now: float):
        self.next_surprise = now + self.rng.uniform(0.5, 1.5) * self.surprise_interval

    # ---- output -------------------------------------------------------
    def apply(self, now: float, left: EyeState, right: EyeState) -> tuple[PanelSpec, PanelSpec, bool]:
        if self.theme is not None and (now >= self.ends_at or self.theme.done):
            self.stop(now)
        if self.theme is None and self.surprise and now >= self.next_surprise:
            self.start(self.rng.choice(SURPRISES), now)
        if self.theme is None:
            specs = (PanelSpec(left), PanelSpec(right))
            key: tuple = ("off", left, right)
        else:
            self.theme.ctx.now = now
            sl, sr = self.theme.apply(now - self.t0, left, right)
            sl.state, sr.state = _q(sl.state), _q(sr.state)
            specs = (sl, sr)
            key = (self.theme.name, sl.scene, sl.state, self._ov_key(sl.overlays), sr.scene, sr.state, self._ov_key(sr.overlays))
        changed = key != self._last_key or self.needs_full_redraw
        self._last_key = key
        return specs[0], specs[1], changed

    @staticmethod
    def _ov_key(ovs: list[Overlay]) -> tuple:
        return tuple((o[2], o[3], o[0].shape, o[1], float(o[0].max()) if o[0].size and o[0].shape[0] < 40 else 1.0) for o in ovs)

    def animating(self, now: float) -> bool:
        return self.theme is not None and self.theme.animating(now - self.t0)

    def next_wake(self, now: float) -> float:
        if self.theme is None:
            return self.next_surprise if self.surprise else float("inf")
        if self.animating(now):
            return now + 1.0 / self.theme.rate
        return self.ends_at
