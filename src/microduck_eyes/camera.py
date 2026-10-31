"""Optional camera source: face position, motion, cover detection and a rough blink detector.

Needs OpenCV (`uv sync --extra camera`). The detector is pure-function style so it can be
tested with synthetic frames; the CameraSource wraps it in a capture thread at a low rate.
"""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from .config import CameraCfg
from .sensors import SensorHub


def available() -> bool:
    try:
        import cv2
        return hasattr(cv2, "CascadeClassifier")
    except Exception:
        return False


class FaceDetector:
    """Haar-cascade face finder plus frame-difference motion and brightness-based cover detection."""

    def __init__(self, cfg: CameraCfg):
        import cv2

        self.cv2 = cv2
        self.cfg = cfg
        root = cv2.data.haarcascades
        self.face_cascade = cv2.CascadeClassifier(root + "haarcascade_frontalface_default.xml")
        self.eye_cascade = cv2.CascadeClassifier(root + "haarcascade_eye.xml")
        self.prev_gray: np.ndarray | None = None
        self.eyes_seen_frames = 0
        self.eyes_missing_frames = 0

    def process(self, frame_bgr: np.ndarray, now: float) -> dict:
        cv2 = self.cv2
        h, w = frame_bgr.shape[:2]
        raw = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(raw)               # for the cascades only; motion and light use the raw image
        out: dict = {"face": None, "motion": None, "covered": False, "user_blink": False, "light": None}

        mean = float(raw.mean()) / 255.0
        out["light"] = mean
        out["covered"] = mean < 0.08

        if self.prev_gray is not None and not out["covered"]:
            diff = cv2.absdiff(raw, self.prev_gray)
            mag = float((diff > 25).mean())
            if mag > 0.01:
                ys, xs = np.nonzero(diff > 25)
                cx, cy = xs.mean(), ys.mean()
                dx = (cx - w / 2) / (w / 2)
                dy = (cy - h / 2) / (h / 2)
                if self.cfg.mirror:
                    dx = -dx
                out["motion"] = (-dx, dy, min(mag * 10, 1.0))   # -dx: camera left is the viewer's right
        self.prev_gray = raw

        if not out["covered"]:
            faces = self.face_cascade.detectMultiScale(gray, 1.2, 4, minSize=(24, 24))
            if len(faces):
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                f_px = (w / 2) / math.tan(math.radians(self.cfg.hfov_deg) / 2)
                z = f_px * self.cfg.face_width_mm / max(fw, 1)
                cx, cy = x + fw / 2, y + fh / 2
                x_mm = (cx - w / 2) / f_px * z
                y_mm = (cy - h / 2) / f_px * z
                if not self.cfg.mirror:
                    x_mm = -x_mm
                out["face"] = (x_mm, y_mm, z)
                roi = gray[y:y + fh // 2, x:x + fw]
                eyes = self.eye_cascade.detectMultiScale(roi, 1.15, 3, minSize=(10, 10))
                if len(eyes):
                    if 1 <= self.eyes_missing_frames <= 3 and self.eyes_seen_frames >= 3:
                        out["user_blink"] = True
                    self.eyes_seen_frames += 1
                    self.eyes_missing_frames = 0
                else:
                    self.eyes_missing_frames += 1
                    if self.eyes_missing_frames > 3:
                        self.eyes_seen_frames = 0
        return out


class CameraSource:
    def __init__(self, cfg: CameraCfg):
        self.cfg = cfg
        self.detector = FaceDetector(cfg)
        self._latest: dict | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: str | None = None
        self.frames = 0
        self.faces = 0

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self):
        cv2 = self.detector.cv2
        cap = cv2.VideoCapture(self.cfg.index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        if not cap.isOpened():
            self.error = (f"camera {self.cfg.index} did not open. On macOS allow camera access for the app that runs "
                          "the simulator (System Settings > Privacy & Security > Camera), then press J again.")
            return
        period = 1.0 / max(self.cfg.fps, 1.0)
        failures = 0
        while not self._stop.is_set():
            t0 = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                failures += 1
                if failures > 30:
                    self.error = f"camera {self.cfg.index} stopped delivering frames"
                    break
                time.sleep(0.1)
                continue
            failures = 0
            self.frames += 1
            if True:
                if frame.shape[1] > self.cfg.width:
                    frame = cv2.resize(frame, (self.cfg.width, self.cfg.height))
                result = self.detector.process(frame, t0)
                with self._lock:
                    self._latest = result
            dt = time.perf_counter() - t0
            if dt < period:
                time.sleep(period - dt)
        cap.release()

    def poll(self, hub: SensorHub, now: float):
        with self._lock:
            r, self._latest = self._latest, None
        if r is None:
            return
        if r["face"] is not None:
            self.faces += 1
            hub.face(now, *r["face"])
        if r["motion"] is not None:
            dx, dy, mag = r["motion"]
            hub.event("motion", now, dx=dx, dy=dy, magnitude=mag)
        if r["covered"] != hub.state.camera_covered:
            hub.set(now, camera_covered=r["covered"])
        if r["user_blink"]:
            hub.event("user_blink", now)
        if r["light"] is not None and not r["covered"]:
            hub.set(now, light=0.8 * hub.state.light + 0.2 * min(r["light"] * 1.6, 1.0))
