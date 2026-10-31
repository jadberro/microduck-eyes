"""Full-panel takeovers: HAL 9000, Terminator, pirate patch, blue screen, boot sequence,
mechanical aperture (drawn over the eye), Eve slit, CRT power-off.

render(name, frame, extra, base) -> (frame, dirty). `extra` is a small hashable tuple of
parameters; `base` is an eye frame to draw over for scenes that sit on top of the eye.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from ..config import Config
from . import sprites
from .font import text_mask, text_size

Rect = tuple[int, int, int, int]

HAL_FRAMES = 8
CRT_SQUEEZES = (0.7, 0.45, 0.28, 0.16, 0.08, 0.035)
CRT_DOTS = (26, 16, 8, 3)
APERTURE_FRAMES = 12
BOOT_LINES = [
    ("MICRODUCK BIOS V1.0", (120, 255, 140)),
    ("CPU: 4X A53 QUACK", (210, 210, 210)),
    ("MEM: 512MB OK", (210, 210, 210)),
    ("EYES: 2 DETECTED", (210, 210, 210)),
    ("BREAD: NOT FOUND", (255, 170, 80)),
    ("LOADING CUTENESS", (120, 255, 140)),
]
BOOT_TEXT_FRAMES = len(BOOT_LINES) + 1
BOOT_BAR_FRAMES = 14
BOOT_FRAMES = BOOT_TEXT_FRAMES + BOOT_BAR_FRAMES


def _put_text(frame: np.ndarray, text: str, x: int, y: int, colour, scale: int = 1):
    m = text_mask(text, scale)
    sprites.blend(frame, x, y, m, colour)


class SceneRenderer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.size = cfg.panel.size
        self.c = self.size / 2.0 - 0.5
        self._hal: list[np.ndarray] | None = None
        self._crt: list[np.ndarray] = []
        self._cache: dict[tuple, np.ndarray] = {}
        self._buf = np.zeros((self.size, self.size, 3), np.uint8)
        ys, xs = np.mgrid[0:self.size, 0:self.size].astype(np.float32)
        self._xs, self._ys = xs - self.c, ys - self.c
        self._rho = np.hypot(self._xs, self._ys)

    def _cached(self, key: tuple, build):
        f = self._cache.get(key)
        if f is None:
            f = build()
            if len(self._cache) > 96:
                self._cache.clear()
            self._cache[key] = f
        return f

    def full(self) -> Rect:
        return (0, 0, self.size, self.size)

    # ---- HAL 9000 -------------------------------------------------------
    def _build_hal(self) -> list[np.ndarray]:
        n = self.size
        rho = self._rho
        lens_r = 100.0
        g = np.clip(1.0 - rho / lens_r, 0.0, 1.0) ** 2.2
        faceplate = (rho >= lens_r) & (rho < lens_r + 9)
        dot = np.clip(7.5 - rho, 0.0, 1.0)
        frames = []
        for k in range(HAL_FRAMES):
            b = 0.72 + 0.28 * (0.5 - 0.5 * np.cos(2 * np.pi * k / HAL_FRAMES))
            f = np.zeros((n, n, 3), np.float32)
            f[..., 0] = (55 + 200 * g) * b
            f[..., 1] = (6 + 70 * g ** 3) * b
            f[..., 2] = (4 + 30 * g ** 4) * b
            f[rho >= lens_r] = 0
            f[faceplate] = (38, 38, 42)
            f = f * (1 - dot[..., None]) + np.array((255, 225, 130), np.float32) * dot[..., None]
            frames.append(np.clip(f + 0.5, 0, 255).astype(np.uint8))
        return frames

    def hal(self, frame: int) -> tuple[np.ndarray, Rect]:
        if self._hal is None:
            self._hal = self._build_hal()
        c = int(self.c)
        return self._hal[frame % HAL_FRAMES], (c - 101, c - 101, c + 103, c + 103)

    # ---- Terminator -----------------------------------------------------
    @lru_cache(maxsize=1)
    def _glow(self):
        n = 141
        ys, xs = np.mgrid[0:n, 0:n] - 70
        rho = np.hypot(xs, ys)
        return np.clip(1.0 - rho / 70.0, 0, 1).astype(np.float32) ** 1.8

    def terminator(self, frame: int, extra: tuple) -> tuple[np.ndarray, Rect]:
        px, py = extra[:2]
        f = self._buf
        f[...] = (6, 4, 4)
        cx, cy = int(round(self.c + px)), int(round(self.c + py))
        glow = self._glow()
        sprites.blend(f, cx - 70, cy - 70, glow, (255, 40, 30))
        core = sprites.disc(13.0)
        sprites.blend(f, cx - core.shape[0] // 2, cy - core.shape[0] // 2, core, (255, 210, 200))
        ring = sprites.ring(40.0, 37.5)
        h = ring.shape[0] // 2
        sprites.blend(f, cx - h, cy - h, ring * 0.9, (240, 240, 240))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):       # ticks outside the ring
            x0 = cx + dx * 42 + (-7 if dx < 0 else 0) if dx else cx - 1
            y0 = cy + dy * 42 + (-7 if dy < 0 else 0) if dy else cy - 1
            w, hh = (8, 2) if dx else (2, 8)
            f[max(y0, 0):max(y0 + hh, 0), max(x0, 0):max(x0 + w, 0)] = (240, 240, 240)
        f[cy - 1:cy + 1, cx - 6:cx + 6] = (240, 240, 240)
        f[cy - 6:cy + 6, cx - 1:cx + 1] = (240, 240, 240)
        rng = np.random.default_rng(frame // 2)
        for i in range(3):
            _put_text(f, f"{rng.integers(0, 0xFFFF):04X} {rng.integers(0, 999):03d}", 56, 26 + i * 10, (255, 90, 80))
        _put_text(f, "SCAN MODE", 56, 58, (255, 150, 140))
        label = "TARGET LOCK" if (frame // 4) % 2 == 0 else "ANALYZING"
        w, _ = text_size(label, 1)
        _put_text(f, label, int(self.c - w / 2), 190, (255, 220, 220))
        return f, self.full()

    # ---- pirate eye patch ------------------------------------------------
    def pirate(self, frame: int) -> tuple[np.ndarray, Rect]:
        def build():
            e, c = self.cfg.eye, self.cfg.colours
            f = np.empty((self.size, self.size, 3), np.uint8)
            f[...] = c.face
            R = e.sclera_r + e.outline_w
            strap = np.abs(self._ys + 0.62 * R - 0.28 * self._xs) < 7
            f[strap] = (35, 28, 22)
            patch = sprites.disc(float(R + 2))
            h = patch.shape[0] // 2
            sprites.blend(f, int(self.c) - h, int(self.c) - h, patch, (28, 24, 22))
            sheen = sprites.ring(float(R - 10), float(R - 16))
            h2 = sheen.shape[0] // 2
            sprites.blend(f, int(self.c) - h2, int(self.c) - h2, sheen * 0.25, (90, 85, 80))
            return f
        return self._cached(("pirate",), build), self.full()

    # ---- blue screen ------------------------------------------------------
    def bsod(self, frame: int) -> tuple[np.ndarray, Rect]:
        pct = min(frame * 3, 100)

        def build():
            f = np.empty((self.size, self.size, 3), np.uint8)
            f[...] = (0, 120, 215)
            c = int(self.c)
            _put_text(f, ":(", c - 40, c - 92, (255, 255, 255), 6)
            lines = ["YOUR DUCK RAN", "INTO A PROBLEM", "AND NEEDS TO", "RESTART"]
            y = c - 34
            for line in lines:
                w, h = text_size(line, 2)
                _put_text(f, line, c - w // 2, y, (255, 255, 255), 2)
                y += h + 5
            msg = f"{pct}% COMPLETE"
            w, _ = text_size(msg, 1)
            _put_text(f, msg, c - w // 2, y + 6, (220, 235, 255), 1)
            return f
        return self._cached(("bsod", pct), build), self.full()

    # ---- boot sequence ----------------------------------------------------
    def boot(self, frame: int, extra: tuple) -> tuple[np.ndarray, Rect]:
        side = extra[0] if extra else 0

        def build():
            f = np.zeros((self.size, self.size, 3), np.uint8)
            c = int(self.c)
            if frame < BOOT_TEXT_FRAMES:
                nlines = min(frame + 1, len(BOOT_LINES))
                y = 58
                for text, colour in BOOT_LINES[:nlines]:
                    _put_text(f, text, 62, y, colour, 1)
                    y += 12
                if frame % 2 == 0:
                    f[y:y + 7, 62:67] = (210, 210, 210)      # blinking cursor
            else:
                k = frame - BOOT_TEXT_FRAMES
                p = min(k / (BOOT_BAR_FRAMES - 1), 1.0)
                _put_text(f, "OPENING EYES", 62, c - 30, (120, 255, 140), 1)
                # The bar spans both panels: left half on the left panel, right half on the right one.
                y0, y1 = c - 8, c + 8
                if side == 0:
                    x0, x1 = c - 70, self.size
                    f[y0:y1, x0:x1] = (60, 60, 70)
                    fill = int((x1 - x0) * min(p * 2, 1.0))
                    f[y0 + 2:y1 - 2, x0 + 2:x0 + 2 + max(fill - 4, 0)] = (120, 255, 140)
                else:
                    x0, x1 = 0, c + 70
                    f[y0:y1, x0:x1] = (60, 60, 70)
                    fill = int((x1 - x0) * max(min((p - 0.5) * 2, 1.0), 0.0))
                    f[y0 + 2:y1 - 2, x0:x0 + max(fill - 2, 0)] = (120, 255, 140)
                pct = f"{int(p * 100):3d}%"
                _put_text(f, pct, c - 10, c + 16, (210, 210, 210), 1)
            return f
        return self._cached(("boot", frame, side), build), self.full()

    # ---- mechanical aperture over the eye ------------------------------------
    @lru_cache(maxsize=APERTURE_FRAMES)
    def _aperture_masks(self, frame: int):
        """(blade index map uint8, coverage alpha float32) for a closure step."""
        p = frame / (APERTURE_FRAMES - 1)
        d = (1.0 - p) * 126.0                      # inscribed radius of the opening; fully open clears the panel
        rot = p * np.radians(28.0)
        s = []
        for i in range(6):
            th = rot + i * np.pi / 3
            s.append(self._xs * np.cos(th) + self._ys * np.sin(th) - d)
        s = np.stack(s)                             # (6, H, W)
        order = np.argsort(-s, axis=0)
        top = np.take_along_axis(s, order[:1], axis=0)[0]
        second = np.take_along_axis(s, order[1:2], axis=0)[0]
        idx = order[0].astype(np.uint8)
        alpha = np.clip(top + 0.5, 0.0, 1.0).astype(np.float32)
        seam = (np.abs(top - second) < 1.2) & (top > 0)
        idx[seam] = 6                               # seam colour
        return idx, alpha

    def aperture(self, frame: int, base: np.ndarray | None) -> tuple[np.ndarray, Rect]:
        idx, alpha = self._aperture_masks(min(frame, APERTURE_FRAMES - 1))
        palette = np.array([(98, 101, 112), (82, 85, 95), (108, 111, 122), (88, 91, 101),
                            (102, 105, 116), (78, 81, 90), (30, 30, 36)], np.float32)
        colours = palette[idx]
        src = base.astype(np.float32) if base is not None else np.zeros((self.size, self.size, 3), np.float32)
        a = alpha[..., None]
        out = src * (1 - a) + colours * a
        self._buf[...] = (out + 0.5).astype(np.uint8)
        return self._buf, self.full()

    # ---- Eve ----------------------------------------------------------------
    def eve(self, frame: int, extra: tuple) -> tuple[np.ndarray, Rect]:
        tilt, closure = extra[:2]

        def build():
            f = np.empty((self.size, self.size, 3), np.uint8)
            f[...] = (236, 239, 246)
            ang = np.arctan(float(tilt)) * 0.8
            ca, sa = np.cos(ang), np.sin(ang)
            u = self._xs * ca + self._ys * sa
            v = -self._xs * sa + self._ys * ca
            a = 0.78 * self.cfg.eye.sclera_r
            b = max(0.26 * self.cfg.eye.sclera_r * (1.0 - float(closure)), 2.0)
            q = (u / a) ** 2 + (v / b) ** 2
            glow = np.clip(1.6 - q, 0, 1) ** 2 * 0.5
            core = np.clip(1.0 - q, 0, 1)
            core = np.clip(core * 6, 0, 1)
            col = np.array((80, 170, 255), np.float32)
            out = f.astype(np.float32)
            out = out * (1 - glow[..., None]) + col * glow[..., None]
            out = out * (1 - core[..., None]) + np.array((70, 150, 255), np.float32) * core[..., None]
            # faint dark edge of the face plate
            rim = (self._rho > 112) & (self._rho < 120)
            out[rim] = (205, 210, 220)
            return np.clip(out + 0.5, 0, 255).astype(np.uint8)
        return self._cached(("eve", round(float(tilt), 2), round(float(closure), 2)), build), self.full()

    # ---- CRT power-off --------------------------------------------------
    def prepare_crt(self, source: np.ndarray) -> int:
        n = self.size
        c = n // 2
        frames: list[np.ndarray] = [source.copy()]
        rows = np.arange(n)
        for s in CRT_SQUEEZES:
            f = np.zeros((n, n, 3), np.uint8)
            src_rows = np.round(c + (rows - c) / s).astype(int)
            ok = (src_rows >= 0) & (src_rows < n)
            band = source[np.clip(src_rows, 0, n - 1)]
            boost = int(220 * (1 - s))
            band = np.clip(band.astype(np.int16) + boost, 0, 255).astype(np.uint8)
            f[ok] = band[ok]
            frames.append(f)
        for r in CRT_DOTS:
            f = np.zeros((n, n, 3), np.uint8)
            m = sprites.disc(float(r))
            h = m.shape[0] // 2
            sprites.blend(f, c - h, c - h, m, (235, 240, 255))
            frames.append(f)
        frames.append(np.zeros((n, n, 3), np.uint8))
        self._crt = frames
        return len(frames)

    def crt(self, frame: int) -> tuple[np.ndarray, Rect]:
        if not self._crt:
            self._crt = [np.zeros((self.size, self.size, 3), np.uint8)]
        return self._crt[min(frame, len(self._crt) - 1)], self.full()

    def crt_frames(self) -> int:
        return len(self._crt)

    # ---- dispatch ---------------------------------------------------------
    def render(self, name: str, frame: int, extra: tuple = (), base: np.ndarray | None = None) -> tuple[np.ndarray, Rect]:
        if name == "hal":
            return self.hal(frame)
        if name == "crt":
            return self.crt(frame)
        if name == "terminator":
            return self.terminator(frame, extra)
        if name == "pirate":
            return self.pirate(frame)
        if name == "bsod":
            return self.bsod(frame)
        if name == "boot":
            return self.boot(frame, extra)
        if name == "aperture":
            return self.aperture(frame, base)
        if name == "eve":
            return self.eve(frame, extra)
        raise KeyError(name)
