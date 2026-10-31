"""Composite cached sprites into a 240x240 RGB frame and report what changed."""
from __future__ import annotations

import numpy as np

from ..config import Config
from . import pupil_sprites, sprites
from .state import EyeState, clamp

Rect = tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive)


def union(a: Rect | None, b: Rect | None) -> Rect | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


class EyeRenderer:
    def __init__(self, cfg: Config, side: str):
        self.cfg = cfg
        self.side = side
        e, c = cfg.eye, cfg.colours
        self.size = cfg.panel.size
        self.c = self.size // 2
        # Static base: face colour, outline ring, sclera disc.
        base = np.empty((self.size, self.size, 3), np.uint8)
        base[...] = c.face
        outer = e.sclera_r + e.outline_w
        ring = sprites.ring(outer, e.sclera_r)
        disc = sprites.disc(e.sclera_r)
        half_r = ring.shape[0] // 2
        half_d = disc.shape[0] // 2
        sprites.blend(base, self.c - half_r, self.c - half_r, ring, c.outline)
        sprites.blend(base, self.c - half_d, self.c - half_d, disc, c.sclera)
        self.base = base
        self.lids = sprites.LidMasks(self.size, e.sclera_r, e.outline_w, e.lid_curve, e.lid_edge_w, e.lid_meet_y)
        b = cfg.brows
        self.brows = sprites.BrowMasks(self.size, b.radius, b.half_angle_deg, b.thickness)
        # the sclera zone clips the iris so it never spills onto the face
        self._sclera = sprites.disc(float(e.sclera_r))
        self._prev: dict[str, tuple[tuple, Rect | None]] = {}   # element -> (key, bbox) from the last frame
        self.frame = base.copy()

    def _draw_disc(self, frame, cx: float, cy: float, r: float, colour) -> Rect | None:
        if r < 0.5:
            return None
        mask = sprites.disc(round(r, 1))
        half = mask.shape[0] // 2
        return sprites.blend(frame, int(round(cx)) - half, int(round(cy)) - half, mask, colour)

    def render(self, state: EyeState, overlays=()) -> tuple[np.ndarray, Rect]:
        """Render `state` into self.frame. Returns (frame, dirty_rect).

        `overlays` are (alpha, colour, x, y) layers drawn on top of everything.
        The dirty rect covers everything that may differ from the previous frame.
        """
        s = clamp(state, self.cfg)
        e, c = self.cfg.eye, self.cfg.colours
        frame = self.frame
        frame[...] = self.base
        boxes: dict[str, tuple[tuple, Rect | None]] = {}

        # --- pupil group: iris, pupil (or sprite), highlights ---
        pr = e.pupil_r * s.pupil_scale
        px = self.c + s.pupil_x
        py = self.c + s.pupil_y
        box: Rect | None = None
        if self.cfg.iris.enabled and s.iris_scale > 0 and s.pupil_sprite == "disc":
            ir = round(pr * self.cfg.iris.scale * s.iris_scale, 1)
            colour = s.iris_colour or self.cfg.iris.colour
            for alpha, col in sprites.iris_layers(ir, tuple(colour)):
                half = alpha.shape[0] // 2
                box = union(box, self._blend_clipped(frame, int(round(px)) - half, int(round(py)) - half, alpha, col))
        if s.pupil_sprite != "disc":
            for alpha, colour in pupil_sprites.layers(s.pupil_sprite, s.pupil_frame, pr):
                half = alpha.shape[0] // 2
                box = union(box, sprites.blend(frame, int(round(px)) - half, int(round(py)) - half, alpha, colour))
        else:
            box = union(box, self._draw_disc(frame, px, py, pr, c.pupil))
        if s.highlights and s.pupil_sprite == "disc":
            k = s.pupil_scale
            bx, by = e.highlight_big_offset
            box = union(box, self._draw_disc(frame, px + bx * k, py + by * k, e.highlight_big_r * k, c.highlight))
            sx, sy = e.highlight_small_offset
            box = union(box, self._draw_disc(frame, px + sx * k, py + sy * k, e.highlight_small_r * k, c.highlight))
        boxes["pupil"] = ((s.pupil_x, s.pupil_y, s.pupil_scale, s.pupil_sprite, s.pupil_frame, s.highlights,
                           s.iris_scale, s.iris_colour), box)

        # --- lids ---
        box = None
        for which, closure in (("upper", s.lid_upper), ("lower", s.lid_lower)):
            alpha, edge, row0 = self.lids.get(which, closure, s.lid_tilt)
            if alpha.shape[0] == 0:
                continue
            r1 = sprites.blend(frame, 0, row0, alpha, c.face)
            r2 = sprites.blend(frame, 0, row0, edge, c.lid_edge)
            box = union(box, union(r1, r2))
        boxes["lids"] = ((s.lid_upper, s.lid_lower, s.lid_tilt), box)

        # --- brows ---
        box = None
        if s.brow and self.cfg.brows.enabled:
            alpha, bx, by = self.brows.get(s.brow_y, s.brow_tilt)
            if alpha.size:
                box = sprites.blend(frame, bx, by, alpha, self.cfg.brows.colour)
        boxes["brows"] = ((s.brow, s.brow_y, s.brow_tilt), box)

        # --- overlays: always counted as changed ---
        box = None
        for alpha, colour, x, y in overlays:
            box = union(box, sprites.blend(frame, x, y, alpha, colour))
        boxes["overlays"] = ((len(overlays), id(overlays) if overlays else 0), box)

        # Dirty rect: every element whose parameters changed contributes old and new bbox.
        # Lids and brows paint over the pupil group, so a pupil change under a lid is still inside its own bbox.
        dirty: Rect | None = None
        for name, (key, bbox) in boxes.items():
            prev = self._prev.get(name)
            if prev is None or prev[0] != key or name == "overlays":
                dirty = union(dirty, bbox)
                if prev is not None:
                    dirty = union(dirty, prev[1])
        self._prev = boxes
        return frame, dirty or (0, 0, 0, 0)

    def _blend_clipped(self, frame, x, y, alpha, colour):
        """Blend a layer but only inside the sclera disc."""
        h, w = alpha.shape
        sx0, sy0 = self.c - self._sclera.shape[1] // 2, self.c - self._sclera.shape[0] // 2
        # overlap of the layer with the sclera sprite, in layer coordinates
        ox0, oy0 = max(x, sx0), max(y, sy0)
        ox1, oy1 = min(x + w, sx0 + self._sclera.shape[1]), min(y + h, sy0 + self._sclera.shape[0])
        if ox1 <= ox0 or oy1 <= oy0:
            return None
        clipped = np.zeros_like(alpha)
        clipped[oy0 - y:oy1 - y, ox0 - x:ox1 - x] = alpha[oy0 - y:oy1 - y, ox0 - x:ox1 - x] * \
            self._sclera[oy0 - sy0:oy1 - sy0, ox0 - sx0:ox1 - sx0]
        return sprites.blend(frame, x, y, clipped, colour)

    def full_rect(self) -> Rect:
        return (0, 0, self.size, self.size)
