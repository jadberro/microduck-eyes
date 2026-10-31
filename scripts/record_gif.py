"""Record an animated GIF of the eyes (screens view, both panels) without opening a window.

Usage: uv run python scripts/record_gif.py [out.gif] [seconds] [fps]
Runs the animator and behaviour engine headless through a short scripted sequence.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from microduck_eyes import config as config_mod  # noqa: E402
from microduck_eyes.eye import sprites  # noqa: E402
from microduck_eyes.eye.animator import Animator  # noqa: E402
from microduck_eyes.eye.renderer import EyeRenderer  # noqa: E402
from microduck_eyes.eye.scenes import SceneRenderer  # noqa: E402
from microduck_eyes.eye.themes import ThemeController  # noqa: E402

BENCH = (30, 30, 33)

# (time, action) scripted sequence; actions are callables on (anim, tc, t)
SCRIPT = [
    (0.6, lambda a, tc, t: a.look_at(150, 0, t, dur_ms=200, hold_s=3)),
    (1.6, lambda a, tc, t: a.look_at(-140, 30, t, dur_ms=200, hold_s=3)),
    (2.4, lambda a, tc, t: a.blink(t)),
    (3.0, lambda a, tc, t: a.look_at(0, 0, t, dur_ms=250, hold_s=3)),
    (3.6, lambda a, tc, t: a.set_expression("happy", t)),
    (5.2, lambda a, tc, t: a.set_expression("surprised", t)),
    (6.4, lambda a, tc, t: a.set_expression("sad", t)),
    (7.8, lambda a, tc, t: a.set_expression("love", t)),
    (9.0, lambda a, tc, t: a.set_expression("neutral", t)),
    (9.4, lambda a, tc, t: tc.start("hearts", t, hold_s=2.5)),
    (12.2, lambda a, tc, t: tc.start("dollar", t, hold_s=2.5)),
    (15.0, lambda a, tc, t: tc.start("spiral", t, hold_s=2.2)),
    (17.4, lambda a, tc, t: a.set_expression("sleepy", t)),
    (18.8, lambda a, tc, t: a.set_expression("asleep", t)),
]


def main(out: str = "docs/images/eyes.gif", seconds: float = 20.0, fps: int = 15):
    cfg = config_mod.load()
    size = cfg.panel.size
    renderers = [EyeRenderer(cfg, "left"), EyeRenderer(cfg, "right")]
    scenes = SceneRenderer(cfg)
    anim = Animator(cfg, 0.0, seed=4)
    tc = ThemeController(cfg, seed=4, anim=anim, scenes=scenes)
    mask = sprites.disc(size / 2 - 0.5)[1:-1, 1:-1][..., None]        # round panel mask
    mask = mask[:size, :size]
    gap = 28
    W, H = size * 2 + gap * 3, size + gap * 2
    frames = []
    script = list(SCRIPT)
    dt = 1.0 / fps
    for i in range(int(seconds * fps)):
        t = i * dt
        while script and t >= script[0][0]:
            script.pop(0)[1](anim, tc, t)
        l, r, _ = anim.update(t)
        sl, sr, _ = tc.apply(t, l, r)
        canvas = np.empty((H, W, 3), np.uint8)
        canvas[...] = BENCH
        for k, spec in enumerate((sl, sr)):
            if spec.scene is not None:
                frame = scenes.render(*spec.scene)[0]
            else:
                frame = renderers[k].render(spec.state, spec.overlays)[0]
            masked = (frame.astype(np.float32) * mask + np.array(BENCH, np.float32) * (1 - mask)).astype(np.uint8)
            x = gap + k * (size + gap)
            canvas[gap:gap + size, x:x + size] = masked
        frames.append(Image.fromarray(canvas).quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
    print(f"saved {out}: {len(frames)} frames, {Path(out).stat().st_size // 1024} KB")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(*(args[:1] + [float(args[1])] * (len(args) > 1) + [int(args[2])] * (len(args) > 2)))
