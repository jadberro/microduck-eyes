"""Anti-aliased masks built with numpy only. Generated once and cached."""
from __future__ import annotations

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=64)
def disc(r: float) -> np.ndarray:
    """Square float32 alpha mask of a disc with radius r, centred in the array.

    The array side is odd so the centre lands on a pixel centre.
    """
    n = int(np.ceil(r)) * 2 + 3
    c = n // 2
    ys, xs = np.mgrid[0:n, 0:n]
    dist = np.hypot(xs - c, ys - c)
    return np.clip(r + 0.5 - dist, 0.0, 1.0).astype(np.float32)


@lru_cache(maxsize=16)
def ring(r_outer: float, r_inner: float) -> np.ndarray:
    n = int(np.ceil(r_outer)) * 2 + 3
    c = n // 2
    ys, xs = np.mgrid[0:n, 0:n]
    dist = np.hypot(xs - c, ys - c)
    outer = np.clip(r_outer + 0.5 - dist, 0.0, 1.0)
    inner = np.clip(r_inner + 0.5 - dist, 0.0, 1.0)
    return (outer - inner).astype(np.float32)


class LidMasks:
    """Upper and lower eyelid masks for a given panel geometry.

    Masks are quantised on (closure, tilt) and cached so repeated blinks are free.
    Each result is (alpha, edge_alpha, row0): two float32 arrays covering rows
    row0..row0+h over the full panel width.
    """

    CLOSURE_STEPS = 64
    TILT_STEPS = 24

    def __init__(self, size: int, sclera_r: float, outline_w: float,
                 curve: float, edge_w: float, meet_y: float):
        self.size = size
        self.cx = self.cy = size / 2.0 - 0.5
        self.R = float(sclera_r)
        self.curve = curve
        self.edge_w = edge_w
        self.meet_y = meet_y
        xs = np.arange(size, dtype=np.float32)
        self.u = (xs - self.cx) / self.R                    # -1..1 across the sclera
        zone_r = sclera_r + outline_w + 3.0  # fully cover the outline ring so no AA residue shows under a lid
        ys = np.arange(size, dtype=np.float32)
        dist = np.hypot(xs[None, :] - self.cx, ys[:, None] - self.cy)
        self.zone = np.clip(zone_r + 0.5 - dist, 0.0, 1.0).astype(np.float32)
        self._cache: dict[tuple, tuple[np.ndarray, np.ndarray, int]] = {}

    def _edge_y(self, which: str, closure: float, tilt: float) -> np.ndarray:
        R, cy = self.R, self.cy
        top = cy - 1.15 * R
        bottom = cy + 1.15 * R
        meet = cy + self.meet_y * R
        arch = self.curve * R * (1.0 - np.clip(self.u, -1, 1) ** 2)
        tilt_px = tilt * R * np.clip(self.u, -1, 1)
        if which == "upper":
            y0 = top + closure * (meet - top)
            return y0 - arch * (1.0 - closure) + tilt_px
        y0 = bottom - closure * (bottom - meet)
        return y0 - arch * closure + tilt_px

    def get(self, which: str, closure: float, tilt: float):
        ci = int(round(min(max(closure, 0.0), 1.0) * self.CLOSURE_STEPS))
        ti = int(round(min(max(tilt, -1.0), 1.0) * self.TILT_STEPS))
        key = (which, ci, ti)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        c = ci / self.CLOSURE_STEPS
        t = ti / self.TILT_STEPS
        edge = self._edge_y(which, c, t)                       # per column
        half = self.edge_w / 2.0
        if which == "upper":
            row0 = 0
            row1 = int(np.ceil(edge.max() + half + 1))
        else:
            row0 = int(np.floor(edge.min() - half - 1))
            row1 = self.size
        row0 = max(row0, 0)
        row1 = min(row1, self.size)
        if row1 <= row0:
            empty = np.zeros((0, self.size), np.float32)
            result = (empty, empty, 0)
            self._cache[key] = result
            return result
        ys = np.arange(row0, row1, dtype=np.float32)[:, None]
        signed = (edge[None, :] - ys) if which == "upper" else (ys - edge[None, :])
        alpha = np.clip(signed + 0.5, 0.0, 1.0)
        edge_alpha = np.clip(half + 0.5 - np.abs(signed), 0.0, 1.0)
        zone = self.zone[row0:row1]
        alpha = (alpha * zone).astype(np.float32)
        edge_alpha = (edge_alpha * zone).astype(np.float32)
        # Trim rows that paint nothing so the renderer's dirty rect stays tight.
        live = np.nonzero((alpha > 0).any(axis=1) | (edge_alpha > 0).any(axis=1))[0]
        if len(live) == 0:
            empty = np.zeros((0, self.size), np.float32)
            result = (empty, empty, 0)
        else:
            a, b = int(live[0]), int(live[-1]) + 1
            result = (np.ascontiguousarray(alpha[a:b]), np.ascontiguousarray(edge_alpha[a:b]), row0 + a)
        if len(self._cache) > 2048:
            self._cache.clear()
        self._cache[key] = result
        return result


def blend(frame: np.ndarray, x: int, y: int, alpha: np.ndarray, colour) -> tuple[int, int, int, int] | None:
    """Alpha-blend a solid colour through `alpha` onto frame at top-left (x, y).

    Returns the clipped bounding box (x0, y0, x1, y1) that was touched, or None.
    """
    h, w = alpha.shape
    H, W = frame.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return None
    a = alpha[y0 - y:y1 - y, x0 - x:x1 - x][..., None]
    region = frame[y0:y1, x0:x1]
    col = np.asarray(colour, dtype=np.float32)
    out = region.astype(np.float32) * (1.0 - a) + col * a
    region[...] = (out + 0.5).astype(np.uint8)
    return (x0, y0, x1, y1)


class BrowMasks:
    """Eyebrow: a thick arc concentric with the sclera, which can lower onto the eye and tilt.

    Cached on (y offset, tilt degrees) so expression changes are the only cost.
    """

    def __init__(self, size: int, radius: float, half_angle_deg: float, thickness: float):
        self.size = size
        self.c = size / 2.0 - 0.5
        self.R = radius
        self.half = np.radians(half_angle_deg)
        self.t = thickness
        self._cache: dict[tuple[int, int], tuple[np.ndarray, int, int]] = {}

    def get(self, y_offset: float, tilt_deg: float) -> tuple[np.ndarray, int, int]:
        """(alpha, x0, y0): a tight mask and its top-left position on the panel."""
        key = (int(round(y_offset)), int(round(tilt_deg)))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        yo, tilt = key
        rot = np.radians(tilt)
        ss = 2
        n = self.size * ss
        coords = (np.arange(n, dtype=np.float32) + 0.5) / ss - 0.5
        x = coords[None, :] - self.c
        y = coords[:, None] - (self.c + yo)
        rho = np.hypot(x, y)
        th = np.arctan2(y, x) + np.pi / 2 - rot          # 0 at the top of the arc
        th = (th + np.pi) % (2 * np.pi) - np.pi
        inside_arc = (np.abs(th) <= self.half) & (np.abs(rho - self.R) < self.t / 2)
        # rounded ends
        ends = np.zeros_like(inside_arc)
        for sgn in (-1, 1):
            a = -np.pi / 2 + rot + sgn * self.half
            ex, ey = self.R * np.cos(a), self.R * np.sin(a)
            ends |= np.hypot(x - ex, y - ey) < self.t / 2
        hit_f = (inside_arc | ends).astype(np.float32)
        alpha = hit_f.reshape(self.size, ss, self.size, ss).mean(axis=(1, 3)).astype(np.float32)
        rows = np.nonzero(alpha.any(axis=1))[0]
        cols = np.nonzero(alpha.any(axis=0))[0]
        if len(rows) == 0:
            result = (np.zeros((0, 0), np.float32), 0, 0)
        else:
            y0, y1, x0, x1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
            result = (np.ascontiguousarray(alpha[y0:y1, x0:x1]), int(x0), int(y0))
        if len(self._cache) > 512:
            self._cache.clear()
        self._cache[key] = result
        return result


@lru_cache(maxsize=32)
def iris_layers(r: float, colour: tuple[int, int, int]) -> list[tuple[np.ndarray, tuple[int, int, int]]]:
    """Textured iris: base disc, radial streaks, darker limbal ring and a lighter inner collar."""
    n = int(np.ceil(r)) * 2 + 3
    c = n // 2
    ys, xs = np.mgrid[0:n, 0:n]
    x, y = xs - c, ys - c
    rho = np.hypot(x, y)
    th = np.arctan2(y, x)
    base = np.clip(r + 0.5 - rho, 0.0, 1.0).astype(np.float32)
    streak = (0.5 + 0.5 * np.sin(th * 22.0) * np.sin(th * 7.0 + 1.3)) * np.clip((rho - 0.35 * r) / (0.65 * r), 0, 1)
    streak = (np.clip(streak, 0, 1) * 0.35 * base).astype(np.float32)
    limbal = (np.clip((rho - 0.82 * r) / (0.18 * r), 0, 1) * 0.55 * base).astype(np.float32)
    collar = (np.clip(1.0 - rho / (0.45 * r), 0, 1) * 0.25 * base).astype(np.float32)
    dark = tuple(int(v * 0.55) for v in colour)
    light = tuple(min(255, int(v * 1.25 + 20)) for v in colour)
    return [(base, colour), (streak, dark), (limbal, dark), (collar, light)]
