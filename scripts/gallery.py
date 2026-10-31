"""Render every expression preset (plus a mid-blink frame) into one PNG for review.

Usage: uv run python scripts/gallery.py [out.png]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from microduck_eyes import config as config_mod  # noqa: E402
from microduck_eyes.eye.animator import Animator  # noqa: E402
from microduck_eyes.eye.expressions import ORDER  # noqa: E402
from microduck_eyes.eye.renderer import EyeRenderer  # noqa: E402


def main(out: str = "screenshots/gallery.png"):
    cfg = config_mod.load()
    size = cfg.panel.size
    renderers = [EyeRenderer(cfg, "left"), EyeRenderer(cfg, "right")]
    anim = Animator(cfg, 0.0, seed=0)
    anim.set_idle(False, 0.0)
    anim.next_blink_at = 1e9
    tiles = []
    labels = list(ORDER) + ["blink 50%", "blink 100%", "look right", "look up-left"]
    for name in ORDER:
        anim.set_expression(name, 0.0, dur_ms=0)
        l, r, _ = anim.update(0.0)
        tiles.append((renderers[0].render(l)[0].copy(), renderers[1].render(r)[0].copy()))
    anim.set_expression("neutral", 0.0, dur_ms=0)
    for t in (0.07, 0.11):   # close phase is 100 ms: ~50% and fully closed
        anim.blink_t0 = 0.0
        l, r, _ = anim.update(t)
        tiles.append((renderers[0].render(l)[0].copy(), renderers[1].render(r)[0].copy()))
    anim.blink_t0 = -1.0
    anim.look_at(150, 0, 10.0, dur_ms=0)
    l, r, _ = anim.update(10.0)
    tiles.append((renderers[0].render(l)[0].copy(), renderers[1].render(r)[0].copy()))
    anim.look_at(-120, -100, 20.0, dur_ms=0)
    l, r, _ = anim.update(20.0)
    tiles.append((renderers[0].render(l)[0].copy(), renderers[1].render(r)[0].copy()))

    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    gap = 12
    tile_w = size * 2 + gap
    tile_h = size + 24
    sheet = np.full((rows * tile_h + gap, cols * (tile_w + gap) + gap, 3), (60, 60, 60), np.uint8)
    import pygame

    pygame.init()
    font = pygame.font.SysFont("menlo,monaco,consolas,monospace", 14)
    surf = pygame.Surface(sheet.shape[1::-1])
    surf.blit(pygame.image.frombuffer(sheet.tobytes(), sheet.shape[1::-1], "RGB"), (0, 0))
    for i, ((lf, rf), label) in enumerate(zip(tiles, labels)):
        row, col = divmod(i, cols)
        x = gap + col * (tile_w + gap)
        y = gap + row * tile_h
        surf.blit(pygame.image.frombuffer(np.ascontiguousarray(lf).tobytes(), (size, size), "RGB"), (x, y + 20))
        surf.blit(pygame.image.frombuffer(np.ascontiguousarray(rf).tobytes(), (size, size), "RGB"), (x + size + gap, y + 20))
        surf.blit(font.render(label, True, (240, 240, 240)), (x, y + 2))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, out)
    print(f"saved {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
