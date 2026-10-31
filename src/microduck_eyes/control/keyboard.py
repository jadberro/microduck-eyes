"""Key bindings for the simulator, kept in one place so the README can quote them."""

HELP = """
Keys
  1..9, 0      expressions in order: neutral happy sleepy surprised sad curious love asleep angry suspicious
  E / Shift+E  next / previous expression
  T / Shift+T  next / previous theme (41 gag modes, see README)
  Backspace    theme off
  U            toggle surprise mode (a random theme every ~20 s while idle)
  Tab          cycle interaction games: staring contest, follow the dot, peekaboo, mirror, off
  /            cycle status glances: clock, weather, compass, wifi, battery, listening, thinking, off
  A            toggle the behaviour engine (attention, eye contact, light, speech cues, circadian...)
  mouse        stands in for the camera: position = your face, quick moves = peripheral motion,
               left click = you blinked, right click = cover/uncover the camera
  arrows       turn the head (IMU): eyes counter-rotate, then recentre
  K / Shift+K  darker / brighter room (pupils adapt, backlight follows)
  N / Shift+N  loud noise (startle) / chirp;   ,  sigh
  X (hold)     pet the duck: eyes soften, iris warms
  C            cover / uncover the camera
  W            time of day: clock, morning, day, evening, night
  O            dome lens over each panel
  Y            speak a demo sentence (syllable cues, brow emphasis)
  Z            yawn
  J            toggle the real webcam as face/motion source (needs the camera extra)
  `            show / hide the control panel (every option as a button or slider)
  Space        neutral
  B            blink now
  I            toggle idle wander (saccades)
  mouse move   look at the mouse (idle resumes after a few seconds)
  P            cycle test patterns (eyes return on any expression key)
  Q            toggle RGB565 quantisation
  F            cycle frame-rate cap (60 30 20 15 10)
  R / L        rotate right / left panel 180 degrees
  M            mirror both panels
  D            show dirty rectangles
  H            toggle HUD
  V            toggle view: screens only (true to size) / set into a face
  + / -        zoom: 1x life size, then 2x 3x 4x 6x
  G            simulate the LCD's inter-pixel gaps (visible from 3x)
  [ / ]        eye spacing in mm
  S            screenshot into ./screenshots
  Esc          quit
"""
