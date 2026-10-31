"""Sensor hub: one place where simulated inputs, the camera and external messages land.

Sources call `set(...)`, `face(...)` and `event(...)`; the behaviour engine and games read
`state` and `recent(kind, since)`. Transitions (face found/lost, touch, cover, charging,
wifi lost, low battery) are turned into events automatically so consumers can react once.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Face:
    x_mm: float
    y_mm: float
    z_mm: float
    seen_at: float


@dataclass
class SensorState:
    face: Face | None = None
    light: float = 0.6                 # 0 dark .. 1 bright
    light_dir: tuple[float, float] = (-0.5, -0.7)   # direction of the brightest light (x right, y down), unit-ish
    sound: float = 0.0                 # current level 0..1
    head_yaw_rate: float = 0.0         # deg/s, positive = head turning to its right
    head_pitch_rate: float = 0.0       # deg/s, positive = nodding down
    head_yaw: float = 0.0              # integrated degrees (decays slowly so it stays bounded)
    head_pitch: float = 0.0
    touch: bool = False
    camera_covered: bool = False
    battery: float = 100.0
    charging: bool = False
    wifi: int = 3                      # bars 0..3
    listening: bool = False
    thinking: bool = False
    speaking: bool = False
    weather: str | None = None
    heading: float | None = None
    hour: float | None = None          # time-of-day override; None = wall clock


@dataclass
class Event:
    kind: str
    t: float
    data: dict = field(default_factory=dict)


class SensorHub:
    KEEP_S = 6.0

    def __init__(self, low_battery: float = 15.0):
        self.state = SensorState()
        self.events: list[Event] = []
        self.low_battery = low_battery
        self._last_integrate: float | None = None

    # ---- writing --------------------------------------------------------
    def event(self, kind: str, now: float, **data):
        self.events.append(Event(kind, now, data))
        self._prune(now)

    def set(self, now: float, **fields):
        """Update fields and emit transition events."""
        s = self.state
        for k, v in fields.items():
            if not hasattr(s, k):
                raise KeyError(k)
            old = getattr(s, k)
            setattr(s, k, v)
            if k == "touch" and v != old:
                self.event("touch_start" if v else "touch_end", now)
            elif k == "camera_covered" and v != old:
                self.event("covered" if v else "uncovered", now)
            elif k == "charging" and v != old:
                self.event("charging_start" if v else "charging_stop", now)
            elif k == "wifi" and v != old and v == 0:
                self.event("wifi_lost", now)
            elif k == "battery" and v <= self.low_battery < (old if old is not None else 100):
                self.event("battery_low", now)
            elif k == "listening" and v != old:
                self.event("listening_start" if v else "listening_stop", now)
            elif k == "thinking" and v != old:
                self.event("thinking_start" if v else "thinking_stop", now)
            elif k == "sound" and v >= 0.6 and (old is None or old < 0.6):
                self.events.append(Event("sound", now, {"kind": "loud", "level": v}))

    def face(self, now: float, x_mm: float, y_mm: float, z_mm: float = 300.0):
        if self.state.face is None:
            self.event("face_found", now)
        self.state.face = Face(float(x_mm), float(y_mm), float(max(z_mm, 50.0)), now)

    def face_lost(self, now: float):
        if self.state.face is not None:
            self.state.face = None
            self.event("face_lost", now)

    def integrate(self, now: float):
        """Integrate head rates into angles (leaky, so a steady drift does not wind up forever)."""
        if self._last_integrate is None:
            self._last_integrate = now
            return
        dt = min(max(now - self._last_integrate, 0.0), 0.1)
        self._last_integrate = now
        s = self.state
        decay = max(0.0, 1.0 - dt / 3.0)
        s.head_yaw = (s.head_yaw + s.head_yaw_rate * dt) * decay
        s.head_pitch = (s.head_pitch + s.head_pitch_rate * dt) * decay
        if s.face is not None and now - s.face.seen_at > 2.5:
            self.face_lost(now)

    # ---- reading --------------------------------------------------------
    def recent(self, kind: str, since: float) -> list[Event]:
        return [e for e in self.events if e.kind == kind and e.t >= since]

    def last(self, kind: str) -> Event | None:
        for e in reversed(self.events):
            if e.kind == kind:
                return e
        return None

    def _prune(self, now: float):
        cutoff = now - self.KEEP_S
        if self.events and self.events[0].t < cutoff:
            self.events = [e for e in self.events if e.t >= cutoff]
