"""Render every theme into one PNG (two panels per theme, at a representative moment).

Usage: uv run python scripts/gallery_themes.py [out.png]
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
from microduck_eyes.eye.renderer import EyeRenderer  # noqa: E402
from microduck_eyes.eye.scenes import SceneRenderer  # noqa: E402
from microduck_eyes.eye.themes import THEMES, ThemeController  # noqa: E402

# Moment (seconds after start) that shows each theme at its best.
SHOT_AT = {
    "hal": 1.0, "terminator": 0.5, "aperture": 0.6, "eve": 0.5, "matrix": 0.6, "spiral": 0.3, "pirate": 0.1,
    "sunglasses": 1.0, "laser": 0.1, "dollar": 2.0, "slot": 3.2, "dice": 1.5, "eightball": 1.2, "poker": 7.3,
    "debate": 1.0, "campaign": 0.6, "election": 5.0, "filibuster": 12.0, "diplomat": 0.8, "tax": 1.5,
    "boot": 3.4, "crt": 0.25, "buffering": 0.3, "bsod": 2.0, "notfound": 0.5, "battery": 4.0, "roll": 0.5,
    "googly": 0.6, "hearts": 1.5, "knockout": 0.4, "dizzy": 0.6, "laughcry": 1.2, "sweat": 1.0, "anime": 0.1,
    "cateyes": 0.5, "zzz": 2.5, "monocle": 0.1, "bread": 0.1, "catalert": 0.5, "rubberduck": 0.5, "migration": 0.1,
}


def main(out: str = "screenshots/gallery-themes.png", subset: str = ""):
    """`subset` is an optional "start:stop" slice of the theme list (for smaller sheets)."""
    cfg = config_mod.load()
    names = THEMES
    if subset:
        a, _, b = subset.partition(":")
        names = THEMES[int(a or 0):int(b) if b else None]
    size = cfg.panel.size
    renderers = [EyeRenderer(cfg, "left"), EyeRenderer(cfg, "right")]
    scenes = SceneRenderer(cfg)
    anim = Animator(cfg, 0.0, seed=0)
    anim.set_idle(False, 0.0)
    anim.next_blink_at = 1e9
    l0, r0, _ = anim.update(0.0)
    sources = [renderers[0].render(l0)[0].copy(), renderers[1].render(r0)[0].copy()]
    tc = ThemeController(cfg, seed=3, anim=anim, scenes=scenes)

    rows = []
    t0 = 100.0
    for name in names:
        tc.start(name, t0, sources=sources, params={"level": 25} if name == "battery" else None)
        tc.needs_full_redraw = False
        shot = SHOT_AT.get(name, 0.5)
        tiles = []
        # step time forward so particle systems and physics have history
        for t in np.arange(0.0, shot, 1 / 15):
            tc.apply(t0 + float(t), l0, r0)
        sl, sr, _ = tc.apply(t0 + shot, l0, r0)
        for i, spec in enumerate((sl, sr)):
            if spec.scene is not None and not spec.over_eye:
                tiles.append(scenes.render(*spec.scene)[0].copy())
            elif spec.scene is not None:
                base, _ = renderers[i].render(spec.state, spec.overlays)
                tiles.append(scenes.render(*spec.scene, base=base)[0].copy())
            else:
                tiles.append(renderers[i].render(spec.state, spec.overlays)[0].copy())
        rows.append((name, tiles))
        tc.stop(t0 + shot)
        t0 += 1000.0

    import pygame

    pygame.init()
    font = pygame.font.SysFont("menlo,monaco,consolas,monospace", 14)
    gap, label_h, cols = 10, 22, 3
    nrows = (len(rows) + cols - 1) // cols
    tile_w = size * 2 + 4
    W = cols * (tile_w + gap) + gap
    H = nrows * (size + label_h + gap) + gap
    surf = pygame.Surface((W, H))
    surf.fill((50, 50, 50))
    for i, (label, (lf, rf)) in enumerate(rows):
        row, col = divmod(i, cols)
        x = gap + col * (tile_w + gap)
        y = gap + row * (size + label_h + gap)
        surf.blit(font.render(label, True, (240, 240, 240)), (x, y + 2))
        surf.blit(pygame.image.frombuffer(np.ascontiguousarray(lf).tobytes(), (size, size), "RGB"), (x, y + label_h))
        surf.blit(pygame.image.frombuffer(np.ascontiguousarray(rf).tobytes(), (size, size), "RGB"), (x + size + 4, y + label_h))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, out)
    print(f"saved {out} ({len(rows)} themes)")


if __name__ == "__main__":
    main(*sys.argv[1:])
