"""Non-blocking JSON-lines-over-UDP command listener.

Commands (one JSON object per datagram, or several separated by newlines):
  {"cmd": "look", "x": 20, "y": -5, "z": 300, "hold": 2.0}   mm in head space
  {"cmd": "express", "name": "happy", "ms": 300}
  {"cmd": "blink"}
  {"cmd": "idle", "on": true}
  {"cmd": "theme", "name": "hal", "hold": 8}        any theme name, or off; extra keys are theme params
  {"cmd": "theme", "name": "battery", "level": 15, "charging": false}
  {"cmd": "surprise", "on": true, "every": 90}      random theme roughly every N seconds while idle
  {"cmd": "sense", "light": 0.2, "battery": 12, "charging": false, "wifi": 0, "weather": "rain",
                   "heading": 270, "touch": true, "camera_covered": false, "listening": true,
                   "thinking": false, "sound": 0.8, "head_yaw_rate": 45, "face": [20, -5, 300]}
  {"cmd": "sound", "kind": "chirp"}                 chirp | sigh | loud
  {"cmd": "speak", "text": "Hello! Any BREAD?"}     syllable cues; CAPS or ! for emphasis
  {"cmd": "glance", "what": "weather", "kind": "snow"}
  {"cmd": "game", "name": "staring"}                staring | followdot | peekaboo | mirror | off
  {"cmd": "flash", "colour": [90, 200, 255]}
  {"cmd": "brightness", "value": 0.4}               null to hand control back to the behaviour engine
  {"cmd": "pet", "on": true}
  {"cmd": "behaviour", "on": false}
  {"cmd": "camera", "on": true}
"""
from __future__ import annotations

import json
import socket
from typing import Callable

Handler = Callable[[dict], None]


class UdpControl:
    def __init__(self, handler: Handler, host: str = "127.0.0.1", port: int = 5005):
        self.handler = handler
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.setblocking(False)
        self.errors = 0

    def poll(self) -> int:
        """Dispatch every waiting datagram. Returns the number of commands handled."""
        n = 0
        while True:
            try:
                data, _ = self.sock.recvfrom(65535)
            except BlockingIOError:
                return n
            except OSError:
                return n
            for line in data.decode("utf-8", "replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if isinstance(msg, dict):
                        self.handler(msg)
                        n += 1
                except (ValueError, KeyError, TypeError):
                    self.errors += 1

    def close(self):
        self.sock.close()


def send(msg: dict, host: str = "127.0.0.1", port: int = 5005) -> None:
    """Tiny client helper used by scripts and tests."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto((json.dumps(msg) + "\n").encode(), (host, port))
