"""Alternative pupil shapes and small overlay sprites, as cached anti-aliased layers.

Shapes are boolean predicates over (x, y) in pixels from the sprite centre, rendered once
with 4x4 supersampling. `layers(name, frame, r)` returns a list of (alpha, colour) layers
drawn centred on the pupil. Names may carry a parameter after a colon, e.g. "pie:0.62".
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from .font import text_mask

SS = 4

GREEN = (30, 165, 70)
RED = (235, 50, 80)
BLACK = (15, 12, 12)
WHITE = (255, 255, 255)
GOLD = (245, 190, 40)
GOLD_DARK = (200, 140, 20)
BLUE = (60, 130, 240)
ORANGE = (245, 130, 30)
GREY = (150, 150, 155)
TAN = (240, 205, 140)
CRUST = (165, 105, 55)
SKY = (130, 195, 255)
PINK = (255, 150, 180)
DUCK_YELLOW = (250, 205, 30)
MATRIX_GREEN = (70, 240, 110)
AMBER = (240, 170, 40)
LASER = (255, 40, 40)

FRAMES = {
    "disc": 1, "dollar": 8, "heart": 1, "spiral": 12, "star": 1, "x": 1, "slit": 9,
    "pie": 25, "battery": 11, "battery_charging": 11, "die": 6, "beachball": 12, "matrix": 16,
    "bread": 1, "cherry": 1, "seven": 1, "duck": 1, "laser": 1, "anime": 1, "eightball": 6,
    "notfound": 1, "coin": 1, "tear": 1, "z": 1, "rosette": 1, "blush": 1, "sparkle": 1,
    "clock": 1, "weather": 1, "compass": 1, "wifi": 1, "mic": 1, "dots": 6, "reflection": 1,
}
EIGHTBALL_ANSWERS = [("YES",), ("NO",), ("ASK", "LATER"), ("MAYBE",), ("QUACK",), ("VERY", "DOUBTFUL")]

Layer = tuple[np.ndarray, tuple[int, int, int]]


# ---- rendering helpers ------------------------------------------------------

def _grid(size: int):
    n = size * SS
    coords = (np.arange(n, dtype=np.float32) + 0.5) / SS - size / 2.0
    return coords[None, :], coords[:, None]


def shape_mask(size: int, pred) -> np.ndarray:
    x, y = _grid(size)
    hit = pred(x, y).astype(np.float32)
    return hit.reshape(size, SS, size, SS).mean(axis=(1, 3)).astype(np.float32)


def size_for(r: float) -> int:
    return int(np.ceil(r)) * 2 + 3


def _centre_text(size: int, lines, scale: int, y0: float, colour, line_gap: int = 2) -> list[Layer]:
    """Text lines centred horizontally in a (size, size) canvas, starting at y0 from the centre."""
    out = []
    y = size / 2.0 + y0
    for line in lines:
        m = text_mask(line, scale)
        canvas = np.zeros((size, size), np.float32)
        h, w = m.shape
        x = int(round(size / 2.0 - w / 2.0))
        yy = int(round(y))
        if 0 <= x and x + w <= size and 0 <= yy and yy + h <= size:
            canvas[yy:yy + h, x:x + w] = m
        out.append((canvas, colour))
        y += h + line_gap * scale
    return out


# ---- predicates --------------------------------------------------------------

def _disc(r):
    return lambda x, y: np.hypot(x, y) < r


def _ellipse(cx, cy, rx, ry):
    return lambda x, y: ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 < 1.0


def _rounded_square(s, power=4.0):
    return lambda x, y: (np.abs(x) / s) ** power + (np.abs(y) / s) ** power < 1.0


def _star(r_out, r_in, points=5, rot=-np.pi / 2):
    step = 2 * np.pi / points
    x1, y1 = r_out, 0.0
    x2, y2 = r_in * np.cos(step / 2), r_in * np.sin(step / 2)

    def pred(x, y):
        th = (np.arctan2(y, x) - rot) % step
        t = np.abs(th - step / 2)                      # 0 at a tip .. step/2 at an inner vertex
        t = step / 2 - t                               # angle from the tip direction
        edge_r = (x1 * y2 - x2 * y1) / ((y2 - y1) * np.cos(t) - (x2 - x1) * np.sin(t))
        return np.hypot(x, y) < np.abs(edge_r)

    return pred


def _dollar_pred(r, squeeze):
    a, w, bar_half, bar_len = 0.36 * r, 0.26 * r, 0.11 * r, 1.0 * r

    def pred(x, y):
        u = x / max(squeeze, 0.06)
        d1 = np.hypot(u, y + a)
        th1 = np.degrees(np.arctan2(y + a, u)) % 360.0
        ring1 = (np.abs(d1 - a) < w / 2) & (th1 >= 90) & (th1 <= 330)
        d2 = np.hypot(u, y - a)
        th2 = np.degrees(np.arctan2(y - a, u)) % 360.0
        ring2 = (np.abs(d2 - a) < w / 2) & ((th2 >= 270) | (th2 <= 150))
        bar = (np.abs(u) < bar_half) & (np.abs(y) < bar_len)
        return ring1 | ring2 | bar

    return pred


def _heart_pred(r):
    k = 0.78 * r

    def pred(x, y):
        u, v = x / k, -y / k + 0.15
        return (u * u + v * v - 1.0) ** 3 - u * u * v ** 3 < 0.0

    return pred


def _segment(x0, y0, x1, y1, w):
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy

    def pred(x, y):
        t = np.clip(((x - x0) * dx + (y - y0) * dy) / L2, 0.0, 1.0)
        return np.hypot(x - (x0 + t * dx), y - (y0 + t * dy)) < w / 2

    return pred


def _lens(a, h):
    """Vertical lens (cat slit): intersection of two circles, half-width a, half-height h."""
    R = (h * h + a * a) / (2 * a)
    off = R - a
    return lambda x, y: (np.hypot(x - off, y) < R) & (np.hypot(x + off, y) < R)


def _sector(r, a0, a1):
    """Angular sector a0..a1 (radians, screen coords, 0 = +x, increasing clockwise on screen)."""
    def pred(x, y):
        th = np.arctan2(y, x) % (2 * np.pi)
        inside = np.hypot(x, y) < r
        if a1 - a0 >= 2 * np.pi - 1e-6:
            return inside
        lo, hi = a0 % (2 * np.pi), a1 % (2 * np.pi)
        ang = (th >= lo) & (th < hi) if lo <= hi else (th >= lo) | (th < hi)
        return inside & ang

    return pred


def _teardrop(rx, ry):
    def pred(x, y):
        body = (x / rx) ** 2 + (y / ry) ** 2 < 1.0
        taper = (y < 0) & (y > -ry * 1.6) & (np.abs(x) < rx * (1.0 + y / (ry * 1.6)))
        return (body & (y >= 0)) | taper

    return pred


def _bolt(r):
    """Lightning bolt: two slanted parallelograms."""
    def pred(x, y):
        up = (y < 0.05 * r) & (y > -0.6 * r) & (np.abs(x + 0.08 * r + 0.35 * y) < 0.16 * r)
        down = (y >= -0.1 * r) & (y < 0.6 * r) & (np.abs(x - 0.08 * r + 0.35 * y) < 0.16 * r)
        return up | down

    return pred


# ---- builders: each returns list[(alpha, colour)] ---------------------------

def _b_dollar(r, frame):
    phi = 2.0 * np.pi * frame / FRAMES["dollar"]
    return [(shape_mask(size_for(r), _dollar_pred(r, abs(float(np.cos(phi))))), GREEN)]


def _b_heart(r, frame):
    return [(shape_mask(size_for(r), _heart_pred(r)), RED)]


def _b_spiral(r, frame):
    size = size_for(r)
    phase = frame / FRAMES["spiral"]

    def band(x, y):
        rho = np.hypot(x, y)
        t = (np.arctan2(y, x) / (2 * np.pi) + 2.0 * rho / r + phase) % 1.0
        return (t < 0.5) & (rho < r - 1.5)

    return [(shape_mask(size, _disc(r)), BLACK), (shape_mask(size, band), WHITE)]


def _b_star(r, frame):
    return [(shape_mask(size_for(r), _star(r, 0.45 * r)), GOLD)]


def _b_x(r, frame):
    w = 0.3 * r
    pred = lambda x, y: ((np.abs(x - y) < w / np.sqrt(2) * 1.0) | (np.abs(x + y) < w / np.sqrt(2))) & (np.abs(x) < 0.8 * r) & (np.abs(y) < 0.8 * r)
    return [(shape_mask(size_for(r), pred), BLACK)]


def _b_slit(r, frame):
    n = FRAMES["slit"]
    a = (0.08 + 0.72 * frame / (n - 1)) * r
    size = size_for(r)
    hl = shape_mask(size, _disc(0.12 * r))
    off = int(0.3 * r)
    hl_shift = np.zeros_like(hl)
    hl_shift[:-off or None, off:] = hl[off or 0:, :-off or None] if off else hl
    return [(shape_mask(size, _disc(0.95 * r)), AMBER), (shape_mask(size, _lens(a, 0.9 * r)), BLACK), (hl_shift, WHITE)]


def _b_pie(r, frame, share=0.55):
    n = FRAMES["pie"]
    p = frame / (n - 1)
    size = size_for(r)
    layers = [(shape_mask(size, _disc(r)), GREY)]
    start = -np.pi / 2
    a_or = 2 * np.pi * p * share
    a_bl = 2 * np.pi * p * (1 - share)
    if a_or > 0.01:
        layers.append((shape_mask(size, _sector(r, start, start + a_or)), ORANGE))
    if a_bl > 0.01:
        layers.append((shape_mask(size, _sector(r, start + a_or, start + a_or + a_bl)), BLUE))
    layers.append((shape_mask(size, lambda x, y: (np.hypot(x, y) < r) & (np.hypot(x, y) >= r - 2)), (60, 60, 65)))
    return layers


def _b_battery(r, frame, charging=False):
    level = frame / (FRAMES["battery"] - 1)
    size = size_for(r)
    bw, bh = 0.7 * r, 0.42 * r
    body = lambda x, y: (np.abs(x + 0.06 * r) < bw) & (np.abs(y) < bh)
    inner = lambda x, y: (np.abs(x + 0.06 * r) < bw - 0.07 * r) & (np.abs(y) < bh - 0.07 * r)
    nub = lambda x, y: (x >= bw - 0.06 * r) & (x < bw + 0.1 * r) & (np.abs(y) < 0.18 * r)
    fill_w = (2 * bw - 0.2 * r) * level
    fill = lambda x, y: (x > -bw + 0.04 * r) & (x < -bw + 0.04 * r + fill_w) & (np.abs(y) < bh - 0.1 * r)
    colour = (60, 200, 90) if level > 0.5 else (240, 170, 40) if level > 0.2 else (230, 50, 50)
    layers = [
        (shape_mask(size, lambda x, y: body(x, y) | nub(x, y)), (40, 40, 45)),
        (shape_mask(size, inner), WHITE),
        (shape_mask(size, fill), colour),
    ]
    if charging:
        layers.append((shape_mask(size, _bolt(r * 0.8)), (255, 220, 60)))
        layers.append((shape_mask(size, lambda x, y: _bolt(r * 0.8)(x, y) & ~_bolt(r * 0.62)(x, y)), (40, 40, 45)))
    return layers


def _b_die(r, frame):
    face = frame % 6 + 1
    s = 0.85 * r
    size = size_for(r)
    pip_r = 0.16 * r
    o = 0.42 * r
    spots = {1: [(0, 0)], 2: [(-o, -o), (o, o)], 3: [(-o, -o), (0, 0), (o, o)],
             4: [(-o, -o), (o, -o), (-o, o), (o, o)], 5: [(-o, -o), (o, -o), (0, 0), (-o, o), (o, o)],
             6: [(-o, -o), (o, -o), (-o, 0), (o, 0), (-o, o), (o, o)]}[face]
    pips = lambda x, y: np.any([np.hypot(x - px, y - py) < pip_r for px, py in spots], axis=0)
    return [(shape_mask(size, _rounded_square(s)), (40, 40, 45)),
            (shape_mask(size, _rounded_square(s - 0.08 * r)), WHITE),
            (shape_mask(size, pips), BLACK)]


def _b_beachball(r, frame):
    n = FRAMES["beachball"]
    rot = 2 * np.pi * frame / n / 6.0          # one sector per full cycle
    size = size_for(r)
    cols = [(255, 70, 70), (255, 170, 40), (255, 230, 60), (70, 200, 90), (60, 140, 255), (170, 90, 230)]
    layers = []
    for i, c in enumerate(cols):
        a0 = rot + i * np.pi / 3
        layers.append((shape_mask(size, _sector(r, a0, a0 + np.pi / 3)), c))
    layers.append((shape_mask(size, _disc(0.22 * r)), WHITE))
    layers.append((shape_mask(size, lambda x, y: (np.hypot(x, y) < r) & (np.hypot(x, y) >= r - 1.5)), (60, 60, 65)))
    return layers


def _b_matrix(r, frame):
    size = size_for(r)
    rng = np.random.default_rng(7)
    canvas = np.zeros((size, size), np.float32)
    col_w, glyph_h = 7, 9
    ncols = size // col_w
    chars = "01QUACKDUCK7Z"
    speeds = rng.integers(1, 4, ncols)
    offsets = rng.integers(0, 40, ncols)
    for ci in range(ncols):
        head = (offsets[ci] + frame * speeds[ci] * 3) % (size + 40) - 20
        for k in range(6):                      # trail length
            y = int(head - k * glyph_h)
            if 0 <= y and y + 7 <= size:
                ch = chars[(ci * 3 + k + frame // 2) % len(chars)]
                m = text_mask(ch, 1) * (1.0 - k * 0.15)
                x = ci * col_w + 1
                canvas[y:y + 7, x:x + 5] = np.maximum(canvas[y:y + 7, x:x + 5], m)
    disc = shape_mask(size, _disc(r))
    return [(disc, (5, 15, 8)), ((canvas * disc).astype(np.float32), MATRIX_GREEN)]


def _b_bread(r, frame):
    size = size_for(r)

    def slice_pred(k):
        def pred(x, y):
            body = (np.abs(x) < 0.78 * r * k) & (y > -0.3 * r * k) & (y < 0.82 * r * k)
            bumps = (np.hypot(x - 0.4 * r * k, y + 0.38 * r * k) < 0.42 * r * k) | (np.hypot(x + 0.4 * r * k, y + 0.38 * r * k) < 0.42 * r * k)
            top = (np.abs(x) < 0.4 * r * k) & (y > -0.65 * r * k) & (y < 0)
            return body | bumps | top
        return pred

    return [(shape_mask(size, slice_pred(1.0)), CRUST), (shape_mask(size, slice_pred(0.84)), TAN)]


def _b_cherry(r, frame):
    size = size_for(r)
    c1, c2 = (-0.4 * r, 0.4 * r), (0.4 * r, 0.45 * r)
    top = (0.05 * r, -0.85 * r)
    stems = lambda x, y: _segment(c1[0], c1[1] - 0.2 * r, top[0], top[1], 0.1 * r)(x, y) | _segment(c2[0], c2[1] - 0.2 * r, top[0], top[1], 0.1 * r)(x, y)
    leaf = _ellipse(0.3 * r, -0.75 * r, 0.3 * r, 0.13 * r)
    cherries = lambda x, y: (np.hypot(x - c1[0], y - c1[1]) < 0.42 * r) | (np.hypot(x - c2[0], y - c2[1]) < 0.42 * r)
    hl = lambda x, y: (np.hypot(x - c1[0] + 0.13 * r, y - c1[1] + 0.15 * r) < 0.1 * r) | (np.hypot(x - c2[0] + 0.13 * r, y - c2[1] + 0.15 * r) < 0.1 * r)
    return [(shape_mask(size, stems), (70, 130, 50)), (shape_mask(size, leaf), (80, 170, 60)),
            (shape_mask(size, cherries), (220, 30, 50)), (shape_mask(size, hl), WHITE)]


def _b_seven(r, frame):
    size = size_for(r)
    scale = max(int(round(1.5 * r / 7)), 2)
    return _centre_text(size, ["7"], scale, -3.5 * scale, (230, 40, 40))


def _b_duck(r, frame):
    size = size_for(r)
    body = _ellipse(-0.1 * r, 0.32 * r, 0.78 * r, 0.42 * r)
    head = _disc(0.36 * r)
    hx, hy = 0.3 * r, -0.38 * r
    head_p = lambda x, y: head(x - hx, y - hy)
    beak = _ellipse(hx + 0.48 * r, hy + 0.06 * r, 0.26 * r, 0.11 * r)
    wing = _ellipse(-0.25 * r, 0.32 * r, 0.4 * r, 0.2 * r)
    eye = lambda x, y: np.hypot(x - hx - 0.12 * r, y - hy + 0.1 * r) < 0.07 * r
    return [(shape_mask(size, lambda x, y: body(x, y) | head_p(x, y)), DUCK_YELLOW),
            (shape_mask(size, wing), (235, 185, 20)),
            (shape_mask(size, beak), ORANGE), (shape_mask(size, eye), BLACK)]


def _b_laser(r, frame):
    size = size_for(1.9 * r)
    x, y = _grid(size)
    rho = np.hypot(x, y)
    bloom = np.clip(1.0 - rho / (1.9 * r), 0, 1) ** 2 * 0.85
    bloom = bloom.reshape(size, SS, size, SS).mean(axis=(1, 3)).astype(np.float32)
    return [(bloom, LASER), (shape_mask(size, _disc(0.8 * r)), (255, 30, 30)), (shape_mask(size, _disc(0.35 * r)), (255, 200, 200))]


def _b_anime(r, frame):
    size = size_for(r)
    hl = lambda x, y: (np.hypot(x + 0.35 * r, y + 0.35 * r) < 0.3 * r) | (np.hypot(x - 0.3 * r, y - 0.3 * r) < 0.16 * r) | (np.hypot(x - 0.42 * r, y + 0.25 * r) < 0.08 * r) | (np.hypot(x + 0.1 * r, y - 0.52 * r) < 0.06 * r)
    sparkle = _star(0.22 * r, 0.06 * r, 4, 0)
    return [(shape_mask(size, _disc(r)), (45, 20, 60)), (shape_mask(size, _disc(0.72 * r)), (90, 40, 120)),
            (shape_mask(size, hl), WHITE), (shape_mask(size, lambda x, y: sparkle(x + 0.05 * r, y - 0.1 * r)), WHITE)]


def _b_eightball(r, frame):
    size = size_for(r)
    tri = lambda x, y: (y > -0.55 * r) & (y < 0.5 * r) & (np.abs(x) < (0.5 * r - y) * 0.85)
    layers = [(shape_mask(size, _disc(r)), (15, 15, 20)), (shape_mask(size, tri), (20, 45, 170))]
    lines = EIGHTBALL_ANSWERS[frame % len(EIGHTBALL_ANSWERS)]
    scale = 1 if r < 60 else 2
    y0 = -0.42 * r if len(lines) > 1 else -0.25 * r
    layers += _centre_text(size, list(lines), scale, y0, WHITE)
    return layers


def _b_notfound(r, frame):
    size = size_for(r)
    layers = [(shape_mask(size, _disc(r)), (35, 35, 40))]
    layers += _centre_text(size, ["404"], 2, -0.62 * r, (255, 120, 120))
    layers += _centre_text(size, ["EYE NOT", "FOUND"], 1, -0.1 * r, WHITE)
    return layers


def _b_coin(r, frame):
    size = size_for(r)
    return [(shape_mask(size, _disc(r)), GOLD_DARK), (shape_mask(size, _disc(0.78 * r)), GOLD)]


def _b_tear(r, frame):
    return [(shape_mask(size_for(1.6 * r), _teardrop(0.6 * r, r)), SKY)]


def _b_z(r, frame):
    size = size_for(r)
    scale = max(int(round(1.4 * r / 7)), 1)
    return _centre_text(size, ["Z"], scale, -3.5 * scale, (90, 110, 200))


def _b_rosette(r, frame):
    size = size_for(1.5 * r)
    ribbon = lambda x, y: ((np.abs(x + 0.25 * r - 0.25 * (y - 0.6 * r)) < 0.16 * r) | (np.abs(x - 0.25 * r + 0.25 * (y - 0.6 * r)) < 0.16 * r)) & (y > 0.5 * r) & (y < 1.45 * r)
    return [(shape_mask(size, ribbon), (200, 40, 60)), (shape_mask(size, _disc(r)), (200, 40, 60)),
            (shape_mask(size, _disc(0.72 * r)), WHITE), (shape_mask(size, _disc(0.45 * r)), (40, 70, 190))]


def _b_blush(r, frame):
    size = size_for(1.6 * r)
    x, y = _grid(size)
    a = np.clip(1.0 - ((x / (1.6 * r)) ** 2 + (y / (0.7 * r)) ** 2), 0, 1) ** 0.7 * 0.55
    return [(a.reshape(size, SS, size, SS).mean(axis=(1, 3)).astype(np.float32), PINK)]


def _b_sparkle(r, frame):
    return [(shape_mask(size_for(r), _star(r, 0.25 * r, 4, 0)), WHITE)]


# ---- status glance sprites --------------------------------------------------------

def _b_clock(r, frame, hhmm="12:00"):
    size = size_for(r)
    try:
        hh, mm = (int(v) for v in hhmm.split(":")[:2])
    except ValueError:
        hh, mm = 12, 0
    a_m = 2 * np.pi * (mm / 60.0) - np.pi / 2
    a_h = 2 * np.pi * ((hh % 12) / 12.0 + mm / 720.0) - np.pi / 2
    hand_m = _segment(0, 0, 0.78 * r * np.cos(a_m), 0.78 * r * np.sin(a_m), 0.09 * r)
    hand_h = _segment(0, 0, 0.5 * r * np.cos(a_h), 0.5 * r * np.sin(a_h), 0.13 * r)
    ticks = lambda x, y: (np.hypot(x, y) > 0.82 * r) & (np.hypot(x, y) < 0.92 * r) & (np.abs(np.sin(6 * np.arctan2(y, x))) < 0.12)
    return [(shape_mask(size, _disc(r)), (40, 40, 45)), (shape_mask(size, _disc(0.92 * r)), WHITE),
            (shape_mask(size, ticks), (60, 60, 65)), (shape_mask(size, lambda x, y: hand_h(x, y) | hand_m(x, y)), BLACK),
            (shape_mask(size, _disc(0.08 * r)), (220, 40, 40))]


def _b_weather(r, frame, kind="sun"):
    size = size_for(r)
    cloud = lambda x, y: (np.hypot(x + 0.3 * r, y - 0.05 * r) < 0.32 * r) | (np.hypot(x - 0.05 * r, y + 0.15 * r) < 0.4 * r) | \
                         (np.hypot(x - 0.42 * r, y - 0.02 * r) < 0.28 * r) | ((np.abs(x - 0.05 * r) < 0.65 * r) & (y > 0.0) & (y < 0.3 * r))
    if kind == "sun":
        rays = lambda x, y: (np.hypot(x, y) > 0.62 * r) & (np.hypot(x, y) < 0.95 * r) & (np.abs(np.sin(4 * np.arctan2(y, x))) < 0.25)
        return [(shape_mask(size, rays), (250, 190, 40)), (shape_mask(size, _disc(0.5 * r)), (255, 210, 60))]
    if kind == "cloud":
        return [(shape_mask(size, cloud), (200, 205, 215))]
    if kind == "rain":
        drops = lambda x, y: np.any([_teardrop(0.07 * r, 0.14 * r)(x - dx * r, y - 0.62 * r) for dx in (-0.4, -0.05, 0.3)], axis=0)
        return [(shape_mask(size, cloud), (170, 178, 190)), (shape_mask(size, drops), SKY)]
    if kind == "snow":
        flakes = lambda x, y: np.any([np.hypot(x - dx * r, y - 0.62 * r) < 0.08 * r for dx in (-0.45, -0.1, 0.25)], axis=0)
        return [(shape_mask(size, cloud), (200, 205, 215)), (shape_mask(size, flakes), (150, 200, 255))]
    if kind == "storm":
        return [(shape_mask(size, cloud), (90, 95, 110)), (shape_mask(size, lambda x, y: _bolt(0.5 * r)(x, y - 0.55 * r)), (255, 220, 60))]
    return [(shape_mask(size, cloud), GREY)]


def _b_compass(r, frame, heading="0"):
    size = size_for(r)
    try:
        h = float(heading)
    except ValueError:
        h = 0.0
    a = np.radians(h) - np.pi / 2               # needle points to north rotated by the heading
    north = lambda x, y: (np.abs(x * np.sin(a) - y * np.cos(a)) < 0.12 * r * (1 - (x * np.cos(a) + y * np.sin(a)) / (0.8 * r))) & \
                         ((x * np.cos(a) + y * np.sin(a)) > 0) & ((x * np.cos(a) + y * np.sin(a)) < 0.8 * r)
    south = lambda x, y: north(-x, -y)
    return [(shape_mask(size, _disc(r)), (40, 40, 45)), (shape_mask(size, _disc(0.9 * r)), WHITE),
            (shape_mask(size, south), (120, 120, 130)), (shape_mask(size, north), (220, 40, 40)),
            (shape_mask(size, _disc(0.08 * r)), (40, 40, 45))]


def _b_wifi(r, frame, bars="3"):
    size = size_for(r)
    try:
        n = int(bars)
    except ValueError:
        n = 3
    layers = []
    for i, rr in enumerate((0.95, 0.68, 0.42)):
        band = lambda x, y, rr=rr: (np.hypot(x, y - 0.5 * r) < rr * r) & (np.hypot(x, y - 0.5 * r) > (rr - 0.16) * r) & \
                                   (y < 0.5 * r) & (np.abs(x) < -(y - 0.5 * r) * 1.0)
        colour = BLUE if (3 - i) <= n else (200, 200, 205)
        layers.append((shape_mask(size, band), colour))
    layers.append((shape_mask(size, lambda x, y: np.hypot(x, y - 0.5 * r) < 0.14 * r), BLUE if n >= 1 else (200, 200, 205)))
    if n == 0:
        layers.append((shape_mask(size, lambda x, y: (np.abs(x - y) < 0.1 * r) & (np.abs(x) < 0.7 * r) & (np.abs(y) < 0.7 * r)), (230, 50, 50)))
    return layers


def _b_mic(r, frame):
    size = size_for(r)
    capsule = lambda x, y: ((np.abs(x) < 0.26 * r) & (np.abs(y + 0.15 * r) < 0.3 * r)) | (np.hypot(x, y + 0.45 * r) < 0.26 * r) | (np.hypot(x, y - 0.15 * r) < 0.26 * r)
    arc = lambda x, y: (np.hypot(x, y - 0.05 * r) < 0.5 * r) & (np.hypot(x, y - 0.05 * r) > 0.4 * r) & (y > 0.05 * r)
    stand = lambda x, y: ((np.abs(x) < 0.05 * r) & (y > 0.5 * r) & (y < 0.8 * r)) | ((np.abs(x) < 0.3 * r) & (np.abs(y - 0.82 * r) < 0.05 * r))
    return [(shape_mask(size, lambda x, y: arc(x, y) | stand(x, y)), (70, 70, 80)), (shape_mask(size, capsule), (230, 60, 60))]


def _b_dots(r, frame):
    size = size_for(r)
    k = frame % FRAMES["dots"]
    def dots(x, y):
        hit = np.zeros_like(x, dtype=bool) | np.zeros_like(y, dtype=bool)
        for i, dx in enumerate((-0.5, 0.0, 0.5)):
            bounce = 0.22 * r if (k // 2) == i else 0.0
            hit = hit | (np.hypot(x - dx * r, y + bounce) < 0.16 * r)
        return hit
    return [(shape_mask(size, _disc(r)), (40, 40, 45)), (shape_mask(size, dots), WHITE)]


def _b_reflection(r, frame):
    """Soft crescent used as a window reflection on the sclera."""
    size = size_for(r)
    x, y = _grid(size)
    outer = np.clip(1.0 - (np.hypot(x, y) / r) ** 2, 0, 1)
    inner = np.clip(1.0 - (np.hypot(x - 0.25 * r, y + 0.3 * r) / (0.95 * r)) ** 2, 0, 1)
    a = np.clip(outer - inner, 0, 1) ** 1.2 * 0.28
    return [(a.reshape(size, SS, size, SS).mean(axis=(1, 3)).astype(np.float32), WHITE)]


_BUILDERS = {
    "mic": _b_mic, "dots": _b_dots, "reflection": _b_reflection,
    "dollar": _b_dollar, "heart": _b_heart, "spiral": _b_spiral, "star": _b_star, "x": _b_x, "slit": _b_slit,
    "pie": _b_pie, "battery": lambda r, f: _b_battery(r, f, False), "battery_charging": lambda r, f: _b_battery(r, f, True),
    "die": _b_die, "beachball": _b_beachball, "matrix": _b_matrix, "bread": _b_bread, "cherry": _b_cherry,
    "seven": _b_seven, "duck": _b_duck, "laser": _b_laser, "anime": _b_anime, "eightball": _b_eightball,
    "notfound": _b_notfound, "coin": _b_coin, "tear": _b_tear, "z": _b_z, "rosette": _b_rosette,
    "blush": _b_blush, "sparkle": _b_sparkle,
}


@lru_cache(maxsize=1024)
def layers(name: str, frame: int, r: float) -> list[Layer]:
    """Centred layers that replace the plain pupil disc (or serve as overlay sprites)."""
    r = round(float(r), 1)
    base, _, param = name.partition(":")
    if base == "pie":
        return _b_pie(r, frame % FRAMES["pie"], float(param) if param else 0.55)
    if base == "clock":
        return _b_clock(r, 0, param or "12:00")
    if base == "weather":
        return _b_weather(r, 0, param or "sun")
    if base == "compass":
        return _b_compass(r, 0, param or "0")
    if base == "wifi":
        return _b_wifi(r, 0, param or "3")
    builder = _BUILDERS[base]
    return builder(r, frame % FRAMES.get(base, 1))


# Backwards-compatible single-mask helpers used by tests and particles.
def dollar(r: float, frame: int = 0) -> np.ndarray:
    return layers("dollar", frame, r)[0][0]


def heart(r: float) -> np.ndarray:
    return layers("heart", 0, r)[0][0]


def spiral(r: float, frame: int = 0) -> tuple[np.ndarray, np.ndarray]:
    ls = layers("spiral", frame, r)
    return ls[0][0], ls[1][0]
