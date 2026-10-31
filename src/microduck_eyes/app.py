"""Simulator entry point: event loop that sleeps whenever the eyes are still."""
from __future__ import annotations

import argparse
import sys
import time

from . import config as config_mod
from .control.keyboard import HELP
from .control.udp import UdpControl
from .display import effects
from .eye.animator import Animator
from .eye.expressions import ORDER
from .eye.renderer import EyeRenderer
from .eye.scenes import SceneRenderer
from .eye.themes import GAMES, GLANCES, SURPRISES, THEMES, ThemeController
from .display.panel import Button, Header, Panel, Slider
from .behaviour import Behaviour
from .sensors import SensorHub
from . import camera as camera_mod
from .patterns import PATTERN_ORDER, PATTERNS

FPS_CAPS = [60, 30, 20, 15, 10]
SIDES = ("left", "right")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="microduck-eyes", description="Cute duck eyes simulator")
    ap.add_argument("--display", choices=["desktop", "gc9a01"], default="desktop")
    ap.add_argument("--config", help="path to eyes.toml (default: config/eyes.toml)")
    ap.add_argument("--zoom", type=float, default=1.0, help="multiple of life size (1 2 3 4 6)")
    ap.add_argument("--view", choices=["screens", "face"], default="screens", help="only the panels, or set into a face")
    ap.add_argument("--pt-per-mm", type=float, help="override the detected display density (window points per mm)")
    ap.add_argument("--spacing", type=float, help="eye spacing in mm (overrides config)")
    ap.add_argument("--udp-port", type=int, default=5005, help="0 disables the UDP listener")
    ap.add_argument("--expression", default="neutral", choices=ORDER)
    ap.add_argument("--no-idle", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--camera", action="store_true", help="start with the webcam as the face/motion source (needs the camera extra)")
    ap.add_argument("--no-behaviour", action="store_true", help="disable the behaviour engine (attention, light, speech cues...)")
    ap.add_argument("--no-panel", action="store_true", help="start without the control panel (` toggles it)")
    ap.add_argument("--theme", help="start with a theme active, e.g. hal (see README for the list)")
    ap.add_argument("--surprise", type=float, metavar="SECONDS", help="fire a random theme roughly every N seconds while idle")
    ap.add_argument("--frames", type=int, default=0, help="exit after N rendered frames (testing)")
    ap.add_argument("--screenshot", help="save a screenshot to this path before exiting (testing)")
    return ap.parse_args(argv)


class App:
    def __init__(self, args):
        self.args = args
        self.cfg = config_mod.load(args.config)
        if args.spacing:
            self.cfg.layout.eye_spacing_mm = args.spacing
        if args.display != "desktop":
            sys.exit("the gc9a01 backend is Phase 6; only --display desktop works today")
        from .display.desktop import DesktopDisplay

        self.display = DesktopDisplay(self.cfg, zoom=args.zoom, view=args.view, pt_per_mm=args.pt_per_mm)
        self.renderers = [EyeRenderer(self.cfg, s) for s in SIDES]
        self.scenes = SceneRenderer(self.cfg)
        now = time.perf_counter()
        self.anim = Animator(self.cfg, now, seed=args.seed)
        self.anim.set_expression(args.expression, now, dur_ms=0)
        self.hub = SensorHub(low_battery=self.cfg.behaviour.low_battery)
        self.behaviour = Behaviour(self.cfg, self.anim, self.hub, now, seed=args.seed)
        if args.no_behaviour:
            self.behaviour.enabled = False
        self.camera = None
        self._camera_error_shown = False
        if args.camera or self.cfg.camera.enabled:
            self.toggle_camera(now)
        self.theme = ThemeController(self.cfg, seed=args.seed, anim=self.anim, scenes=self.scenes, hub=self.hub)
        if args.surprise:
            self.theme.set_surprise(True, now, args.surprise)
        if args.theme:
            self._start_theme(args.theme, now)
        if args.no_idle:
            self.anim.set_idle(False, now)
        self.udp = UdpControl(self.on_command, port=args.udp_port) if args.udp_port else None
        self.running = True
        self.quantize = False
        self.fps_i = 0
        self.rotate = [False, False]
        self.mirror = False
        self.hud = True
        self.pattern_i = -1
        self.frames = 0
        self.render_ms = 0.0
        self.fps = 0.0
        self._fps_win = (now, 0)
        self._force = True
        self.last_mouse = -1e9
        self.hour_cycle = [None, 7.5, 14.0, 21.0, 1.0]
        self.hour_i = 0
        self.brightness_override = None
        self._last_frame_key = None
        self.head_pulse_until = 0.0
        self.panel = Panel(self.display.pg, self.display.font, self._panel_tabs())
        self.panel.visible = not args.no_panel
        self.display.set_panel_width(Panel.WIDTH if self.panel.visible else 0)

    # ---- commands -----------------------------------------------------
    def _start_theme(self, name: str, now: float, hold=None, params=None):
        sources = [r.frame.copy() for r in self.renderers]
        self.theme.start(name, now, hold_s=hold, params=params, sources=sources)
        self.pattern_i = -1

    def toggle_camera(self, now: float):
        if self.camera is not None:
            self.camera.stop()
            self.camera = None
            self.hub.face_lost(now)
            print("camera off")
            return
        if not camera_mod.available():
            print("camera: OpenCV not installed. Run: uv sync --extra desktop --extra camera")
            return
        self.camera = camera_mod.CameraSource(self.cfg.camera)
        self._camera_error_shown = False
        self.camera.start()
        print("camera on")

    # ---- control panel ---------------------------------------------------
    def set_expression(self, name: str):
        now = time.perf_counter()
        self.anim.set_expression(name, now)
        self.behaviour.set_expression_name(name, now)
        self.pattern_i = -1
        self._force = True

    def start_theme(self, name: str, params=None):
        self._start_theme(name, time.perf_counter(), None, params)
        self._force = True

    def sense(self, **fields):
        self.hub.set(time.perf_counter(), **fields)
        self._force = True

    def pulse_head(self, axis: str, sign: float):
        now = time.perf_counter()
        self.hub.set(now, **{axis: 90.0 * sign})
        self.head_pulse_until = now + 0.35

    def toggle_panel(self):
        self.panel.visible = not self.panel.visible
        self.display.set_panel_width(Panel.WIDTH if self.panel.visible else 0)
        self._force = True

    def _panel_tabs(self):
        app = self
        now = time.perf_counter

        def eyes():
            w = [Header(text="Expression")]
            w += [Button(label=n, on_click=lambda n=n: app.set_expression(n), is_active=lambda n=n: app.anim.expression.name == n) for n in ORDER]
            w += [Header(text="Actions"),
                  Button(label="Blink", on_click=lambda: app.anim.blink(now())),
                  Button(label="Wink L", on_click=lambda: app.anim.blink(now(), "left")),
                  Button(label="Wink R", on_click=lambda: app.anim.blink(now(), "right")),
                  Button(label="Yawn", on_click=lambda: app.start_theme("yawn")),
                  Button(label="Idle wander", on_click=lambda: app.anim.set_idle(not app.anim.idle, now()), is_active=lambda: app.anim.idle),
                  Button(label="Alive engine", on_click=lambda: setattr(app.behaviour, "enabled", not app.behaviour.enabled), is_active=lambda: app.behaviour.enabled),
                  Header(text="Sounds"),
                  Button(label="Loud noise", on_click=lambda: app.behaviour.sound("loud", now())),
                  Button(label="Chirp", on_click=lambda: app.behaviour.sound("chirp", now())),
                  Button(label="Sigh", on_click=lambda: app.behaviour.sound("sigh", now())),
                  Header(text="Speak")]
            for text in ("Hello there! I am Microduck.", "Do you have any BREAD?", "Quack quack QUACK!", "I am thinking about it..."):
                w.append(Button(label=text, on_click=lambda t=text: app.behaviour.speak(t, now())))
            w += [Header(text="Mood"),
                  Button(label="Pet (toggle)", on_click=lambda: app.sense(touch=not app.hub.state.touch), is_active=lambda: app.hub.state.touch),
                  Button(label="Iris flash", on_click=lambda: app.start_theme("flash", {"colour": [90, 200, 255]})),
                  Button(label="Flash red", on_click=lambda: app.start_theme("flash", {"colour": [255, 60, 60]})),
                  Button(label="Flash green", on_click=lambda: app.start_theme("flash", {"colour": [60, 230, 90]}))]
            return w

        def themes():
            w = [Header(text="Gag themes (click again to stop)"),
                 Button(label="Theme off", on_click=lambda: app.theme.stop(now()), is_active=lambda: app.theme.active is None),
                 Button(label="Surprise me", on_click=lambda: app.theme.set_surprise(not app.theme.surprise, now(), 20.0), is_active=lambda: app.theme.surprise)]
            for n in SURPRISES:
                w.append(Button(label=n, on_click=lambda n=n: app.theme.stop(now()) if app.theme.active == n else app.start_theme(n),
                                is_active=lambda n=n: app.theme.active == n))
            w += [Header(text="Long running")]
            for n in ("filibuster", "boot"):
                w.append(Button(label=n, on_click=lambda n=n: app.theme.stop(now()) if app.theme.active == n else app.start_theme(n),
                                is_active=lambda n=n: app.theme.active == n))
            return w

        def games():
            w = [Header(text="Interaction games (mouse = your face, left click = your blink)")]
            for n in GAMES:
                w.append(Button(label=n, on_click=lambda n=n: app.theme.stop(now()) if app.theme.active == n else app.start_theme(n),
                                is_active=lambda n=n: app.theme.active == n))
            w += [Button(label="Stop game", on_click=lambda: app.theme.stop(now())),
                  Header(text="Status glances")]
            for n in GLANCES:
                params = {"level": app.hub.state.battery} if n == "battery" else None
                w.append(Button(label=n, on_click=lambda n=n, p=params: app.start_theme(n, {"level": app.hub.state.battery} if n == "battery" else None),
                                is_active=lambda n=n: app.theme.active == n))
            w += [Header(text="Weather glance")]
            for k in ("sun", "cloud", "rain", "snow", "storm"):
                w.append(Button(label=k, on_click=lambda k=k: (app.sense(weather=k), app.start_theme("weather", {"kind": k}))))
            w += [Header(text="Compass glance")]
            for h in (0, 90, 180, 270):
                w.append(Button(label=f"{h} deg", on_click=lambda h=h: (app.sense(heading=float(h)), app.start_theme("compass", {"heading": h}))))
            return w

        def senses():
            st = lambda: app.hub.state
            w = [Header(text="Environment"),
                 Slider(label="Light", get=lambda: st().light, set=lambda v: app.sense(light=v), lo=0, hi=1, step=0.05),
                 Slider(label="Sound level", get=lambda: st().sound, set=lambda v: app.sense(sound=v), lo=0, hi=1, step=0.05),
                 Header(text="Time of day")]
            for label, hour in (("Clock", None), ("Morning", 7.5), ("Day", 14.0), ("Evening", 21.0), ("Night", 1.0)):
                w.append(Button(label=label, on_click=lambda h=hour: app.sense(hour=h), is_active=lambda h=hour: st().hour == h))
            w += [Header(text="Head (IMU)"),
                  Button(label="Turn left", on_click=lambda: app.pulse_head("head_yaw_rate", -1)),
                  Button(label="Turn right", on_click=lambda: app.pulse_head("head_yaw_rate", 1)),
                  Button(label="Nod down", on_click=lambda: app.pulse_head("head_pitch_rate", 1)),
                  Button(label="Nod up", on_click=lambda: app.pulse_head("head_pitch_rate", -1)),
                  Header(text="Robot state"),
                  Slider(label="Battery %", get=lambda: st().battery, set=lambda v: app.sense(battery=v), lo=0, hi=100, step=1, fmt="{:.0f}"),
                  Button(label="Charging", on_click=lambda: app.sense(charging=not st().charging), is_active=lambda: st().charging)]
            for bars in range(4):
                w.append(Button(label=f"Wifi {bars}", on_click=lambda b=bars: app.sense(wifi=b), is_active=lambda b=bars: st().wifi == b))
            w += [Button(label="Listening", on_click=lambda: app.sense(listening=not st().listening), is_active=lambda: st().listening),
                  Button(label="Thinking", on_click=lambda: app.sense(thinking=not st().thinking), is_active=lambda: st().thinking),
                  Header(text="Camera"),
                  Button(label="Webcam", on_click=lambda: app.toggle_camera(now()), is_active=lambda: app.camera is not None),
                  Button(label="Cover camera", on_click=lambda: app.sense(camera_covered=not st().camera_covered), is_active=lambda: st().camera_covered),
                  Button(label="Face lost", on_click=lambda: app.hub.face_lost(now())),
                  Button(label="Face left", on_click=lambda: app.hub.face(now(), -150.0, 0.0, 300.0)),
                  Button(label="Face right", on_click=lambda: app.hub.face(now(), 150.0, 0.0, 300.0)),
                  Button(label="Face close", on_click=lambda: app.hub.face(now(), 0.0, 0.0, 90.0))]
            return w

        def view():
            d = app.display
            w = [Header(text="View")]
            for v in ("screens", "face"):
                w.append(Button(label=v, on_click=lambda v=v: d.set_view(v), is_active=lambda v=v: d.view == v))
            w += [Header(text="Zoom (x life size)")]
            for z in (1.0, 2.0, 3.0, 4.0, 6.0):
                w.append(Button(label=f"{z:g}x", on_click=lambda z=z: d.set_zoom(z), is_active=lambda z=z: abs(d.zoom - z) < 0.01))
            w += [Button(label="Pixel gaps", on_click=lambda: setattr(d, "pixel_gaps", not d.pixel_gaps), is_active=lambda: d.pixel_gaps),
                  Button(label="Dome lens", on_click=lambda: setattr(d, "dome", not d.dome), is_active=lambda: d.dome),
                  Button(label="RGB565", on_click=lambda: setattr(app, "quantize", not app.quantize), is_active=lambda: app.quantize),
                  Button(label="Dirty rects", on_click=lambda: setattr(d, "show_dirty", not d.show_dirty), is_active=lambda: d.show_dirty),
                  Button(label="HUD", on_click=lambda: setattr(app, "hud", not app.hud), is_active=lambda: app.hud),
                  Header(text="Frame-rate cap")]
            for i, f in enumerate(FPS_CAPS):
                w.append(Button(label=f"{f} fps", on_click=lambda i=i: setattr(app, "fps_i", i), is_active=lambda i=i: app.fps_i == i))
            w += [Header(text="Panel orientation"),
                  Button(label="Rotate left", on_click=lambda: app.rotate.__setitem__(0, not app.rotate[0]), is_active=lambda: app.rotate[0]),
                  Button(label="Rotate right", on_click=lambda: app.rotate.__setitem__(1, not app.rotate[1]), is_active=lambda: app.rotate[1]),
                  Button(label="Mirror", on_click=lambda: setattr(app, "mirror", not app.mirror), is_active=lambda: app.mirror),
                  Header(text="Test patterns")]
            for i, n in enumerate(PATTERN_ORDER):
                w.append(Button(label=n, on_click=lambda i=i: setattr(app, "pattern_i", -1 if app.pattern_i == i else i), is_active=lambda i=i: app.pattern_i == i))
            w += [Header(text="Geometry and backlight"),
                  Slider(label="Spacing mm", get=lambda: d.spacing_mm, set=lambda v: (d.set_spacing(v), setattr(app.cfg.layout, "eye_spacing_mm", d.spacing_mm)),
                         lo=35, hi=120, step=1, fmt="{:.0f}"),
                  Slider(label="Brightness", get=lambda: d.brightness, set=lambda v: setattr(app, "brightness_override", v), lo=0.05, hi=1, step=0.05),
                  Button(label="Brightness auto", on_click=lambda: setattr(app, "brightness_override", None), is_active=lambda: app.brightness_override is None),
                  Header(text="Output"),
                  Button(label="Screenshot", on_click=lambda: print("saved", d.screenshot())),
                  Button(label="Hide panel (`)", on_click=app.toggle_panel),
                  Button(label="Quit", on_click=lambda: setattr(app, "running", False))]
            return w

        return [("Eyes", eyes), ("Themes", themes), ("Games", games), ("Senses", senses), ("View", view)]

    def _camera_status(self) -> str:
        if self.camera is None:
            return "off"
        if self.camera.error:
            return "ERROR (see console)"
        return f"on {self.camera.frames}f/{self.camera.faces}faces"

    def on_command(self, msg: dict):
        now = time.perf_counter()
        cmd = msg.get("cmd")
        if cmd == "look":
            self.anim.look_at(float(msg.get("x", 0)), float(msg.get("y", 0)), now,
                              z_mm=msg.get("z"), dur_ms=msg.get("ms"), hold_s=float(msg.get("hold", 2.0)))
        elif cmd == "express":
            self.anim.set_expression(str(msg.get("name", "neutral")), now, dur_ms=msg.get("ms"))
            self.behaviour.set_expression_name(str(msg.get("name", "neutral")), now)
            self.pattern_i = -1
        elif cmd == "blink":
            self.anim.blink(now)
        elif cmd == "idle":
            self.anim.set_idle(bool(msg.get("on", True)), now)
        elif cmd == "theme":
            hold = msg.get("hold")
            params = {k: v for k, v in msg.items() if k not in ("cmd", "name", "hold")}
            self._start_theme(str(msg.get("name", "off")), now, None if hold is None else float(hold), params)
        elif cmd == "surprise":
            self.theme.set_surprise(bool(msg.get("on", True)), now, msg.get("every"))
        elif cmd == "sense":
            fields = {k: v for k, v in msg.items() if k != "cmd"}
            face = fields.pop("face", "keep")
            if face is None:
                self.hub.face_lost(now)
            elif face != "keep":
                self.hub.face(now, *[float(v) for v in face][:3])
            if fields:
                self.hub.set(now, **fields)
        elif cmd == "sound":
            self.behaviour.sound(str(msg.get("kind", "loud")), now, float(msg.get("level", 1.0)))
        elif cmd == "speak":
            self.behaviour.speak(str(msg.get("text", "")), now, think=bool(msg.get("think", True)))
        elif cmd == "glance":
            params = {k: v for k, v in msg.items() if k not in ("cmd", "what", "hold")}
            self._start_theme(str(msg.get("what", "clock")), now, msg.get("hold"), params)
        elif cmd == "game":
            self._start_theme(str(msg.get("name", "off")), now)
        elif cmd == "flash":
            self._start_theme("flash", now, None, {"colour": msg.get("colour", [90, 200, 255])})
        elif cmd == "brightness":
            v = msg.get("value")
            self.brightness_override = None if v is None else float(v)
        elif cmd == "pet":
            self.hub.set(now, touch=bool(msg.get("on", True)))
        elif cmd == "behaviour":
            self.behaviour.enabled = bool(msg.get("on", True))
        elif cmd == "camera":
            if bool(msg.get("on", True)) != (self.camera is not None):
                self.toggle_camera(now)
        elif cmd == "quit":
            self.running = False
        self._force = True

    def on_key(self, key, mods, now: float):
        pg = self.display.pg
        shift = mods & pg.KMOD_SHIFT
        if key == pg.K_ESCAPE:
            self.running = False
        elif pg.K_0 <= key <= pg.K_9:
            idx = (key - pg.K_0 - 1) % 10
            self.anim.set_expression(ORDER[idx], now)
            self.behaviour.set_expression_name(ORDER[idx], now)
            self.pattern_i = -1
        elif key == pg.K_e:
            name = self.anim.cycle_expression(now, -1 if shift else 1)
            self.behaviour.set_expression_name(name, now)
            self.pattern_i = -1
        elif key == pg.K_SPACE:
            self.anim.set_expression("neutral", now)
            self.behaviour.set_expression_name("neutral", now)
            self.pattern_i = -1
        elif key == pg.K_b:
            self.anim.blink(now)
        elif key == pg.K_i:
            self.anim.set_idle(not self.anim.idle, now)
        elif key == pg.K_t:
            names = THEMES + ["off"]
            cur = self.theme.active if self.theme.active in names else "off"
            self._start_theme(names[(names.index(cur) + (-1 if shift else 1)) % len(names)], now)
        elif key == pg.K_BACKSPACE:
            self.theme.stop(now)
        elif key == pg.K_u:
            self.theme.set_surprise(not self.theme.surprise, now, 20.0)
        elif key == pg.K_TAB:
            names = GAMES + ["off"]
            cur = self.theme.active if self.theme.active in names else "off"
            self._start_theme(names[(names.index(cur) + 1) % len(names)], now)
        elif key == pg.K_SLASH:
            names = GLANCES + ["off"]
            cur = self.theme.active if self.theme.active in names else "off"
            nxt = names[(names.index(cur) + 1) % len(names)]
            self._start_theme(nxt, now, None, {"level": self.hub.state.battery} if nxt == "battery" else None)
        elif key == pg.K_a:
            self.behaviour.enabled = not self.behaviour.enabled
            if not self.behaviour.enabled:
                self.anim.set_idle(True, now)
        elif key == pg.K_k:
            self.hub.set(now, light=min(1.0, max(0.0, self.hub.state.light + (0.15 if shift else -0.15))))
        elif key == pg.K_n:
            self.behaviour.sound("chirp" if shift else "loud", now)
        elif key == pg.K_COMMA:
            self.behaviour.sound("sigh", now)
        elif key == pg.K_c:
            self.hub.set(now, camera_covered=not self.hub.state.camera_covered)
        elif key == pg.K_w:
            self.hour_i = (self.hour_i + 1) % len(self.hour_cycle)
            self.hub.set(now, hour=self.hour_cycle[self.hour_i])
        elif key == pg.K_o:
            self.display.dome = not self.display.dome
        elif key == pg.K_y:
            self.behaviour.speak("Hello there! I am Microduck. Do you have any BREAD?", now)
        elif key == pg.K_z:
            self._start_theme("yawn", now)
        elif key == pg.K_j:
            self.toggle_camera(now)
        elif key == pg.K_x:
            self.hub.set(now, touch=True)
        elif key in (pg.K_LEFT, pg.K_RIGHT):
            self.hub.set(now, head_yaw_rate=(90.0 if key == pg.K_RIGHT else -90.0))
        elif key in (pg.K_UP, pg.K_DOWN):
            self.hub.set(now, head_pitch_rate=(90.0 if key == pg.K_DOWN else -90.0))
        elif key == pg.K_BACKQUOTE:
            self.toggle_panel()
        elif key == pg.K_p:
            self.pattern_i = (self.pattern_i + 1) % len(PATTERN_ORDER)
        elif key == pg.K_q:
            self.quantize = not self.quantize
        elif key == pg.K_f:
            self.fps_i = (self.fps_i + 1) % len(FPS_CAPS)
        elif key == pg.K_r:
            self.rotate[1] = not self.rotate[1]
        elif key == pg.K_l:
            self.rotate[0] = not self.rotate[0]
        elif key == pg.K_m:
            self.mirror = not self.mirror
        elif key == pg.K_d:
            self.display.show_dirty = not self.display.show_dirty
        elif key == pg.K_h:
            self.hud = not self.hud
        elif key in (pg.K_PLUS, pg.K_EQUALS, pg.K_KP_PLUS):
            self.display.step_zoom(+1)
        elif key in (pg.K_MINUS, pg.K_KP_MINUS):
            self.display.step_zoom(-1)
        elif key == pg.K_v:
            self.display.set_view("face" if self.display.view == "screens" else "screens")
        elif key == pg.K_g:
            self.display.pixel_gaps = not self.display.pixel_gaps
        elif key == pg.K_LEFTBRACKET:
            self.display.set_spacing(self.display.spacing_mm - 1)
            self.cfg.layout.eye_spacing_mm = self.display.spacing_mm
        elif key == pg.K_RIGHTBRACKET:
            self.display.set_spacing(self.display.spacing_mm + 1)
            self.cfg.layout.eye_spacing_mm = self.display.spacing_mm
        elif key == pg.K_s:
            path = self.display.screenshot()
            print(f"saved {path}")
        else:
            return
        self._force = True

    def handle_events(self, timeout_ms: int):
        pg = self.display.pg
        events = []
        ev = pg.event.wait(timeout_ms) if timeout_ms > 0 else None
        if ev is not None and ev.type != pg.NOEVENT:
            events.append(ev)
        events.extend(pg.event.get())
        now = time.perf_counter()
        for ev in events:
            if ev.type in (pg.MOUSEMOTION, pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP, pg.MOUSEWHEEL) and self.panel.handle(ev):
                self._force = True
                continue
            if ev.type == pg.QUIT:
                self.running = False
            elif ev.type == pg.KEYDOWN:
                self.theme.on_input(now)
                self.on_key(ev.key, ev.mod, now)
            elif ev.type == pg.KEYUP:
                if ev.key in (pg.K_LEFT, pg.K_RIGHT):
                    self.hub.set(now, head_yaw_rate=0.0)
                elif ev.key in (pg.K_UP, pg.K_DOWN):
                    self.hub.set(now, head_pitch_rate=0.0)
                elif ev.key == pg.K_x:
                    self.hub.set(now, touch=False)
            elif ev.type == pg.MOUSEMOTION:
                self.theme.on_input(now)
                x, y = self.display.window_to_mm(ev.pos)
                if self.behaviour.enabled and self.camera is None:
                    # The mouse stands in for a face seen by the camera, plus peripheral motion.
                    self.hub.face(now, x, y, self.cfg.layout.gaze_depth_mm)
                    mag = min(1.0, (abs(ev.rel[0]) + abs(ev.rel[1])) / 60.0)
                    if mag > 0.15:
                        self.hub.event("motion", now, dx=x / 250.0, dy=y / 150.0, magnitude=mag)
                else:
                    self.anim.look_at(x, y, now, hold_s=self.cfg.animation.mouse_idle_after_s)
                self.theme.impulse(ev.rel[0] * 6.0, ev.rel[1] * 6.0)
                self.last_mouse = now
            elif ev.type == pg.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    self.hub.event("user_blink", now)
                elif ev.button == 3:
                    self.hub.set(now, camera_covered=not self.hub.state.camera_covered)
            elif ev.type == pg.WINDOWLEAVE:
                self.hub.face_lost(now)

    # ---- frame --------------------------------------------------------
    def draw(self, specs, now: float):
        t0 = time.perf_counter()
        if self.panel.visible:
            w, h = self.display.window.get_size()
            self.panel.place(w - Panel.WIDTH, 0, h)
        size = self.cfg.panel.size
        for i, (side, spec) in enumerate(zip(SIDES, specs)):
            if self.pattern_i >= 0:
                frame = PATTERNS[PATTERN_ORDER[self.pattern_i]](size, side)
                dirty = (0, 0, size, size)
            elif spec.scene is not None and not spec.over_eye:
                frame, dirty = self.scenes.render(*spec.scene)
            elif spec.scene is not None:
                base, _ = self.renderers[i].render(spec.state, spec.overlays)
                frame, dirty = self.scenes.render(*spec.scene, base=base)
            else:
                frame, dirty = self.renderers[i].render(spec.state, spec.overlays)
            if self._force:
                dirty = (0, 0, size, size)
            if self.quantize:
                frame = effects.rgb565_quantize(frame)
            if self.rotate[i] or self.mirror:
                frame = effects.orient(frame, self.rotate[i], self.mirror)
                dirty = effects.orient_rect(dirty, size, self.rotate[i], self.mirror)
            self.display.show(i, frame, dirty)
        self.render_ms = (time.perf_counter() - t0) * 1000.0
        self.frames += 1
        t_win, n_win = self._fps_win
        n_win += 1
        if now - t_win >= 1.0:
            self.fps = n_win / (now - t_win)
            self._fps_win = (now, 0)
        else:
            self._fps_win = (t_win, n_win)
        if self.hud:
            mode = PATTERN_ORDER[self.pattern_i] if self.pattern_i >= 0 else self.anim.expression.name
            if self.theme.active:
                mode = f"{mode}+{self.theme.active}"
            if self.theme.surprise:
                mode += " (surprise)"
            st = self.hub.state
            alive = (f"alive:{'on' if self.behaviour.enabled else 'off'}  attention:{self.behaviour.attention}  "
                     f"face:{'yes' if st.face else 'no'}  light:{st.light:.2f}  mood:{self.behaviour.mood:.2f}  "
                     f"phase:{self.behaviour.phase}  bright:{self.display.brightness:.2f}  "
                     f"camera:{self._camera_status()}  cover:{int(st.camera_covered)}  dome:{int(self.display.dome)}")
            self.display.set_hud([
                f"{mode:<11} idle:{'on ' if self.anim.idle else 'off'}  cap:{FPS_CAPS[self.fps_i]:>2}fps  "
                f"rgb565:{'on ' if self.quantize else 'off'}  rot L/R:{int(self.rotate[0])}/{int(self.rotate[1])}  mirror:{int(self.mirror)}",
                f"{self.display.scale_text()}  gaps:{'on' if self.display.pixel_gaps else 'off'}  view:{self.display.view}  spacing:{self.display.spacing_mm:.0f}mm",
                alive,
                f"render:{self.render_ms:5.2f}ms  fps:{self.fps:4.1f}  frames:{self.frames}   "
                "1-0 expr  E cycle  T theme  Tab game  / glance  A alive  K light  N noise  arrows head  X pet  C cover  W time  O dome  Y speak  Z yawn  J camera  V view  +/- zoom  G gaps  S shot  Esc",
            ])
        else:
            self.display.set_hud([])
        self.display.flip(draw_extra=lambda surf: self.panel.draw(surf, self.display.pg.mouse.get_pos()))
        self._force = False

    def run(self):
        print(HELP)
        timeout_ms = 0
        next_frame_at = 0.0
        while self.running:
            self.handle_events(timeout_ms)
            if self.udp:
                self.udp.poll()
            now = time.perf_counter()
            if self.args.frames and self.frames >= self.args.frames:
                break
            self.hub.integrate(now)
            if self.head_pulse_until and now >= self.head_pulse_until:
                self.head_pulse_until = 0.0
                self.hub.set(now, head_yaw_rate=0.0, head_pitch_rate=0.0)
            if self.camera is not None:
                self.camera.poll(self.hub, now)
                if self.camera.error and not self._camera_error_shown:
                    self._camera_error_shown = True
                    print(f"camera: {self.camera.error}")
            self.behaviour.update(now)
            while (req := self.behaviour.pop_request()) is not None:
                if req.theme == "off":
                    if self.theme.active in ("listening", "thinking"):
                        self.theme.stop(now)
                elif self.theme.active is None or self.theme.active in ("listening", "thinking"):
                    self._start_theme(req.theme, now, req.hold, req.params)
            left, right, changed = self.anim.update(now)
            left, right, ov_l, ov_r = self.behaviour.modify(now, left, right)
            spec_l, spec_r, tchanged = self.theme.apply(now, left, right)
            for spec, ov in ((spec_l, ov_l), (spec_r, ov_r)):
                if spec.scene is None and ov:
                    spec.overlays = ov + spec.overlays
            self.display.brightness = self.brightness_override if self.brightness_override is not None else self.behaviour.brightness
            frame_key = (spec_l.state, spec_r.state, spec_l.scene, spec_r.scene, ThemeController._ov_key(spec_l.overlays),
                         ThemeController._ov_key(spec_r.overlays), self.display.brightness)
            if frame_key != self._last_frame_key:
                changed = True
                self._last_frame_key = frame_key
            if self.theme.needs_full_redraw:
                self._force = True
                self.theme.needs_full_redraw = False
            if (changed or tchanged or self._force) and now >= next_frame_at:
                self.draw((spec_l, spec_r), now)
                next_frame_at = now + 1.0 / FPS_CAPS[self.fps_i]
            # Decide how long to sleep: tick while animating, otherwise wait for the next event.
            now = time.perf_counter()
            if self.anim.animating(now) or self.theme.animating(now) or self.behaviour.animating(now) or self._force or self.camera is not None:
                wait = max(next_frame_at - now, 0.0) if self.camera is None else min(max(next_frame_at - now, 0.0), 0.1)
            else:
                wake = min(self.anim.next_wake(now), self.theme.next_wake(now), self.behaviour.next_wake(now))
                wait = min(max(wake - now, 0.0), 0.25)
            timeout_ms = max(int(wait * 1000), 1)
        if self.args.screenshot:
            self.display.pg.image.save(self.display.window, self.args.screenshot)
        if self.udp:
            self.udp.close()
        if self.camera is not None:
            self.camera.stop()
        self.display.close()


def main(argv=None):
    app = App(parse_args(argv))
    app.run()


if __name__ == "__main__":
    main()
