from microduck_eyes.display.desktop import ZOOMS, compute_layout, detect_pt_per_mm


def test_detect_density_is_sane():
    ppm, source = detect_pt_per_mm()
    assert 2.0 < ppm < 12.0 and source


def test_life_size_matches_physical_panel(cfg):
    ppm = 5.24
    L = compute_layout(cfg, ppm, 1.0, 45.0, 72)
    active_mm = cfg.panel.size / cfg.panel.px_per_mm              # ~32.4 mm
    assert abs(L.panel_px - active_mm * ppm) < 1.0                # 32.4 mm on screen
    assert abs(L.spacing_px - 45.0 * ppm) < 1.0
    assert L.px_per_screen_px < 1.0 and L.k == 1                  # a panel pixel is smaller than a point


def test_zoom_keeps_pixels_crisp(cfg):
    for z in ZOOMS[1:]:
        L = compute_layout(cfg, 5.24, z, 45.0, 72)
        assert L.k >= 2 and L.k * cfg.panel.size >= L.panel_px   # integer pre-scale then resample down
        assert abs(L.px_per_screen_px - 5.24 * z / cfg.panel.px_per_mm) < 0.01


def test_panels_do_not_overlap_and_fit(cfg):
    L = compute_layout(cfg, 5.24, 3.0, 45.0, 72)
    (lx, _), (rx, _) = L.centres
    assert rx - lx >= L.panel_px + 2 * L.bezel_px - 1 or L.spacing_px < L.panel_px   # 45 mm apart, 35.4 mm wide
    assert L.origins[0][0] >= 0 and L.origins[1][0] + L.panel_px <= L.width
