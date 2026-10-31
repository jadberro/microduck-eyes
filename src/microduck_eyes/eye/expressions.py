"""Named expression presets, defined relative to the face (inner/outer), not the screen."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class EyeParams:
    lid_upper: float = 0.0
    lid_lower: float = 0.0
    tilt_inner: float = 0.0   # + means the lid edge is lower at the inner corner (towards the beak)
    pupil_scale: float = 1.0
    gaze_dx_inner: float = 0.0  # px bias towards the inner corner
    gaze_dy: float = 0.0        # px bias, + is down
    brow_y: float = 0.0         # px lowered (negative = raised)
    brow_inner: float = 0.0     # degrees; positive = inner end of the brow lower (anger), negative = inner up (worry)


@dataclass(frozen=True)
class Expression:
    name: str
    both: EyeParams = EyeParams()
    left: EyeParams | None = None   # per-side override, viewer's left panel
    right: EyeParams | None = None

    def for_side(self, side: str) -> EyeParams:
        override = self.left if side == "left" else self.right
        return override if override is not None else self.both


def _e(name: str, **kw) -> Expression:
    left = kw.pop("left", None)
    right = kw.pop("right", None)
    both = EyeParams(**kw)
    return Expression(
        name,
        both,
        replace(both, **left) if left else None,
        replace(both, **right) if right else None,
    )


PRESETS: dict[str, Expression] = {
    "neutral": _e("neutral"),
    "happy": _e("happy", lid_lower=0.45, lid_upper=0.08, gaze_dy=-4, brow_y=-3),
    "sleepy": _e("sleepy", lid_upper=0.55, lid_lower=0.12, pupil_scale=1.05, gaze_dy=3, brow_y=4),
    "surprised": _e("surprised", pupil_scale=0.72, brow_y=-9),
    "sad": _e("sad", lid_upper=0.3, lid_lower=0.1, tilt_inner=-0.35, gaze_dy=8, brow_y=-2, brow_inner=-14),
    "curious": _e("curious", left={"lid_upper": 0.35, "brow_y": 5}, right={"lid_upper": 0.0, "brow_y": -8}),
    "love": _e("love", pupil_scale=1.35, lid_lower=0.3, lid_upper=0.05, brow_y=-4),
    "asleep": _e("asleep", lid_upper=1.0, lid_lower=1.0, brow_y=2),
    "angry": _e("angry", lid_upper=0.32, tilt_inner=0.45, pupil_scale=0.9, brow_y=9, brow_inner=16),
    "suspicious": _e("suspicious", lid_upper=0.5, lid_lower=0.3, pupil_scale=0.95, left={"brow_y": 7}, right={"brow_y": -3}),
}

# Order used by number keys and the E key cycle. Cute set first.
ORDER = ["neutral", "happy", "sleepy", "surprised", "sad", "curious", "love", "asleep", "angry", "suspicious"]


def screen_tilt(params: EyeParams, side: str) -> float:
    """Convert inner/outer tilt to screen tilt (drop at right side vs left).

    The left panel's inner corner is its right side, so the sign flips for the right panel.
    """
    return params.tilt_inner if side == "left" else -params.tilt_inner


def inner_sign(side: str) -> float:
    """+1 if the inner corner is in +x screen direction for this side."""
    return 1.0 if side == "left" else -1.0


def screen_brow_tilt(params: EyeParams, side: str) -> float:
    """Brow tilt in screen degrees: positive drops the right end. Inner end is right for the left panel."""
    return params.brow_inner if side == "left" else -params.brow_inner
