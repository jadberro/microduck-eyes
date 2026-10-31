"""Drive a running simulator over UDP: wake up, look around, get surprised, fall asleep.

Start the simulator first (uv run microduck-eyes), then: uv run python scripts/demo.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from microduck_eyes.control.udp import send  # noqa: E402

STEPS = [
    ({"cmd": "idle", "on": False}, 0.0),
    ({"cmd": "express", "name": "asleep", "ms": 0}, 1.5),
    ({"cmd": "express", "name": "sleepy", "ms": 900}, 1.5),
    ({"cmd": "blink"}, 0.6),
    ({"cmd": "express", "name": "neutral", "ms": 400}, 0.8),
    ({"cmd": "look", "x": 150, "y": 0, "hold": 2}, 0.9),
    ({"cmd": "look", "x": -150, "y": 20, "hold": 2}, 0.9),
    ({"cmd": "look", "x": 0, "y": -80, "z": 120, "hold": 2}, 0.9),
    ({"cmd": "express", "name": "curious", "ms": 250}, 1.2),
    ({"cmd": "look", "x": 0, "y": 0, "z": 60, "hold": 2}, 0.8),
    ({"cmd": "express", "name": "surprised", "ms": 120}, 1.2),
    ({"cmd": "blink"}, 0.5),
    ({"cmd": "express", "name": "happy", "ms": 300}, 1.5),
    ({"cmd": "express", "name": "love", "ms": 500}, 1.8),
    ({"cmd": "express", "name": "neutral", "ms": 400}, 1.0),
    ({"cmd": "speak", "text": "Hello there! I am Microduck. Do you have any BREAD?"}, 4.5),
    ({"cmd": "sense", "light": 0.05}, 2.0),
    ({"cmd": "sense", "light": 0.95}, 2.0),
    ({"cmd": "sense", "light": 0.6}, 1.0),
    ({"cmd": "sound", "kind": "loud"}, 1.5),
    ({"cmd": "sound", "kind": "chirp"}, 1.0),
    ({"cmd": "sound", "kind": "sigh"}, 2.2),
    ({"cmd": "sense", "touch": True}, 4.0),
    ({"cmd": "sense", "touch": False}, 1.0),
    ({"cmd": "sense", "battery": 12}, 3.5),
    ({"cmd": "sense", "battery": 80, "charging": True}, 3.5),
    ({"cmd": "sense", "wifi": 0}, 3.0),
    ({"cmd": "sense", "wifi": 3}, 0.5),
    ({"cmd": "glance", "what": "clock"}, 3.5),
    ({"cmd": "glance", "what": "weather", "kind": "rain"}, 3.5),
    ({"cmd": "glance", "what": "compass", "heading": 230}, 3.5),
    ({"cmd": "flash", "colour": [90, 200, 255]}, 1.0),
    ({"cmd": "theme", "name": "yawn"}, 3.0),
    ({"cmd": "theme", "name": "dollar", "hold": 3.5}, 4.0),
    ({"cmd": "theme", "name": "spiral", "hold": 3.0}, 3.5),
    ({"cmd": "theme", "name": "hearts", "hold": 4.0}, 4.5),
    ({"cmd": "theme", "name": "slot", "hold": 5.0}, 5.5),
    ({"cmd": "theme", "name": "googly", "hold": 4.0}, 4.5),
    ({"cmd": "theme", "name": "bsod", "hold": 4.0}, 4.5),
    ({"cmd": "theme", "name": "hal", "hold": 5.0}, 5.5),
    ({"cmd": "express", "name": "surprised", "ms": 100}, 1.0),
    ({"cmd": "theme", "name": "crt", "hold": 3.0}, 3.5),
    ({"cmd": "express", "name": "sleepy", "ms": 1200}, 1.8),
    ({"cmd": "express", "name": "asleep", "ms": 900}, 2.0),
    ({"cmd": "express", "name": "neutral", "ms": 500}, 0.0),
    ({"cmd": "idle", "on": True}, 0.0),
]


def main(port: int = 5005):
    for msg, pause in STEPS:
        send(msg, port=port)
        print(msg)
        time.sleep(pause)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5005)
