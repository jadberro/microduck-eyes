import os

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def test_brightness_and_dome(cfg):
    from microduck_eyes.display.desktop import DesktopDisplay
    d = DesktopDisplay(cfg, zoom=2.0, pt_per_mm=5.24)
    frame = np.full((240, 240, 3), 200, np.uint8)
    d.brightness = 0.5
    out = d._apply_brightness(frame)
    assert int(out[0, 0, 0]) in (100, 101)
    d.brightness = 1.0
    assert d._apply_brightness(frame) is frame
    d.dome = True
    d.show(0, frame, (0, 0, 240, 240))
    d.show(1, frame, (0, 0, 240, 240))
    d.flip()
    assert d._dome_maps is not None and d._dome_maps[0].shape == (d.lay.panel_px, d.lay.panel_px)
    d.close()
