"""Every panel control is clicked once, every slider dragged, every tab shown. Nothing may raise."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from microduck_eyes.app import App, parse_args
from microduck_eyes.display.panel import Button, Panel, Slider


@pytest.fixture
def app():
    a = App(parse_args(["--udp-port", "0", "--no-idle", "--zoom", "1", "--seed", "0"]))
    yield a
    if a.camera is not None:
        a.camera.stop()
    a.display.close()


def test_every_control_works(app):
    pg = app.display.pg
    panel = app.panel
    clicked = dragged = 0
    for tab in range(len(panel.tab_defs)):
        panel.set_tab(tab)
        for w in list(panel.widgets):
            if isinstance(w, Button):
                if w.label in ("Quit", "Webcam", "Screenshot"):
                    continue
                w.on_click()
                clicked += 1
                if w.is_active is not None:
                    assert isinstance(bool(w.is_active()), bool)
            elif isinstance(w, Slider):
                w.set(w.lo)
                w.set(w.hi)
                w.set((w.lo + w.hi) / 2)
                assert w.lo <= w.get() <= w.hi
                dragged += 1
        # the panel must draw in this state
        app.panel.place(app.display.window.get_width() - Panel.WIDTH, 0, app.display.window.get_height())
        app.panel.draw(app.display.window, (0, 0))
    assert clicked > 120 and dragged >= 5
    app.theme.stop(0.0)
    assert app.running


def test_panel_event_routing(app):
    pg = app.display.pg
    panel = app.panel
    w, h = app.display.window.get_size()
    panel.place(w - Panel.WIDTH, 0, h)
    # click on the second tab header
    tw = Panel.WIDTH // len(panel.tab_defs)
    ev = pg.event.Event(pg.MOUSEBUTTONDOWN, pos=(w - Panel.WIDTH + tw + 5, 10), button=1)
    assert panel.handle(ev) and panel.tab == 1
    # a click in the eyes area is not consumed
    ev = pg.event.Event(pg.MOUSEBUTTONDOWN, pos=(50, 50), button=1)
    assert not panel.handle(ev)
    # clicking the first button of the Eyes tab sets that expression
    panel.set_tab(0)
    first = next(x for x in panel.widgets if isinstance(x, Button))
    ox, oy = panel._content_origin()
    ev = pg.event.Event(pg.MOUSEBUTTONDOWN, pos=(ox + first.x + 2, oy + first.y + 2), button=1)
    assert panel.handle(ev)
    assert app.anim.expression.name == first.label
    # wheel scrolls the themes tab
    panel.set_tab(1)
    pg.mouse.set_pos = lambda *a: None
    before = panel.scroll[1]
    ev = pg.event.Event(pg.MOUSEWHEEL, x=0, y=-3)
    panel.handle(ev)
    assert panel.scroll[1] >= before


def test_panel_toggle_changes_layout(app):
    w0 = app.display.window.get_width()
    app.toggle_panel()
    assert app.display.window.get_width() == w0 - Panel.WIDTH and not app.panel.visible
    app.toggle_panel()
    assert app.display.window.get_width() == w0 and app.panel.visible
