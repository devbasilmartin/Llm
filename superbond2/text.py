"""Reading the game's text: the hover text at the top left of the 3D view, and right-click
menu rows.

The game writes the action in white and the thing's name in a color that says what it is:
cyan for objects, yellow for NPCs, orange for items. Those colors are picked out of the
picture, so the busy 3D view behind the text drops away, and the result is blown up and read
with Tesseract (`sudo apt install tesseract-ocr`, `pip install pytesseract`).

None of this is measured on the real client yet: `python -m superbond2 hover` reads what's
under the mouse and saves the picture it read, to tune against.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .layout import Layout, Rect

WHITE = (255, 255, 255)
KINDS = {"object": (0, 255, 255), "npc": (255, 255, 0), "item": (255, 144, 64)}
TEXT_TOL = 40
MENU_FILL = (93, 84, 71)          # a menu's background (measured by skillbot)
NOTHING = ("walk here", "cancel")
# dialogue in the chatbox (fixed mode; not measured yet): the speaker or "Select an Option" in
# dark red at the top, the words in black, "Click here to continue" in blue at the bottom
TITLE = (128, 0, 0)
INK_BLACK = (0, 0, 0)
CONTINUE = (0, 0, 255)
TITLE_BAND = 20             # pixels at the top of the chatbox where the title goes
LINE_GAP = 3                # blank pixel rows that end a line of text


@dataclass
class Hover:
    text: str                       # "Chop down Oak tree"
    name: str                       # "Oak tree"
    kind: str                       # object / npc / item / player


@dataclass
class Dialogue:
    speaker: str                    # who's talking ("" for a list of options)
    text: str                       # what they say
    options: list                   # [(option text, where to click it)] when there's a choice
    more: bool                      # "Click here to continue"


def _mask(img: np.ndarray, rgb, tol: int = TEXT_TOL) -> np.ndarray:
    return (np.abs(img[..., :3].astype(np.int16) - np.array(rgb)).max(axis=-1) <= tol)


def tesseract(img: np.ndarray) -> str:
    """One line of text from a black-on-white picture."""
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError("reading text needs Tesseract: sudo apt install tesseract-ocr, "
                           "then pip install pytesseract") from None
    return pytesseract.image_to_string(img, config="--psm 7").strip()


class Reader:
    def __init__(self, layout: Layout = Layout(), ocr=tesseract):
        self.layout, self.ocr = layout, ocr
        self._seen: dict[bytes, str] = {}       # text pictures already read (a survey sees
                                                # "Walk here" over and over)

    def prepare(self, crop: np.ndarray) -> tuple[np.ndarray, str | None]:
        """The text pixels as black on white, 4x bigger; and the kind the name's color says."""
        counts = {k: int(_mask(crop, rgb).sum()) for k, rgb in KINDS.items()}
        kind = max(counts, key=counts.get) if max(counts.values()) >= 6 else None
        text = _mask(crop, WHITE)
        for rgb in KINDS.values():
            text |= _mask(crop, rgb)
        out = np.where(text, 0, 255).astype(np.uint8)
        return cv2.resize(out, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST), kind

    def read(self, img: np.ndarray, rect: Rect) -> tuple[str, str | None]:
        pic, kind = self.prepare(rect.crop(img))
        if (pic == 0).sum() < 20:
            return "", None
        key = pic.tobytes()
        if key not in self._seen:
            if len(self._seen) > 500:
                self._seen.clear()
            self._seen[key] = " ".join(self.ocr(pic).split())
        return self._seen[key], kind

    def read_ink(self, img: np.ndarray, rect: Rect, rgb, tol: int = 30) -> str:
        """The text drawn in one color inside `rect`, black on white, 4x bigger."""
        ink = _mask(rect.crop(img), rgb, tol)
        if ink.sum() < 20:
            return ""
        pic = cv2.resize(np.where(ink, 0, 255).astype(np.uint8), None, fx=4, fy=4,
                         interpolation=cv2.INTER_NEAREST)
        key = pic.tobytes()
        if key not in self._seen:
            self._seen[key] = " ".join(self.ocr(pic).split())
        return self._seen[key]

    def dialogue(self, img: np.ndarray) -> Dialogue | None:
        """The dialogue in the chatbox: who, what, the options or the continue line."""
        box = self.layout.chatbox
        top = Rect(box.x, box.y, box.w, TITLE_BAND)
        title = self.read_ink(img, top, TITLE)
        if not title:
            return None
        body = Rect(box.x, box.y + TITLE_BAND, box.w, box.h - TITLE_BAND)
        ink = _mask(body.crop(img), INK_BLACK, 30).any(axis=1)
        lines, start, blank = [], None, 0
        for y, on in enumerate(list(ink) + [False] * (LINE_GAP + 1)):
            if on:
                start, blank = (y if start is None else start), 0
            elif start is not None:
                blank += 1
                if blank > LINE_GAP:
                    lines.append((start, y - blank + 1))
                    start, blank = None, 0
        texts = []
        for y0, y1 in lines:
            row = Rect(box.x, body.y + y0 - 1, box.w, y1 - y0 + 2)
            texts.append((self.read_ink(img, row, INK_BLACK), (box.x + box.w // 2, body.y + (y0 + y1) // 2)))
        more = _mask(body.crop(img), CONTINUE, 30).sum() >= 20
        if title.lower().startswith("select an option"):
            return Dialogue("", "", [(t, at) for t, at in texts if t], more)
        return Dialogue(title, " ".join(t for t, _ in texts if t), [], more)

    def hover(self, img: np.ndarray) -> Hover | None:
        """What the mouse is over, or None for nothing (Walk here)."""
        text, kind = self.read(img, self.layout.hover_text)
        text = text.split(" / ")[0].strip()              # drop "/ 2 more options"
        if not text or text.lower().startswith(NOTHING):
            return None
        return Hover(text, split_name(text), kind or "player")

    def menu(self, img: np.ndarray, point) -> list[tuple[str, tuple[int, int]]]:
        """Each row of the menu open at `point` (it opens just below the mouse), with where to
        click it."""
        lay, (x, y) = self.layout, (int(point[0]), int(point[1]))
        fill = _mask(img, MENU_FILL, 10)
        rows, i = [], 0
        while True:
            mid = y + lay.menu_header + lay.menu_row * i + lay.menu_row // 2
            if mid + 7 >= img.shape[0] or not fill[mid - 6:mid + 7, max(0, x - 3):x + 4].any():
                break
            cols = np.flatnonzero(fill[mid - 6:mid + 7].any(axis=0))
            near = cols[(cols > x - 260) & (cols < x + 260)]
            if not near.size:
                break
            text, _ = self.read(img, Rect(int(near.min()), mid - 7, int(near.max() - near.min()), 15))
            rows.append((text, (x, mid)))
            i += 1
        return rows


def split_name(text: str) -> str:
    """'Chop down Oak tree' -> 'Oak tree': the action is one word, or two for the few
    two-word ones."""
    two = ("chop down", "talk-to", "pick-up", "climb-up", "climb-down", "take-from", "net from")
    low = text.lower()
    for t in two:
        if low.startswith(t + " "):
            return text[len(t) + 1:].strip()
    return text.split(" ", 1)[1].strip() if " " in text else text
