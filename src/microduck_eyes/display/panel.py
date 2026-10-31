"""In-window control panel: tabs of buttons, toggles and sliders for every option.

Pure pygame, no extra dependency. Widgets hold callables so highlighted states always
reflect the live app state. The panel sits in a right-hand column of the simulator window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

BG = (36, 36, 40)
TAB_BG = (26, 26, 30)
BTN = (62, 62, 70)
BTN_HOVER = (84, 84, 94)
ACTIVE = (240, 180, 30)
ACTIVE_TEXT = (30, 24, 10)
TEXT = (232, 232, 232)
HEADER = (165, 165, 175)
BAR = (90, 90, 100)
KNOB = (240, 180, 30)


@dataclass
class Widget:
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 24
    full_width: bool = False

    def contains(self, px, py) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def draw(self, pg, surf, font, ox, oy, mouse):  # pragma: no cover - trivial base
        pass

    def click(self, px, py) -> bool:
        return False


@dataclass
class Header(Widget):
    text: str = ""
    full_width: bool = True
    h: int = 20

    def draw(self, pg, surf, font, ox, oy, mouse):
        surf.blit(font.render(self.text.upper(), True, HEADER), (ox + self.x, oy + self.y + 4))


@dataclass
class Button(Widget):
    label: str = ""
    on_click: Callable[[], None] = lambda: None
    is_active: Callable[[], bool] | None = None
    hint: str = ""

    def draw(self, pg, surf, font, ox, oy, mouse):
        r = pg.Rect(ox + self.x, oy + self.y, self.w, self.h)
        active = bool(self.is_active()) if self.is_active else False
        hover = r.collidepoint(mouse)
        colour = ACTIVE if active else (BTN_HOVER if hover else BTN)
        pg.draw.rect(surf, colour, r, border_radius=5)
        text = font.render(self.label, True, ACTIVE_TEXT if active else TEXT)
        surf.blit(text, (r.x + (r.w - text.get_width()) // 2, r.y + (r.h - text.get_height()) // 2))

    def click(self, px, py) -> bool:
        self.on_click()
        return True


@dataclass
class Slider(Widget):
    label: str = ""
    get: Callable[[], float] = lambda: 0.0
    set: Callable[[float], None] = lambda v: None
    lo: float = 0.0
    hi: float = 1.0
    step: float = 0.01
    fmt: str = "{:.2f}"
    full_width: bool = True
    h: int = 26
    dragging: bool = False
    label_w: int = 96

    def _bar(self, ox, oy):
        return (ox + self.x + self.label_w, oy + self.y + 8, self.w - self.label_w - 52, 10)

    def draw(self, pg, surf, font, ox, oy, mouse):
        surf.blit(font.render(self.label, True, TEXT), (ox + self.x, oy + self.y + 5))
        bx, by, bw, bh = self._bar(ox, oy)
        pg.draw.rect(surf, BAR, pg.Rect(bx, by, bw, bh), border_radius=5)
        v = self.get()
        k = 0.0 if self.hi == self.lo else (min(max(v, self.lo), self.hi) - self.lo) / (self.hi - self.lo)
        pg.draw.circle(surf, KNOB, (int(bx + k * bw), by + bh // 2), 7)
        surf.blit(font.render(self.fmt.format(v), True, TEXT), (bx + bw + 8, oy + self.y + 5))

    def value_at(self, px, ox):
        bx, _, bw, _ = self._bar(ox, 0)
        k = min(max((px - bx) / max(bw, 1), 0.0), 1.0)
        v = self.lo + k * (self.hi - self.lo)
        if self.step:
            v = round(round(v / self.step) * self.step, 6)
        return v

    def click(self, px, py) -> bool:
        self.dragging = True
        return True


class Panel:
    WIDTH = 330
    TABS_H = 28
    PAD = 8
    GAP = 4

    def __init__(self, pg, font, tabs: list[tuple[str, Callable[[], list[Widget]]]]):
        self.pg = pg
        self.font = font
        self.tab_defs = tabs
        self.tab = 0
        self.scroll = [0] * len(tabs)
        self.widgets: list[Widget] = []
        self.content_h = 0
        self.rect = pg.Rect(0, 0, self.WIDTH, 100)
        self.visible = True
        self._drag: Slider | None = None
        self.rebuild()

    # ---- layout -------------------------------------------------------
    def rebuild(self):
        self.widgets = self.tab_defs[self.tab][1]()
        width = self.WIDTH - 2 * self.PAD
        x = y = 0
        line_h = 0
        for w in self.widgets:
            if isinstance(w, Button) and not w.w:
                w.w = max(self.font.size(w.label)[0] + 16, 54)
            if w.full_width:
                if x > 0:
                    y += line_h + self.GAP
                    x, line_h = 0, 0
                w.x, w.y, w.w = 0, y, width
                y += w.h + self.GAP
                continue
            if x + w.w > width and x > 0:
                y += line_h + self.GAP
                x, line_h = 0, 0
            w.x, w.y = x, y
            x += w.w + self.GAP
            line_h = max(line_h, w.h)
        if x > 0:
            y += line_h
        self.content_h = y + self.PAD

    def set_tab(self, i: int):
        self.tab = i % len(self.tab_defs)
        self.rebuild()

    def place(self, x: int, y: int, h: int):
        self.rect = self.pg.Rect(x, y, self.WIDTH, h)

    def contains(self, pos) -> bool:
        return self.visible and self.rect.collidepoint(pos)

    # ---- drawing ------------------------------------------------------
    def draw(self, surf, mouse):
        if not self.visible:
            return
        pg = self.pg
        pg.draw.rect(surf, BG, self.rect)
        pg.draw.rect(surf, TAB_BG, pg.Rect(self.rect.x, self.rect.y, self.rect.w, self.TABS_H))
        tw = self.rect.w // len(self.tab_defs)
        for i, (name, _) in enumerate(self.tab_defs):
            r = pg.Rect(self.rect.x + i * tw, self.rect.y, tw, self.TABS_H)
            if i == self.tab:
                pg.draw.rect(surf, BG, r)
                pg.draw.rect(surf, ACTIVE, pg.Rect(r.x, r.y, r.w, 3))
            text = self.font.render(name, True, TEXT if i == self.tab else HEADER)
            surf.blit(text, (r.x + (r.w - text.get_width()) // 2, r.y + 7))
        content = pg.Rect(self.rect.x, self.rect.y + self.TABS_H, self.rect.w, self.rect.h - self.TABS_H)
        old_clip = surf.get_clip()
        surf.set_clip(content)
        ox = content.x + self.PAD
        oy = content.y + self.PAD - self.scroll[self.tab]
        for w in self.widgets:
            if oy + w.y + w.h < content.y or oy + w.y > content.bottom:
                continue
            w.draw(pg, surf, self.font, ox, oy, mouse)
        surf.set_clip(old_clip)
        view_h = content.h - self.PAD
        if self.content_h > view_h:
            track = pg.Rect(self.rect.right - 5, content.y, 4, content.h)
            pg.draw.rect(surf, TAB_BG, track)
            k = view_h / self.content_h
            pos = self.scroll[self.tab] / max(self.content_h - view_h, 1)
            thumb_h = max(int(track.h * k), 20)
            pg.draw.rect(surf, BAR, pg.Rect(track.x, track.y + int((track.h - thumb_h) * pos), 4, thumb_h), border_radius=2)

    # ---- events -------------------------------------------------------
    def _content_origin(self):
        return self.rect.x + self.PAD, self.rect.y + self.TABS_H + self.PAD - self.scroll[self.tab]

    def handle(self, ev) -> bool:
        """Returns True when the event was consumed by the panel."""
        pg = self.pg
        if not self.visible:
            return False
        if ev.type == pg.MOUSEMOTION:
            if self._drag is not None:
                ox, _ = self._content_origin()
                self._drag.set(self._drag.value_at(ev.pos[0], ox))
                return True
            return self.rect.collidepoint(ev.pos)
        if ev.type == pg.MOUSEBUTTONUP:
            if self._drag is not None:
                self._drag.dragging = False
                self._drag = None
                return True
            return self.rect.collidepoint(ev.pos)
        if ev.type == pg.MOUSEWHEEL:
            mouse = pg.mouse.get_pos()
            if self.rect.collidepoint(mouse):
                view_h = self.rect.h - self.TABS_H - self.PAD
                self.scroll[self.tab] = int(min(max(self.scroll[self.tab] - ev.y * 30, 0), max(self.content_h - view_h, 0)))
                return True
            return False
        if ev.type == pg.MOUSEBUTTONDOWN and ev.button in (1, 2, 3):
            if not self.rect.collidepoint(ev.pos):
                return False
            if ev.button != 1:
                return True
            if ev.pos[1] < self.rect.y + self.TABS_H:
                tw = self.rect.w // len(self.tab_defs)
                self.set_tab(min((ev.pos[0] - self.rect.x) // tw, len(self.tab_defs) - 1))
                return True
            ox, oy = self._content_origin()
            px, py = ev.pos[0] - ox, ev.pos[1] - oy
            for w in self.widgets:
                if w.contains(px, py):
                    if isinstance(w, Slider):
                        self._drag = w
                        w.set(w.value_at(ev.pos[0], ox))
                    w.click(px, py)
                    break
            return True
        return False
