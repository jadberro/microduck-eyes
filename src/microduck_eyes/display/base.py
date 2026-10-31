"""Display backend protocol. Frames are (size, size, 3) uint8 RGB numpy arrays."""
from __future__ import annotations

from typing import Protocol

import numpy as np

Rect = tuple[int, int, int, int]


class Display(Protocol):
    def show(self, index: int, frame: np.ndarray, dirty: Rect) -> None:
        """Push one eye's frame. `dirty` is the region that changed (x0, y0, x1, y1)."""

    def flip(self) -> None:
        """Present everything pushed since the last flip."""

    def close(self) -> None: ...
