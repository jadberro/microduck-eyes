"""EyeState: everything the renderer needs to draw one eye, in screen space."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..config import Config


@dataclass(frozen=True)
class EyeState:
    pupil_x: float = 0.0      # px offset from panel centre, +right
    pupil_y: float = 0.0      # px offset from panel centre, +down
    pupil_scale: float = 1.0  # multiplier on cfg.eye.pupil_r
    lid_upper: float = 0.0    # 0 fully open .. 1 closed to the meeting line
    lid_lower: float = 0.0
    lid_tilt: float = 0.0     # drop of the lid edge at the right side vs the left, in units of sclera_r
    highlights: bool = True
    pupil_sprite: str = "disc"   # or dollar / heart / spiral, see pupil_sprites.py
    pupil_frame: int = 0
    brow_y: float = 0.0          # px the brow is lowered (negative = raised)
    brow_tilt: float = 0.0       # degrees; positive drops the right end of the arc (screen space)
    brow: bool = True
    iris_scale: float = 1.0      # multiplier on cfg.iris.scale (0 hides the iris)
    iris_colour: tuple[int, int, int] | None = None   # None = config colour


def clamp(state: EyeState, cfg: Config) -> EyeState:
    """Keep the pupil fully inside the sclera and lids within range."""
    e = cfg.eye
    scale = min(max(state.pupil_scale, 0.3), 1.6)
    pr = e.pupil_r * scale
    max_off = e.sclera_r - e.outline_w - e.pupil_margin - pr
    max_off = max(max_off, 0.0)
    d = math.hypot(state.pupil_x, state.pupil_y)
    px, py = state.pupil_x, state.pupil_y
    if d > max_off and d > 0:
        k = max_off / d
        px, py = px * k, py * k
    return replace(
        state,
        pupil_x=px,
        pupil_y=py,
        pupil_scale=scale,
        lid_upper=min(max(state.lid_upper, 0.0), 1.0),
        lid_lower=min(max(state.lid_lower, 0.0), 1.0),
        lid_tilt=min(max(state.lid_tilt, -1.0), 1.0),
        brow_y=min(max(state.brow_y, -14.0), 22.0),
        brow_tilt=min(max(state.brow_tilt, -25.0), 25.0),
    )
