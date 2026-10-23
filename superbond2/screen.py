"""Grabbing the game canvas from the screen, and finding it in the first place.

The stone frame around the 3D view looks the same every time, so the canvas can be found
anywhere on the desktop by matching points sampled from it (fixed_frame.json, measured on
the real client by skillbot). `calibrate` does that once and saves the position.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .eyes import FRAME_FILE
from .layout import CANVAS_H, CANVAS_W

FRAME_TOL = 12           # per color channel
FRAME_MIN = 0.85         # share of the frame's points that must match


class Screen:
    """The game canvas, grabbed from the desktop at a known origin."""

    def __init__(self, origin: tuple[int, int]):
        import mss                      # only needed on a real desktop
        self.origin = origin
        self._sct = mss.mss()

    @classmethod
    def load(cls, path: Path) -> "Screen":
        if not path.exists():
            raise SystemExit("Not calibrated yet: run `python -m superbond2 calibrate` first.")
        return cls(tuple(json.loads(path.read_text())["origin"]))

    def grab(self) -> np.ndarray:
        """The canvas as an RGB array of shape (503, 765, 3)."""
        box = {"left": self.origin[0], "top": self.origin[1], "width": CANVAS_W, "height": CANVAS_H}
        return np.asarray(self._sct.grab(box))[..., 2::-1].copy()       # BGRA → RGB

    def to_screen(self, pt) -> tuple[int, int]:
        return self.origin[0] + int(pt[0]), self.origin[1] + int(pt[1])


def grab_desktop() -> tuple[np.ndarray, tuple[int, int]]:
    """The whole primary monitor as RGB, and its top-left in screen coordinates."""
    import mss
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        img = np.asarray(sct.grab(mon))[..., 2::-1].copy()
    return img, (mon["left"], mon["top"])


def find_canvas(desktop: np.ndarray, sample: int = 300) -> tuple[tuple[int, int] | None, float]:
    """Where the canvas's top-left is in `desktop`, and the share of frame points matched
    there. A rough pass with a few hundred points finds candidates; every point decides."""
    pts = np.array(json.loads(FRAME_FILE.read_text()), dtype=np.int32)
    H, W = desktop.shape[:2]
    x1, y1 = W - CANVAS_W, H - CANVAS_H
    if x1 < 0 or y1 < 0:
        return None, 0.0
    img = desktop[..., :3].astype(np.int16)

    rough = pts[::max(1, len(pts) // sample)]
    hits = np.zeros((y1 + 1, x1 + 1), np.int32)
    for dx, dy, r, g, b in rough:
        win = img[dy:y1 + dy + 1, dx:x1 + dx + 1]
        hits += ((np.abs(win[..., 0] - r) <= FRAME_TOL) & (np.abs(win[..., 1] - g) <= FRAME_TOL)
                 & (np.abs(win[..., 2] - b) <= FRAME_TOL))
    share = hits / len(rough)
    best, best_share = None, 0.0
    for y, x in zip(*np.nonzero(share >= share.max() - 0.1)):
        got = img[y + pts[:, 1], x + pts[:, 0]]
        s = float((np.abs(got - pts[:, 2:]) <= FRAME_TOL).all(axis=1).mean())
        if s > best_share:
            best, best_share = (int(x), int(y)), s
    return (best, best_share) if best_share >= FRAME_MIN else (None, best_share)
