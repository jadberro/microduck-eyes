# Microduck Eyes

Cute cartoon duck eyes for two 1.28" round GC9A01 panels, with a desktop simulator
that shows both eyes at true relative scale. The eye code is written to run unchanged
on the Radxa Zero later; only the display backend swaps.

Plan and design notes: [plans/001-eye-simulator-plan.md](plans/001-eye-simulator-plan.md).

## Run the simulator

```sh
uv sync --extra desktop
uv run microduck-eyes            # or: uv run python -m microduck_eyes
```

By default the window shows only what the two screens show, at life size: the round active
areas and the module's thin black border on a dark bench, nothing else. The size comes from the
display's points-per-millimetre (read from CoreGraphics on macOS; `--pt-per-mm` overrides it),
so a ruler held against the screen should measure about 32 mm across each eye.

Useful flags: `--zoom 3` (multiple of life size: 1, 2, 3, 4 or 6), `--view face` (panels set
into a face-coloured head, for judging the mockup), `--spacing 50` (eye spacing in mm),
`--expression happy`, `--no-idle`, `--udp-port 0` (disable the command listener),
`--config path/to/eyes.toml`.

About pixel density: a GC9A01 pixel is 0.135 mm. On most laptops a window point is 0.19 mm or
more, so at 1x the simulator area-averages each frame down and the panel looks as smooth as the
real thing does at arm's length. From 2x up each panel pixel covers more than one window point
and the true pixel grid shows; `G` adds the dark inter-pixel gaps of a real LCD from 3x.

### Control panel

The window opens with a control panel on the right: five tabs (Eyes, Themes, Games, Senses, View)
with a button, toggle or slider for every option in this README. Highlighted buttons show the
current state, so you can see which expression, theme, zoom or sensor value is active. Scroll with
the mouse wheel on long tabs. The backquote key hides and shows it, and `--no-panel` starts without it.
Mouse movement over the panel is not treated as your face.

### Alive mode

The behaviour engine runs by default and makes the eyes react to the world through a sensor hub.
In the simulator the mouse stands in for the camera (your face is where the pointer is, quick moves
are peripheral motion, left click means you blinked, right click covers the camera), and a few keys
stand in for other sensors. On the robot the same hub is fed by real sensors or by `sense` messages.

| Behaviour | What happens | Simulate with |
|---|---|---|
| Eye contact | A face becomes the gaze target with convergence; the duck breaks contact for a moment every few seconds, like people do | move the mouse; `J` for the real webcam |
| Attention | Peripheral motion earns a glance, a short evaluation, then either tracking or a bored return to idle | quick mouse moves |
| Pupil light response | Pupils dilate in the dark and shrink in bright light, with slow adaptation; a loud sound gives a startle dilation, a blink and a backlight flash | `K` / `Shift+K`, `N` |
| Vestibular reflex | When the head turns the eyes counter-rotate to hold the gaze, then recentre | arrow keys |
| Circadian | Morning stretch (a yawn), evening sleepiness, night sleep with occasional stirs and a breathing backlight | `W` cycles the time of day |
| Speech cues | A think-look first, then a squeeze and pupil bounce per syllable, brows up on emphasised words | `Y`, or `speak` over UDP |
| Sound motion | Chirp: a quick double bounce. Sigh: a slow drift down and back | `Shift+N`, `,` |
| Mood ring | Petting softens the lids and warms the iris over a few seconds, fading over twenty | hold `X` |
| Tears | A sad face slowly pools a tear at the inner corner that then falls | `5`, wait |
| Reflections | A soft window reflection on the sclera that shifts with head movement and the light direction | arrows |
| Backlight | Brightness follows the room, dims at night, breathes when asleep. Maps to PWM on the BLK pin later | `K`, `W`, `brightness` command |
| Status glances | Low battery, charging, lost wifi, listening and thinking states, and a breakfast weather glance appear automatically from sensor values | `/` cycles them, or `sense` + `glance` commands |

`A` switches the engine off, leaving the plain animator. `O` adds a clear dome lens over each panel
(barrel magnification and a highlight) to preview that mounting option.

### Interaction games

`Tab` cycles them, or `{"cmd": "game", "name": ...}`.

| Game | Rules |
|---|---|
| `staring` | The duck tries not to blink. Tension builds, then it loses dramatically, unless you blink first (left click), in which case it looks smug |
| `followdot` | It looks left, right, then up and waits for your face to follow (mouse position). A correct follow earns a happy burst of hearts; a timeout earns a disappointed look |
| `peekaboo` | Cover the camera (`C` or right click) and the eyes close. Uncover and it is surprised, then delighted |
| `mirror` | It copies your blinks (left click) and looks where you are |

### Keys

| Key | Action |
|---|---|
| `1`..`9`, `0` | expressions: neutral, happy, sleepy, surprised, sad, curious, love, asleep, angry, suspicious |
| `E` / `Shift+E` | next / previous expression |
| `T` / `Shift+T` | next / previous theme (41 gag modes, see Themes below) |
| `Backspace` | theme off |
| `U` | toggle surprise mode: a random theme every ~20 s while idle |
| `` ` `` | show / hide the control panel |
| `Tab` | cycle interaction games |
| `/` | cycle status glances: clock, weather, compass, wifi, battery, listening, thinking |
| `A` | toggle the behaviour engine |
| mouse | your face (position), peripheral motion (quick moves), your blink (left click), cover the camera (right click) |
| arrows | turn the head; the eyes counter-rotate |
| `K` / `Shift+K` | darker / brighter room |
| `N` / `Shift+N` / `,` | loud noise / chirp / sigh |
| `X` (hold) | pet the duck |
| `C` | cover or uncover the camera |
| `W` | time of day: clock, morning, day, evening, night |
| `O` | dome lens over each panel |
| `Y` | speak a demo sentence |
| `Z` | yawn |
| `J` | real webcam on/off (needs `uv sync --extra camera`) |
| `Space` | neutral |
| `B` | blink now |
| `I` | toggle idle wander |
| mouse move | look at the mouse; idle resumes after a few seconds |
| `P` | cycle test patterns (bars, grid, rings, orientation arrow) |
| `Q` | toggle RGB565 quantisation |
| `F` | cycle frame-rate cap: 60, 30, 20, 15, 10 |
| `R` / `L` | rotate right / left panel 180 degrees |
| `M` | mirror both panels |
| `D` | outline the dirty rectangle sent each frame |
| `H` | toggle the HUD |
| `V` | toggle view: screens only (true to size) or set into a face |
| `+` / `-` | zoom: 1x life size, then 2x, 3x, 4x, 6x |
| `G` | simulate inter-pixel gaps (visible from 3x) |
| `[` / `]` | eye spacing in mm |
| `S` | screenshot into `screenshots/` |
| `Esc` | quit |

### Drive it from another program

The simulator listens for JSON over UDP on `127.0.0.1:5005` (one object per datagram or per line).
The same listener will run on the robot, so behaviour code never touches rendering.

```json
{"cmd": "look", "x": 20, "y": -5, "z": 300, "hold": 2.0}
{"cmd": "express", "name": "happy", "ms": 300}
{"cmd": "blink"}
{"cmd": "idle", "on": true}
{"cmd": "theme", "name": "hal", "hold": 8}
{"cmd": "sense", "light": 0.2, "battery": 12, "wifi": 0, "weather": "rain", "touch": true, "face": [20, -5, 300]}
{"cmd": "speak", "text": "Hello! Any BREAD?"}
{"cmd": "sound", "kind": "chirp"}
{"cmd": "glance", "what": "weather", "kind": "snow"}
{"cmd": "game", "name": "staring"}
{"cmd": "flash", "colour": [90, 200, 255]}
{"cmd": "brightness", "value": 0.4}
{"cmd": "quit"}
```

The full command list with every `sense` field is in the docstring of [udp.py](src/microduck_eyes/control/udp.py).

`x`, `y`, `z` are millimetres in head space: origin midway between the eyes, `x` right,
`y` down, `z` forward. `hold` is how many seconds idle wandering stays suspended.

Demo sequence: start the simulator, then `uv run python scripts/demo.py`.

Expression sheet for review: `uv run python scripts/gallery.py` writes `screenshots/gallery.png`.
Theme sheet: `uv run python scripts/gallery_themes.py` writes `screenshots/gallery-themes.png`.

### Themes (gag modes)

Themes take over the eyes for a few seconds, then return to the current expression. Cycle them
with `T` / `Shift+T`, switch off with `Backspace`, or send `{"cmd": "theme", "name": "..."}`.
`U` toggles surprise mode, which fires a random theme now and then while the duck is idle
(`--surprise 90` on the command line, or `{"cmd": "surprise", "on": true, "every": 90}`).

| Group | Themes |
|---|---|
| Movie and sci-fi | `hal` (HAL 9000 lens, breathing, no blinks), `terminator` (red eye with a tracking reticle and hex readout), `aperture` (mechanical iris blades close over the eye), `eve` (soft blue slits on a white face), `matrix` (glyph rain in the pupils), `spiral` (hypnotist), `pirate` (eye patch left, squint right), `sunglasses` (lenses slide down), `laser` (red glowing pupils locked ahead) |
| Money and games | `dollar` (spinning dollar signs), `slot` (reels of cherry, seven, duck, bread; double duck is a jackpot with falling coins), `dice` (tumbling dice; snake eyes makes the duck sad), `eightball` (shake, then an answer), `poker` (no blinks, no movement, one slow squint at the end) |
| Politics, non-partisan | `debate` (eyes dart anywhere but at the asker, then a confident neutral), `campaign` (star pupils, rosettes, a practiced wink each side), `election` (pie-chart pupils fill up; the result decides happy or sad), `filibuster` (eyes roll back over twenty seconds; any input cancels), `diplomat` (perfect symmetry and a small nod), `tax` (sad eyes crying dollar signs) |
| Computer gags | `boot` (fake BIOS text, a progress bar spanning both panels, then the eyes open), `crt` (old TV power-off collapse), `buffering` (spinning rainbow wheel), `bsod` (blue screen on the left, horror on the right), `notfound` (404 in one eye, the other searches for it), `battery` (battery icon pupils; `level` 0-100 and `charging` params), `roll` (exasperated full eye roll), `googly` (loose pupils with physics; move the mouse to shake them) |
| Cartoon classics | `hearts` (beating hearts and floating hearts), `knockout` (X pupils with orbiting stars), `dizzy` (spirals that sway), `laughcry` (happy squint with streaming tears), `sweat` (a nervous drop slides down, eyes dart), `anime` (sparkly purple eyes with blush), `cateyes` (vertical slits that widen in the dark; `light` 0-1 param), `zzz` (asleep with drifting Zs), `monocle` (gold ring and a raised lid, the other eye squints) |
| Duck-specific | `bread` (toast pupils, rapid happy blinks), `catalert` (pinprick pupils tracking a threat), `rubberduck` (tiny rubber duck pupils nodding while you explain your bug), `migration` (longing gaze up and to the south, slow blinks) |

Themes are built from three mechanisms in [themes.py](src/microduck_eyes/eye/themes.py): pupil sprite swaps
([pupil_sprites.py](src/microduck_eyes/eye/pupil_sprites.py)), full-panel scenes
([scenes.py](src/microduck_eyes/eye/scenes.py)) and particle overlays. Text comes from a built-in 5x7
bitmap font ([font.py](src/microduck_eyes/eye/font.py)). Adding a theme is a small class with an
`apply(t, left, right)` method, registered in `THEME_CLASSES`.

### Camera

`uv sync --extra desktop --extra camera` installs OpenCV 4 (5.x dropped the Haar cascades this uses).
`J` or `--camera` turns the webcam into the face and motion source: Haar face detection at 10 fps on a
320x240 frame, depth from the face width, frame-difference motion for the attention model, cover
detection from brightness, and a rough blink detector from the eye cascade. It runs in a thread and
costs a few percent of a core; on the Radxa a USB camera works the same way. Set `mirror = true` in
`[camera]` if left and right come out swapped.

On macOS the first run asks for camera permission for the app that launched the simulator (Terminal,
VS Code, ...). If it was denied, the HUD shows `camera:ERROR` and the console prints the fix: allow it
under System Settings > Privacy & Security > Camera, then press `J` again. The HUD otherwise shows how
many frames and faces the camera has delivered, e.g. `camera:on 412f/398faces`.

With the camera on, macOS prints `objc` warnings about SDL2 classes being implemented twice (pygame
and OpenCV each bundle a copy of libSDL2). They are harmless in testing here; if you ever see crashes
with the camera on, that duplicate library is the first suspect.

## Tuning the look

Eyebrows (`[brows]`) and a textured iris (`[iris]`) are on by default and carry most of the
emotion; set `enabled = false` to go back to the flat look. `[personality]` has a `lazy_eye`
amount, how often a blink becomes a wink, and how often eye contact is broken.

Everything visual lives in [config/eyes.toml](config/eyes.toml): colours, sclera and pupil
radii, highlight placement, lid curvature, and animation timings. Expression presets are
numbers in [expressions.py](src/microduck_eyes/eye/expressions.py).

## How it stays light

- Nothing renders while the eyes are still. The loop sleeps until the next blink, saccade,
  tween step or input event.
- Sprites (discs, outline ring, lid shapes) are generated once with numpy and cached;
  a frame is a few slice copies and blends.
- Each render reports a dirty rectangle. The desktop backend repaints only the panel;
  the SPI backend will send only those bytes.
- The core depends on numpy only. pygame-ce is an optional extra for the desktop window.

Budget gates in `tests/test_perf.py` fail the suite if render time or bytes-per-update grow.

## Tests

```sh
uv run pytest
```

Tests run headless (`SDL_VIDEODRIVER=dummy`).

## Layout

```
config/eyes.toml            geometry, colours, timings
src/microduck_eyes/
  app.py                    event loop and key handling
  config.py                 TOML loader
  eye/state.py              EyeState and clamping
  eye/sprites.py            cached anti-aliased masks
  eye/renderer.py           compositing and dirty rects
  eye/expressions.py        presets
  eye/animator.py           tweens, blinks, winks, gaze, idle, lazy eye
  sensors.py                sensor hub: state, transition events
  camera.py                 optional OpenCV face/motion/cover/blink source
  behaviour.py              attention, eye contact, light, startle, vestibular, circadian, speech, mood, tears
  eye/font.py               5x7 bitmap font
  eye/pupil_sprites.py      pupil shapes and overlay sprites (26 kinds)
  eye/scenes.py             HAL 9000 lens, CRT power-off
  eye/themes.py             41 theme classes plus the controller (timeouts, surprise mode)
  display/desktop.py        pygame window backend
  display/panel.py          in-window control panel (tabs, buttons, sliders)
  display/effects.py        RGB565, rotation, mirroring
  control/udp.py            JSON command listener
  patterns.py               hardware test patterns
scripts/gallery.py          expression sheet
scripts/gallery_themes.py   theme sheet
scripts/demo.py             scripted UDP sequence
tests/                      pytest suite with perf gates
```

## Hardware (Phase 6, not started)

`--display gc9a01` will drive the real panels via spidev and gpiod on the Radxa Zero using
partial window writes. Wiring and pin numbers will be recorded in `docs/wiring.md` once the
screens and board are in hand.
