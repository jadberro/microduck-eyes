"""Pixel-level effects shared by the simulator and the hardware path."""
from __future__ import annotations

import numpy as np


def rgb565_quantize(frame: np.ndarray) -> np.ndarray:
    """Round an RGB888 frame to what an RGB565 panel can show, expanded back to 8 bits."""
    out = frame.copy()
    r = out[..., 0] & 0xF8
    g = out[..., 1] & 0xFC
    b = out[..., 2] & 0xF8
    out[..., 0] = r | (r >> 5)
    out[..., 1] = g | (g >> 6)
    out[..., 2] = b | (b >> 5)
    return out


def to_rgb565_bytes(frame: np.ndarray) -> bytes:
    """Pack RGB888 into big-endian RGB565 bytes, the order the GC9A01 expects."""
    r = frame[..., 0].astype(np.uint16)
    g = frame[..., 1].astype(np.uint16)
    b = frame[..., 2].astype(np.uint16)
    packed = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return packed.astype(">u2").tobytes()


def orient(frame: np.ndarray, rotate180: bool = False, mirror: bool = False) -> np.ndarray:
    if rotate180:
        frame = frame[::-1, ::-1]
    if mirror:
        frame = frame[:, ::-1]
    return frame


def orient_rect(rect, size: int, rotate180: bool = False, mirror: bool = False):
    x0, y0, x1, y1 = rect
    if rotate180:
        x0, x1 = size - x1, size - x0
        y0, y1 = size - y1, size - y0
    if mirror:
        x0, x1 = size - x1, size - x0
    return (x0, y0, x1, y1)
