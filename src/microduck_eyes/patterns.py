"""Test patterns for checking orientation, colour order and alignment on real panels."""
from __future__ import annotations

import numpy as np

from .eye import sprites


def colour_bars(size: int) -> np.ndarray:
    cols = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255), (0, 0, 0)]
    f = np.zeros((size, size, 3), np.uint8)
    w = size / len(cols)
    for i, c in enumerate(cols):
        f[:, int(i * w):int((i + 1) * w)] = c
    return f


def grid(size: int, step: int = 10) -> np.ndarray:
    f = np.full((size, size, 3), 30, np.uint8)
    f[::step, :] = (200, 200, 200)
    f[:, ::step] = (200, 200, 200)
    f[size // 2, :] = (255, 80, 80)
    f[:, size // 2] = (80, 255, 80)
    return f


def rings(size: int) -> np.ndarray:
    f = np.zeros((size, size, 3), np.uint8)
    c = size // 2
    for i, r in enumerate(range(size // 2, 0, -20)):
        colour = (255, 255, 255) if i % 2 == 0 else (0, 90, 200)
        mask = sprites.disc(r)
        half = mask.shape[0] // 2
        sprites.blend(f, c - half, c - half, mask, colour)
    return f


def arrow(size: int, label: str) -> np.ndarray:
    """An 'up' arrow plus an L or R block, to check rotation and mirroring."""
    f = np.full((size, size, 3), (20, 20, 20), np.uint8)
    c = size // 2
    yellow = (255, 220, 0)
    f[c - 40:c + 50, c - 8:c + 8] = yellow                      # shaft
    for i in range(40):                                           # triangular head, tip at c-80
        y = c - 80 + i
        f[y, c - i:c + i + 1] = yellow
    if label.upper() == "L":                                      # L: bar plus base, cyan
        f[c + 60:c + 100, c - 40:c - 28] = (0, 200, 255)
        f[c + 88:c + 100, c - 40:c] = (0, 200, 255)
    else:                                                         # R: solid red square
        f[c + 60:c + 100, c - 20:c + 20] = (255, 60, 60)
    return f


PATTERNS = {
    "bars": lambda size, side: colour_bars(size),
    "grid": lambda size, side: grid(size),
    "rings": lambda size, side: rings(size),
    "arrow": lambda size, side: arrow(size, "L" if side == "left" else "R"),
}
PATTERN_ORDER = ["bars", "grid", "rings", "arrow"]
