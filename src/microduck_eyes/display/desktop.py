"""pygame window showing the two round panels at true physical scale.

Two views:
  screens  only what the panels show: the round active areas (and the module's thin black
           border) on a dark bench, at life size or an exact multiple of it.
  face     the same panels set into a face-coloured head, for judging the mockup.

Life size uses the host display's points-per-millimetre (CoreGraphics on macOS, 96 dpi
fallback elsewhere). At 1x a GC9A01 pixel (0.135 mm) is smaller than a window point on most
laptops, so frames are area-averaged down; at 2x and above each panel pixel covers more than
one window point and the real pixel grid shows. `G` adds the inter-pixel gaps of a real LCD.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Config

Rect = tuple[int, int, int, int]

ZOOMS = [1.0, 2.0, 3.0, 4.0, 6.0]
ACTIVE_MM = 240 / 7.4        # overridden by cfg.panel in compute_layout


def detect_pt_per_mm() -> tuple[float, str]:
    """Window points per millimetre of the main display, and where the number came from."""
    if sys.platform == "darwin":
        try:
            import ctypes

            cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")

            class CGSize(ctypes.Structure):
                _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

            cg.CGMainDisplayID.restype = ctypes.c_uint32
            cg.CGDisplayScreenSize.restype = CGSize
            cg.CGDisplayScreenSize.argtypes = [ctypes.c_uint32]
            cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
            cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
            d = cg.CGMainDisplayID()
            mm = cg.CGDisplayScreenSize(d).width
            pts = cg.CGDisplayPixelsWide(d)
            if mm > 50 and pts > 100:
                return pts / mm, "CoreGraphics"
        except Exception:  # pragma: no cover - depends on host
            pass
    return 96.0 / 25.4, "assumed 96 dpi"


@dataclass
class Layout:
    pt_per_mm: float
    zoom: float
    panel_px: int            # window px across one panel's active area
    bezel_px: int
    k: int                   # integer pre-scale so pixels stay crisp before the final resample
    spacing_px: int
    width: int
    height: int
    centres: list[tuple[int, int]]
    origins: list[tuple[int, int]]
    pair_centre: tuple[int, int]
    px_per_screen_px: float
    panel_w: int = 0


def compute_layout(cfg: Config, pt_per_mm: float, zoom: float, spacing_mm: float, hud_h: int, panel_w: int = 0) -> Layout:
    size = cfg.panel.size
    active_mm = size / cfg.panel.px_per_mm
    panel_px = max(int(round(active_mm * pt_per_mm * zoom)), 24)
    bezel_px = max(int(round(cfg.layout.bezel_mm * pt_per_mm * zoom)), 1)
    k = max(1, math.ceil(panel_px / size))
    spacing_px = int(round(spacing_mm * pt_per_mm * zoom))
    margin = int(round(6 * pt_per_mm * zoom))
    outer = panel_px + 2 * bezel_px
    width = max(spacing_px + outer, 2 * outer + 10) + 2 * margin
    width = max(width, 640)                               # room for the HUD text
    height = max(outer + 2 * margin + hud_h, 560 if panel_w else 0)
    cx, cy = width // 2, margin + outer // 2
    width += panel_w
    centres = [(cx - spacing_px // 2, cy), (cx + spacing_px // 2, cy)]
    origins = [(c[0] - panel_px // 2, c[1] - panel_px // 2) for c in centres]
    lay = Layout(pt_per_mm, zoom, panel_px, bezel_px, k, spacing_px, width, height, centres, origins, (cx, cy),
                  panel_px / size)
    lay.panel_w = panel_w
    return lay


class DesktopDisplay:
    HUD_H = 90
    BENCH = (30, 30, 33)

    def __init__(self, cfg: Config, zoom: float = 1.0, view: str = "screens", pt_per_mm: float | None = None,
                 title: str = "Microduck eyes"):
        import pygame  # optional dependency, only the simulator needs it

        self.pg = pygame
        self.cfg = cfg
        self.view = view
        self.zoom = zoom
        self.pixel_gaps = False
        self.brightness = 1.0          # backlight simulation, 0..1 (PWM on the real BLK pin)
        self.dome = False              # clear dome lens over each panel
        self._lut_b = None
        self._lut = None
        self.panel_w = 0               # width reserved on the right for the control panel
        self.spacing_mm = cfg.layout.eye_spacing_mm
        self.hud_lines: list[str] = []
        self.show_dirty = False
        if pt_per_mm:
            self.pt_per_mm, self.pt_source = pt_per_mm, "command line"
        else:
            self.pt_per_mm, self.pt_source = detect_pt_per_mm()
        pygame.init()
        pygame.display.set_caption(title)
        self.font = pygame.font.SysFont("menlo,monaco,consolas,monospace", 13)
        self.window = None
        self._layout()

    # ---- layout -------------------------------------------------------
    def _layout(self):
        pg = self.pg
        self.lay = compute_layout(self.cfg, self.pt_per_mm, self.zoom, self.spacing_mm, self.HUD_H, self.panel_w)
        L = self.lay
        self.window = pg.display.set_mode((L.width, L.height))
        self.overlay = self._make_overlay()
        self.grid = self._make_grid()
        self._dome_maps = None
        self._dome_shine = None
        self.window.fill(self.cfg.colours.face if self.view == "face" else self.BENCH)
        for ox, oy in L.origins:
            self.window.blit(self.overlay, (ox - L.bezel_px, oy - L.bezel_px))

    def _make_overlay(self):
        """Mask with a transparent circular hole, a black module border and the surround colour."""
        pg = self.pg
        L = self.lay
        n = L.panel_px + 2 * L.bezel_px
        c = (n - 1) / 2.0
        r_active = L.panel_px / 2.0
        ys, xs = np.mgrid[0:n, 0:n]
        dist = np.hypot(xs - c, ys - c)
        rgba = np.empty((n, n, 4), np.uint8)
        rgba[..., :3] = self.cfg.colours.face if self.view == "face" else self.BENCH
        ring = dist < r_active + L.bezel_px
        rgba[ring, :3] = (8, 8, 8)
        rgba[..., 3] = (np.clip(dist - r_active + 0.5, 0.0, 1.0) * 255).astype(np.uint8)
        return pg.image.frombuffer(rgba.tobytes(), (n, n), "RGBA").convert_alpha()

    def _make_grid(self):
        """Inter-pixel gap mask at the integer pre-scale; multiplied onto the upscaled frame."""
        L = self.lay
        size = self.cfg.panel.size
        n = size * L.k
        g = np.full((n, n, 3), 255, np.uint8)
        if L.k >= 3:
            g[L.k - 1::L.k, :] = 150        # inter-pixel gap: darker, but a real panel's aperture is not black
            g[:, L.k - 1::L.k] = 150
        return self.pg.image.frombuffer(g.tobytes(), (n, n), "RGB").convert()

    def _make_dome(self):
        """Index maps for a barrel-magnified centre plus a specular highlight, at the panel size."""
        n = self.lay.panel_px
        c = (n - 1) / 2.0
        ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
        dx, dy = (xs - c) / c, (ys - c) / c
        rho = np.hypot(dx, dy)
        rho_c = np.clip(rho, 0, 1)
        k = 0.22
        src = rho_c * (1.0 - k * (1.0 - rho_c ** 2))          # centre magnified, edge fixed
        scale = np.where(rho > 1e-6, src / np.maximum(rho, 1e-6), 1.0)
        sx = np.clip(np.round(c + dx * c * scale), 0, n - 1).astype(np.intp)
        sy = np.clip(np.round(c + dy * c * scale), 0, n - 1).astype(np.intp)
        self._dome_maps = (sy, sx)
        shine = np.clip(1.0 - np.hypot(dx + 0.42, dy + 0.42) / 0.42, 0, 1) ** 1.6 * 0.55
        rim = np.clip((rho - 0.86) / 0.14, 0, 1) * (rho <= 1.0) * 0.35
        rgba = np.zeros((n, n, 4), np.uint8)
        rgba[..., :3] = 255
        rgba[..., 3] = (np.clip(shine, 0, 1) * 255).astype(np.uint8)
        self._dome_shine = self.pg.image.frombuffer(rgba.tobytes(), (n, n), "RGBA").convert_alpha()
        rim_rgba = np.zeros((n, n, 4), np.uint8)
        rim_rgba[..., 3] = (rim * 255).astype(np.uint8)
        self._dome_rim = self.pg.image.frombuffer(rim_rgba.tobytes(), (n, n), "RGBA").convert_alpha()

    def _apply_brightness(self, frame: np.ndarray) -> np.ndarray:
        b = round(min(max(self.brightness, 0.0), 1.0), 2)
        if b >= 0.995:
            return frame
        if self._lut_b != b:
            self._lut = (np.arange(256) * b + 0.5).astype(np.uint8)
            self._lut_b = b
        return self._lut[frame]

    def set_zoom(self, zoom: float):
        self.zoom = max(0.5, min(zoom, 8.0))
        self._layout()

    def step_zoom(self, step: int):
        i = min(range(len(ZOOMS)), key=lambda j: abs(ZOOMS[j] - self.zoom))
        self.set_zoom(ZOOMS[max(0, min(len(ZOOMS) - 1, i + step))])

    def set_view(self, view: str):
        self.view = view
        self._layout()

    def set_spacing(self, spacing_mm: float):
        self.spacing_mm = max(35.0, min(spacing_mm, 120.0))
        self._layout()

    # ---- drawing ------------------------------------------------------
    def show(self, index: int, frame: np.ndarray, dirty: Rect) -> None:
        pg = self.pg
        L = self.lay
        size = frame.shape[0]
        frame = self._apply_brightness(frame)
        surf = pg.image.frombuffer(np.ascontiguousarray(frame).tobytes(), (size, size), "RGB")
        if L.k > 1:
            surf = pg.transform.scale(surf, (size * L.k, size * L.k))        # crisp integer step
            if self.pixel_gaps and L.k >= 3:
                surf.blit(self.grid, (0, 0), special_flags=pg.BLEND_RGB_MULT)
        if surf.get_width() != L.panel_px:
            surf = pg.transform.smoothscale(surf, (L.panel_px, L.panel_px))  # area-averaged to true size
        if self.dome:
            if self._dome_maps is None:
                self._make_dome()
            arr = pg.surfarray.array3d(surf).swapaxes(0, 1)            # (h, w, 3)
            sy, sx = self._dome_maps
            warped = np.ascontiguousarray(arr[sy, sx])
            surf = pg.image.frombuffer(warped.tobytes(), (L.panel_px, L.panel_px), "RGB")
        ox, oy = L.origins[index]
        self.window.blit(surf, (ox, oy))
        if self.dome:
            self.window.blit(self._dome_rim, (ox, oy))
            self.window.blit(self._dome_shine, (ox, oy))
        self.window.blit(self.overlay, (ox - L.bezel_px, oy - L.bezel_px))
        if self.show_dirty and dirty[2] > dirty[0]:
            s = L.px_per_screen_px
            r = pg.Rect(ox + int(dirty[0] * s), oy + int(dirty[1] * s), int((dirty[2] - dirty[0]) * s), int((dirty[3] - dirty[1]) * s))
            pg.draw.rect(self.window, (255, 0, 255), r, 1)

    def set_hud(self, lines: list[str]):
        self.hud_lines = lines

    def scale_text(self) -> str:
        L = self.lay
        return f"{L.zoom:g}x life size ({L.px_per_screen_px:.2f} window px per screen px, {L.pt_per_mm:.2f} pt/mm via {self.pt_source})"

    def set_panel_width(self, w: int):
        self.panel_w = max(0, int(w))
        self._layout()

    def flip(self, draw_extra=None) -> None:
        pg = self.pg
        w, h = self.window.get_size()
        w -= self.panel_w
        hud = pg.Rect(0, h - self.HUD_H, w, self.HUD_H)
        pg.draw.rect(self.window, (18, 18, 18), hud)
        y = hud.y + 6
        for line in self._wrap(self.hud_lines, w - 20):
            if y + 16 > h:
                break
            self.window.blit(self.font.render(line, True, (230, 230, 230)), (10, y))
            y += 16
        if draw_extra is not None:
            draw_extra(self.window)
        pg.display.flip()

    def _wrap(self, lines: list[str], max_w: int) -> list[str]:
        """Greedy wrap on double-space separators so the HUD fits narrow (life-size) windows."""
        out: list[str] = []
        for line in lines:
            parts = [p for p in line.split("  ") if p]
            cur = ""
            for part in parts:
                cand = part if not cur else cur + "  " + part
                if self.font.size(cand)[0] <= max_w or not cur:
                    cur = cand
                else:
                    out.append(cur)
                    cur = part
            if cur:
                out.append(cur)
        return out

    def screenshot(self, directory: Path | str = "screenshots") -> Path:
        import time

        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        path = d / time.strftime("eyes-%Y%m%d-%H%M%S.png")
        self.pg.image.save(self.window, str(path))
        return path

    # ---- input helpers ------------------------------------------------
    def window_to_mm(self, pos: tuple[int, int]) -> tuple[float, float]:
        k = 1.0 / (self.pt_per_mm * self.zoom)
        return ((pos[0] - self.lay.pair_centre[0]) * k, (pos[1] - self.lay.pair_centre[1]) * k)

    def close(self) -> None:
        self.pg.quit()
