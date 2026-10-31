# Microduck Eyes: Desktop Simulator Plan

**Status:** Revised 2026-10-31 (v2: single cute cartoon duck style, resource-light by design). Phases 0 to 5 built 2026-10-31; see Progress at the end.
**Goal:** Mock up how two 1.28" round GC9A01 screens will look as the Microduck's eyes, using a simulator that runs on this Mac, built so the same eye code later drives the real screens from the Radxa Zero while using very little CPU and memory.

---

## 1. What we are simulating

### The screens (Tiardey 2PCS 1.28" GC9A01)

| Property | Value | Why it matters |
|---|---|---|
| Resolution | 240 x 240 px, round panel | Corners of the square buffer are invisible; draw inside a 240 px circle |
| Active area | ~32.4 mm diameter (~7.4 px/mm) | Simulator shows eyes at true physical scale and spacing |
| Colour depth | RGB565 (65K colours) | Flat cartoon colours suit this perfectly; no gradients to band |
| Interface | 4-wire SPI, 3.3 V logic | Bandwidth, not rendering, bounds refresh rate |
| Pins | VCC, GND, SCL, SDA (MOSI), RES, DC, CS, BLK | Two screens share SCL/SDA, each needs its own CS |
| Touch | None | Nothing to simulate |

A full frame is 115,200 bytes. Full-frame refresh ceilings on one shared bus for two screens: ~8 fps at 16 MHz, ~17 fps at 32 MHz, ~26 fps at 48 MHz. The plan avoids this limit by only ever sending the pixels that changed (see section 2), so the practical frame rate during a blink or pupil move is several times higher than these numbers.

**Verify on arrival:** the listing says "bare round screen". Confirm the units have a 7 or 8-pin header rather than a bare flex cable, which would need an FPC breakout board.

### The target computer (Radxa Zero)

Amlogic S905Y2, four Cortex-A53 cores, 40-pin header, Debian or Ubuntu arm64. SPI appears as `/dev/spidevX.Y` via a device-tree overlay whose name differs between OS images; chip-select handling is a known rough edge in community threads. Exact pin numbers come from the official Radxa Zero docs for the chosen image and are deliberately not hard-coded here. Hardware bring-up is Phase 6; nothing earlier depends on it.

---

## 2. Design constraints

### Look: cute cartoon duck eyes

One style only. The eye is designed as a small number of flat-coloured layers, which is both the cute cartoon look and the cheapest thing to render:

1. **Background** outside the eye in the duck's face colour (yellow by default), so the panel edge disappears into the head.
2. **Sclera:** large white disc filling about 85 to 90 percent of the panel, with a thin dark outline ring.
3. **Pupil:** big dark disc (near-black, or very dark brown), roughly 40 to 50 percent of the sclera diameter. Big pupils read as cute and friendly.
4. **Highlights:** one large white specular dot upper-left of the pupil centre and one small dot lower-right. They move with the pupil.
5. **Eyelids:** upper and lower lids in the face colour, drawn as circle segments clipped to the sclera, so a blink looks like skin closing over the eye. Lid tilt (inner edge higher or lower) carries most of the emotion.

Expression presets, all tuned for cuteness: neutral, happy (lower lid raised into a squint, pupils slightly up), sleepy (lids half closed, slow blinks), surprised (lids wide, pupils small), sad (upper lids tilted down at the outer edge, pupils down), curious (one upper lid lower than the other, pupils to one side), love (pupils large, optional heart-shaped pupil sprite), asleep (closed lids with a thin dark line). Angry and suspicious are available but off the default key map.

### Resource budget (hard targets on the Radxa Zero)

| Measure | Target |
|---|---|
| CPU when idle (eyes still, waiting to blink) | under 2 percent of one core |
| CPU during a blink or gaze move | under 25 percent of one core |
| Resident memory | under 50 MB |
| Startup to first frame | under 3 s |
| SPI bytes per blink | a fraction of a full frame, since only the lid band is sent |

How the design meets the budget:

- **Event-driven, not a fixed frame loop.** Nothing is rendered or transmitted while the eye state is unchanged. The main loop sleeps until the next scheduled event (blink due, tween step, incoming command). Idle eyes cost near zero.
- **Pre-rendered sprites instead of per-frame vector drawing.** At startup the renderer builds anti-aliased masks once: the sclera disc with outline, the pupil disc plus highlights, and upper and lower lid shapes at about 32 discrete closure steps and a few tilt angles. A frame is then a handful of numpy slice copies and masked fills. Cache size is a few megabytes.
- **Dirty rectangles everywhere.** The renderer reports the bounding box of what changed (pupil old plus new position, or the lid band). The desktop backend repaints only that; the SPI backend sets the GC9A01 column/row window and sends only those bytes. A pupil move is about 10 to 15 KB instead of 115 KB.
- **Integer pixel positions with eased tweens.** At 7.4 px/mm, whole-pixel steps look smooth with ease-in-out timing, so there is no sub-pixel resampling.
- **Minimal dependencies in the core.** The eye model, renderer, animator and SPI backend depend on numpy only. pygame-ce is an optional dependency pulled in just for the desktop window. The Radxa never loads SDL.
- **No threads for rendering, no asyncio.** One process, one loop, a non-blocking UDP socket polled in the same loop.

### Stack: Python 3.12, numpy, optional pygame-ce, managed by uv

Why Python is still the right call given the budget: with sprites and dirty rectangles, per-frame work is a few array copies of at most 240 x 240 bytes, which is well under a millisecond even on an A53. The expensive parts (SPI transfer) happen in the kernel. Python's cost is paid once at startup. If measurements in Phase 6 ever miss the budget, the renderer sits behind one small interface and can be ported to C without touching the animator or API.

Rejected: web canvas (not portable to SPI), C or Rust from the start (slower to iterate on the look, not needed at this pixel count), LVGL (heavier than the problem).

### Architecture

```
EyeState (per eye)  ->  SpriteRenderer  ->  240x240 uint8 RGB numpy array + dirty rect, x2  ->  Display backend
  pupil x/y (int px), pupil scale,                                                              |- DesktopDisplay (pygame window; bezel, round mask,
  upper/lower lid step, lid tilt,                                                               |   integer upscale, mm spacing)   [optional dep]
  highlight on/off                                                                              '- GC9A01Display (spidev + gpiod, partial window
        ^                                                                                           writes)                        [Phase 6]
  Animator (tweens, blink scheduler, gaze with convergence, idle saccades, expression presets)
        ^
  Controls (keyboard + mouse on desktop; JSON-over-UDP for the robot brain; identical on hardware)
```

Desktop fidelity rules so the mockup is honest:

1. Render at native 240 x 240, integer-upscale with nearest-neighbour (2x or 3x). Real pixel grain stays visible.
2. Circular mask plus the panel's black bezel ring, on a face-colour background.
3. Eyes placed at configurable centre-to-centre spacing in millimetres, adjustable live.
4. Toggles: RGB565 quantisation, frame-rate cap (10/15/20/30), per-eye 180 degree rotation and mirroring, visualise dirty rectangles.
5. Screenshot and short GIF export.

### Project layout

```
Microduck eyes/
  pyproject.toml                 uv; core deps: numpy. optional extra [desktop]: pygame-ce, pillow (GIF export)
  README.md                      run instructions, key bindings, config reference, resource measurements
  config/eyes.toml               geometry, colours, spacing, expression presets, animation timings
  plans/
  src/microduck_eyes/
    __main__.py                  `python -m microduck_eyes --display desktop|gc9a01`
    app.py                       event loop: sleep-until-next-event, controls -> animator -> renderer -> display
    config.py                    dataclasses + TOML loader (tomllib, stdlib)
    eye/
      state.py                   EyeState (integer pixel fields) and clamping
      sprites.py                 one-time generation of anti-aliased masks (numpy only)
      renderer.py                composite sprites into frame; returns dirty rect
      expressions.py             named presets
      animator.py                tweens with easing, blink scheduler, gaze controller, idle saccades
    display/
      base.py                    Display protocol: show(eye_index, frame, dirty_rect), close()
      desktop.py                 pygame backend (imports pygame lazily)
      effects.py                 rgb565 quantise, rotation/mirror, dirty-rect overlay
      gc9a01.py                  SPI backend with window writes (Phase 6)
    control/
      keyboard.py
      udp.py                     non-blocking JSON listener
    patterns.py                  test patterns for orientation and colour checks
  tests/
    test_state.py, test_sprites.py, test_renderer.py (golden PNGs, headless),
    test_animator.py, test_effects.py, test_perf.py (render time and bytes-per-update budget)
  assets/golden/
```

---

## 3. Phases

### Phase 0: Scaffold (small)

- `uv init`, pin Python 3.12, numpy as core dependency, pygame-ce and pillow under a `desktop` extra. src layout. README. git init.
- Headless pytest harness proven with one test.

Done when: `uv run python -m microduck_eyes` opens an empty window and `uv run pytest` passes.

### Phase 1: Display backend and test patterns (small)

- `Display` protocol taking a frame plus dirty rect. `DesktopDisplay` with bezel, round mask, integer upscale, mm spacing, face-colour background. Repaints only the dirty region.
- Test patterns: colour bars, 10 px grid, concentric rings, "up" arrow with L/R label. Reused in Phase 6 to verify orientation, mirroring and colour order.
- Keys: `+`/`-` scale, `[`/`]` spacing, `P` patterns, `S` screenshot.

Done when: both panels show patterns at true relative scale and a screenshot saves.

### Phase 2: Sprites, eye model and renderer (medium)

- `sprites.py` generates anti-aliased discs, outline ring, highlights and lid shapes (closure steps and tilt angles) with numpy at startup; measured generation time under 1 s on the Mac.
- `EyeState` with integer pupil position, pupil scale index, lid steps, lid tilt index, highlight flag. Clamping keeps the pupil fully inside the sclera.
- `renderer.py` composites layers in order (background, sclera, pupil, highlights, lids) and returns the dirty rect.
- All expression presets from section 2 as config numbers; a gallery mode (`E`) shows every preset side by side for a look review.

Done when: every preset renders, golden-image tests pass, a full eye render is under 1 ms and a pupil-only update under 0.3 ms on the Mac.

### Phase 3: Animation and interaction (medium)

- Tween engine with ease-in-out over integer steps; each field has its own duration.
- Blink scheduler: close ~100 ms, open ~150 ms, random interval 2 to 6 s, occasional double blink. Lids may close a step apart for a softer look.
- Gaze controller: head-space target in mm mapped to per-eye pupil offsets with slight convergence. Mouse drives it on the desktop.
- Idle saccades: small random jumps every 0.5 to 2 s, slow drift, occasional glance-and-return.
- Pupil scale tied to expression (surprised small, sleepy and love large). Expression transitions over 200 to 400 ms.
- Event loop sleeps until the next tween tick or blink; no rendering while still. Keys `1`..`8` expressions, `B` blink, `Space` neutral, `I` toggle idle.

Done when: the eyes feel alive with no input, and the process shows near-zero CPU while idle in Activity Monitor.

### Phase 4: Fidelity toggles and export (small)

- `Q` RGB565 quantise, `F` cycle frame-rate cap, `R`/`L` rotate right/left panel, `M` mirror, `D` show dirty rectangles, `H` overlay with fps, bytes sent per second and render time.
- `G` record a 5 s GIF via Pillow.

Done when: a 15 fps RGB565 capture and the bytes-per-second readout can be reviewed together.

### Phase 5: Control API (small)

- JSON lines over UDP, default port 5005: `{"cmd":"look","x":20,"y":-5}`, `{"cmd":"express","name":"happy","hold":2.0}`, `{"cmd":"blink"}`, `{"cmd":"idle","on":true}`.
- Tiny Python client helper and a demo script: wake up, look around, get surprised, fall asleep.

Done when: the demo drives the simulator from a second terminal.

### Phase 6: Hardware backend on the Radxa Zero (medium, after screens are in hand)

- Install the chosen OS image; enable the spidev overlay per the Radxa docs; confirm `/dev/spidev*`. Raise `spidev.bufsiz` so a full frame goes in two transfers.
- Wire shared SCL/SDA, separate CS, RES and DC per screen via gpiod, backlights to 3.3 V or PWM. Record the final pin table in `docs/wiring.md`.
- `GC9A01Display`: reset, init sequence ported from a known-good driver, column/row window set from the dirty rect, RGB565 byte-swap with numpy, write. Verify with Phase 1 patterns.
- Measure: SPI clock sweep 16 to 80 MHz, CPU percent idle and during blinks, bytes per second, resident memory. Record results in the README against the budget table.
- systemd unit to start on boot, with the UDP listener.

Done when: both panels run the Phase 5 demo within the resource budget in section 2.

---

## 4. Testing strategy

- **Unit:** state clamping, tween maths, blink scheduler (seeded RNG), RGB565 round-trip, dirty-rect correctness (changed pixels always inside the reported rect).
- **Snapshot:** each preset rendered headless and compared to golden PNGs with a small tolerance; `--update-goldens` to refresh deliberately.
- **Performance gate in CI:** full render under 1 ms, pupil update under 0.3 ms, sprite generation under 1 s, bytes per pupil update under 16 KB. Failing these fails the test run, so the budget cannot silently erode.
- **Manual:** README checklist for judging the mockup (readable from 1 m, blink believable at 15 fps, lid colour matches the head, pupils look cute not creepy).

---

## 5. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Screens are bare flex panels, not modules | Cannot wire | Check on arrival; order a GC9A01 FPC adapter |
| Radxa SPI overlay or CS fights back | Delays Phase 6 | Phases 0 to 5 are hardware-independent; drive CS from ordinary GPIO via gpiod |
| Discrete lid steps look steppy | Blinks feel mechanical | Blinks are fast, so 32 steps over 100 ms is 3 ms per step; increase steps if needed, cache stays small |
| Python interpreter overhead exceeds budget | CPU too high | Measure in Phase 6; port `renderer.py` to C behind the same interface |
| Cartoon proportions need tuning on the real panel | Rework | Everything is config numbers; gallery mode makes side-by-side tuning quick |

---

## 6. Decisions needed from you

1. **Face colour and eye spacing:** approximate centre-to-centre distance in mm and the head colour around the screens. Default: 45 mm, duck yellow.
2. **Pupil colour:** pure black or dark brown. Default: near-black.
3. **Radxa OS image** (Radxa Debian, Armbian, DietPi). Only matters for Phase 6.
4. **Who drives the eyes:** a Python process on the same board, or something over the network. Default: UDP JSON, which covers both.

---

## 7. Next step

On approval: execute Phases 0 to 2 in one go so there is something to look at, including the expression gallery, then review the look before animation polish.

## References

- GC9A01 module pinout and specs (generic 1.28" modules): https://shop.controllerstech.com/products/1-28-inch-gc9a01-round-tft-lcd-display-module , https://protosupplies.com/?p=15523
- Radxa Zero SPI overlay naming and chip-select issues (community threads, verify against official docs): https://forum.radxa.com/t/cannot-detect-spi/10807 , https://dietpi.com/forum/t/cant-enable-spi-on-dietpi-radxa-zero/22250
- Waveshare GC9A01 Raspberry Pi example (candidate source for the init sequence): https://thinkrobotics.com/collections/waveshare/products/waveshare-1-28inch-lcd-module

---

## Progress (2026-10-31)

| Phase | State | Notes |
|---|---|---|
| 0 Scaffold | done | uv project, Python 3.13, numpy core, pygame-ce as `desktop` extra, 26 tests passing |
| 1 Display + patterns | done | round panels with bezel at mm scale, 4 test patterns, screenshots |
| 2 Sprites + renderer | done | cached numpy masks, dirty rects, 10 presets, `scripts/gallery.py` sheet |
| 3 Animation | done | eased tweens, blink scheduler with double blinks, gaze with convergence, idle saccades, mouse follow, event-driven loop |
| 4 Fidelity toggles | mostly done | RGB565, fps cap, rotate/mirror, dirty-rect overlay, HUD, screenshots. GIF export not built |
| 5 Control API | done | JSON over UDP, `scripts/demo.py` sequence |
| 6 Hardware | not started | waiting on screens and Radxa image |
| 1b Screens view | done (2026-10-31) | default view shows only the round panels at life size using the display's measured pt/mm; zoom 1/2/3/4/6x with crisp integer pre-scale then area resample; `G` inter-pixel gaps; `V` switches to the face mockup |
| 9 Control panel | done (2026-10-31) | in-window tabbed panel with a control for every option, live state highlighting, scroll, backquote toggle, `--no-panel`; test clicks every control |
| 8 Alive layer | done (2026-10-31) | sensor hub + behaviour engine (attention model, eye contact with glance-aways, pupil light response and startle, vestibular reflex, circadian phases, speech cues, chirp/sigh motion, mood ring, pooling tears, backlight brightness, sclera reflections), eyebrows and textured iris, winks and lazy eye, status glances (clock, weather, compass, wifi, battery, listening, thinking, iris flash), games (staring, follow the dot, peekaboo, mirror), yawn, dome lens preview, optional OpenCV camera source, verified live on the Mac webcam 2026-10-31 (face found in 176 of 180 frames at 320x240, depth estimate plausible) |
| 7 Fun modes | all 41 done (2026-10-31) | every row of the backlog below is implemented as a theme class; `T` cycles, `theme` command with params, surprise mode (`U`, `--surprise`, `surprise` command). PNG asset loading was not needed: every sprite is procedural |

Measured on the Mac (M-series): idle process 0 percent CPU and 26 MB resident with blinks and saccades enabled; one eye full render about 0.3 ms, pupil-only move about 0.3 ms with an 18 KB dirty region; RGB565 pack of a full frame under 0.1 ms.

Open refinements for the look review: lid edge colour and thickness, whether lids should carry a dark outline like the sclera, pupil size, highlight placement, eye spacing and face colour once the head design exists.

---

## Fun modes backlog (added 2026-10-31)

Themed takeovers of the eyes for comedy. Each is either a **pupil swap** (the pupil disc becomes another
sprite, lids and sclera stay), a **scene** (the whole panel becomes something else), or an **overlay**
(something drawn on top of the normal eye). All three fit the existing pipeline: sprites are generated or
loaded once, animations are short pre-rendered frame sets, dirty rects stay small, and the idle loop still
sleeps. Each mode is triggered by `{"cmd":"theme","name":...,"hold":seconds}` and times out back to the
current expression. Pop-culture ones are homages drawn by us, not copied assets.

### Movie and sci-fi

| Mode | What you see | Type | Cost |
|---|---|---|---|
| HAL 9000 | Both panels go black with a deep red radial glow and a tiny yellow centre dot. No blinking. Slow breathing pulse. Pupil stops following you and just stares. Optional "I'm sorry Dave" via the robot's speaker. | scene | easy (one gradient sprite, 8 brightness steps) |
| Terminator | Red glowing eye, thin white targeting reticle that tracks the gaze target, tiny scrolling hex text in the corner. | scene + overlay | medium |
| Wall-E / Eve | Mechanical aperture: iris blades that open and close instead of soft lids. Eve version: two soft blue slits that tilt for emotion. | scene | medium (blade frames pre-rendered) |
| Matrix | Green falling glyph rain inside the pupil, sclera tinted faintly green. | pupil swap, animated | medium |
| Hypnotist | Black and white spiral rotating in the pupil, pupils dilate to maximum, lids droop. | pupil swap, 12 rotating frames | easy |
| Pirate | Left panel becomes an eye patch (black with a strap line across the yellow), right eye squints hard. | scene + expression | easy |
| Sunglasses "deal with it" | Dark lenses slide down from the top with a white reflection streak, then the eyes vanish behind them. | overlay, animated | easy |
| Laser eyes | Pupils glow red, a red bloom spills onto the sclera, eyes lock dead ahead. | pupil swap + tint | easy |

### Money and games

| Mode | What you see | Type | Cost |
|---|---|---|---|
| Scrooge dollar eyes | Pupils become green dollar signs. On trigger they spin like slot reels and land with a bounce. Pupils dilate. | pupil swap, animated | easy |
| Slot machine | Pupils scroll through symbols (cherry, seven, duck, bread) and stop one eye after the other. Jackpot: both ducks, happy squint, coins fall through the sclera. | pupil swap, animated | medium |
| Snake eyes | Each pupil shows a die face; a "roll" command tumbles them. Two ones means snake eyes and a sad expression. | pupil swap | easy |
| Magic 8-ball | Pupil becomes the blue triangle window: "Ask again later", "Outlook good", "No". | pupil swap with text | easy |
| Poker face | Zero blinks, zero saccades for a set time, then one slow suspicious squint. | expression timing | trivial |

### Politics, kept non-partisan (no real people, no parties)

| Mode | What you see | Type | Cost |
|---|---|---|---|
| Debate mode | Whenever a "question" arrives the eyes dart anywhere except at the asker, then hold a confident neutral. | gaze behaviour | trivial |
| Campaign mode | Pupils become stars, a rosette badge appears in the corner, the eyes do a practiced slow wink to the left panel, then to the right. | pupil swap + overlay | easy |
| Election night | Pupils are pie charts filling up over time; the expression tracks the "result" from surprised to happy or sad. | pupil swap, animated | medium |
| Filibuster | Eyes slowly roll back and lids droop over several minutes. Any input resets them to wide awake. | expression timing | easy |
| Diplomat | Perfect symmetric neutral, a nod-like gaze dip when spoken to, never surprised. | expression | trivial |
| Tax season | Dollar signs fall out of the eyes like tears, lids sad. | overlay, animated | easy |

### Computer and robot gags

| Mode | What you see | Type | Cost |
|---|---|---|---|
| Boot sequence | On power-up: fake BIOS text scroll, a progress bar across both panels, then the eyes "open" for the first time. | scene | medium |
| CRT power-off | On shutdown: the eye collapses to a bright horizontal line, then a dot, then black. | scene, 10 frames | easy |
| Buffering | Pupil becomes a spinning rainbow wheel (or an hourglass) while the robot is thinking. | pupil swap, animated | easy |
| Blue screen | One panel shows a blue field with a white ":(" and "Your duck ran into a problem", the other eye looks at it in horror. | scene | easy |
| 404 | Text "EYE NOT FOUND" in the pupil, the other eye looks for it. | pupil swap | easy |
| Low battery | Pupil shows a red battery icon, lids droop in steps as charge drops; a lightning bolt when charging. | pupil swap, driven by real battery level | easy |
| Reboot roll | Exasperated full 360 degree eye roll when asked to do something again. | gaze path | trivial |
| Googly eyes | Pupils become loose weights on a spring that wobble and bounce off the sclera edge when the robot moves (accelerometer input). Surprisingly funny on a robot that waddles. | physics pupil | medium |

### Cartoon classics

| Mode | What you see | Type | Cost |
|---|---|---|---|
| Heart eyes plus | Love preset but the pupils are beating hearts and small hearts float up and out of the panel. | pupil swap + overlay | easy |
| Knocked out | Pupils become X marks, small stars orbit the panel. Triggered by a bump. | pupil swap + overlay | easy |
| Dizzy spirals | Spinning spirals plus the whole eye sways. | pupil swap | easy |
| Laughing-crying | Happy squint with streams of blue tears pouring out of the outer corners. | overlay, animated | easy |
| Nervous sweat | One big sweat drop slides down the panel edge, eyes dart. | overlay | easy |
| Anime sparkle | Several oversized highlights, pupils huge, a faint pink blush at the lower edge. | pupil swap | easy |
| Cat eyes | Vertical slit pupils that widen in the dark (light sensor) and track very fast. | pupil swap | easy |
| Zzz | Asleep preset with "Z" letters drifting up and out of each panel. | overlay, animated | easy |
| Monocle | One eye gets a thin gold ring and a raised lid, the other squints: distinguished duck. | overlay + expression | easy |

### Duck-specific

| Mode | What you see | Type | Cost |
|---|---|---|---|
| Bread detected | Pupils become slices of bread, extreme dilation, rapid happy blinks. | pupil swap | easy |
| Cat detected | Pupils shrink to pinpricks, lids wide, eyes lock on and track the threat. | expression + gaze | trivial |
| Rubber duck debugging | Pupils become tiny rubber ducks; the eyes nod slowly while you explain your bug. | pupil swap + gaze | easy |
| Migration | Eyes gaze upward and to the south, longingly, every autumn afternoon. | gaze + scheduling | trivial |

### How this gets built (Phase 7, after the look review)

1. **Pupil sprite swap**: `EyeState` gains `pupil_sprite` (name) and `pupil_frame` (int). `sprites.py` grows a
   small library of generated shapes (dollar, star, heart, X, slit, die faces) and a loader for 8-bit PNGs in
   `assets/pupils/` for anything hard to draw procedurally. Animated ones are frame lists; the animator steps the
   frame index on a timer, so each step is one small dirty rect.
2. **Scenes**: a `SceneRenderer` with the same `render(state) -> (frame, dirty)` contract as `EyeRenderer`.
   The app swaps renderers per panel. HAL, CRT power-off, boot sequence and blue screen live here.
3. **Overlays**: a list of lightweight particles (hearts, Z, tears, stars, sweat) with position, velocity and a
   sprite; drawn after lids; each contributes its own bbox to the dirty rect. Capped at a handful at a time.
4. **Theme command**: `{"cmd":"theme","name":"hal","hold":10}` and a `T` key in the simulator that cycles themes.
   Themes time out back to the current expression. An optional "surprise me" setting fires a random gag at a
   low rate when idle.
5. Resource rule stays: no theme may render while nothing changes, and animated themes run at 10 to 15 fps
   with pre-rendered frames.

All built 2026-10-31, including surprise mode. Scenes that sit on top of the eye (the aperture) use a fourth
mechanism: the eye is rendered first and the scene draws over it. A 5x7 bitmap font covers all text gags without
font files. Not built: PNG asset loading, since nothing needed it.
