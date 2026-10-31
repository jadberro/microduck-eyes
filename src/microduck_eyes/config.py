"""Configuration dataclasses and TOML loader (stdlib tomllib, no extra deps)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

RGB = tuple[int, int, int]


@dataclass
class PanelCfg:
    size: int = 240
    px_per_mm: float = 7.4


@dataclass
class LayoutCfg:
    eye_spacing_mm: float = 45.0
    bezel_mm: float = 1.5
    gaze_depth_mm: float = 300.0


@dataclass
class ColourCfg:
    face: RGB = (255, 204, 0)
    sclera: RGB = (255, 255, 255)
    outline: RGB = (40, 30, 20)
    pupil: RGB = (20, 16, 14)
    highlight: RGB = (255, 255, 255)
    lid_edge: RGB = (225, 150, 0)


@dataclass
class EyeCfg:
    sclera_r: int = 106
    outline_w: int = 3
    pupil_r: int = 46
    pupil_margin: int = 4
    highlight_big_r: int = 11
    highlight_big_offset: tuple[int, int] = (-16, -16)
    highlight_small_r: int = 5
    highlight_small_offset: tuple[int, int] = (12, 14)
    lid_curve: float = 0.18
    lid_edge_w: float = 2.5
    lid_meet_y: float = 0.3


@dataclass
class AnimCfg:
    blink_close_ms: int = 100
    blink_hold_ms: int = 40
    blink_open_ms: int = 160
    blink_interval_s: tuple[float, float] = (2.0, 6.0)
    double_blink_chance: float = 0.15
    saccade_interval_s: tuple[float, float] = (0.6, 2.2)
    saccade_range_mm: float = 60.0
    gaze_move_ms: int = 180
    expression_ms: int = 300
    mouse_idle_after_s: float = 3.0


@dataclass
class BrowCfg:
    enabled: bool = True
    colour: RGB = (60, 40, 25)
    thickness: float = 8.0
    radius: float = 113.0          # arc radius from the panel centre at rest
    half_angle_deg: float = 36.0


@dataclass
class IrisCfg:
    enabled: bool = True
    scale: float = 1.45            # times the pupil radius
    colour: RGB = (214, 150, 48)
    mood_colour: RGB = (236, 118, 92)


@dataclass
class PersonalityCfg:
    lazy_eye: float = 0.0          # 0..1, right eye lags and drifts outward
    wink_chance: float = 0.08      # chance a blink becomes a wink
    glance_away_s: tuple[float, float] = (4.0, 9.0)


@dataclass
class CameraCfg:
    enabled: bool = False
    index: int = 0
    width: int = 320
    height: int = 240
    hfov_deg: float = 60.0
    face_width_mm: float = 150.0
    mirror: bool = False
    fps: float = 10.0


@dataclass
class BehaviourCfg:
    enabled: bool = True
    light_adapt_s: float = 0.8
    pupil_dark: float = 1.25
    pupil_bright: float = 0.80
    vor_gain: float = 0.9          # px of counter-rotation per degree of head turn
    vor_decay_s: float = 0.5
    morning_hour: int = 6
    evening_hour: int = 20
    night_hour: int = 23
    low_battery: float = 15.0


@dataclass
class Config:
    panel: PanelCfg = field(default_factory=PanelCfg)
    layout: LayoutCfg = field(default_factory=LayoutCfg)
    colours: ColourCfg = field(default_factory=ColourCfg)
    eye: EyeCfg = field(default_factory=EyeCfg)
    animation: AnimCfg = field(default_factory=AnimCfg)
    brows: BrowCfg = field(default_factory=BrowCfg)
    iris: IrisCfg = field(default_factory=IrisCfg)
    personality: PersonalityCfg = field(default_factory=PersonalityCfg)
    camera: CameraCfg = field(default_factory=CameraCfg)
    behaviour: BehaviourCfg = field(default_factory=BehaviourCfg)


def _build(cls: type, data: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {}
    known = {f.name: f for f in fields(cls)}
    for key, value in data.items():
        if key not in known:
            raise KeyError(f"unknown config key '{key}' in [{cls.__name__}]")
        ftype = known[key].type
        if isinstance(value, dict):
            sub = next(f for f in fields(cls) if f.name == key).default_factory  # type: ignore[union-attr]
            kwargs[key] = _build(sub, value)  # type: ignore[arg-type]
        elif isinstance(value, list):
            kwargs[key] = tuple(value)
        else:
            kwargs[key] = value
        del ftype
    return cls(**kwargs)


def default_config_path() -> Path:
    """config/eyes.toml at the repo root, when running from a checkout."""
    return Path(__file__).resolve().parents[2] / "config" / "eyes.toml"


def load(path: Path | str | None = None) -> Config:
    """Load config from TOML; missing file means built-in defaults."""
    p = Path(path) if path else default_config_path()
    if not p.exists():
        if path:
            raise FileNotFoundError(p)
        return Config()
    with p.open("rb") as fh:
        data = tomllib.load(fh)
    cfg = Config()
    for section, values in data.items():
        if not hasattr(cfg, section):
            raise KeyError(f"unknown config section [{section}]")
        current = getattr(cfg, section)
        assert is_dataclass(current)
        setattr(cfg, section, _build(type(current), values))
    return cfg
