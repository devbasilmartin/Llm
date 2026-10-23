"""superbond2's eyes: one screenshot of the game canvas in, a View of what's going on out.

Everything comes from what RuneLite draws: highlight outlines in known colors (Object
Markers, NPC Indicators, Ground Items, Player Indicators), Inventory Tags, the Status Bars
health bar, and the fixed-mode frame around the 3D view. Untagged items show up as
"untagged": the eyes can see something is there, not what it is.

describe() turns a View into the short text the brain reads each turn.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .colors import Registry
from .layout import SLOTS, Layout, Rect

FRAME_FILE = Path(__file__).resolve().parent / "fixed_frame.json"
UNTAGGED = "untagged"


def color_mask(img: np.ndarray, rgb, tol: int) -> np.ndarray:
    diff = np.abs(img[..., :3].astype(np.int16) - np.asarray(rgb, dtype=np.int16))
    return np.all(diff <= tol, axis=-1)


def find_blobs(img: np.ndarray, rgb, tol: int, region: Rect, min_pixels: int = 15) -> list[Rect]:
    """Boxes around each group of pixels in `rgb` inside `region`, biggest first.

    Highlights are thin outlines, possibly broken, so the mask is thickened to group the
    pieces of one outline; the box is then taken from the real pixels, not the thickened
    ones."""
    mask = color_mask(region.crop(img), rgb, tol)
    joined = cv2.dilate(mask.astype(np.uint8), np.ones((7, 7), np.uint8))
    n, labels = cv2.connectedComponents(joined, connectivity=8)
    found = []
    for i in range(1, n):
        ys, xs = np.nonzero((labels == i) & mask)
        if len(xs) >= min_pixels:
            x, y = int(xs.min()), int(ys.min())
            box = Rect(x + region.x, y + region.y, int(xs.max()) - x + 1, int(ys.max()) - y + 1)
            found.append((len(xs), box))
    return [r for _, r in sorted(found, key=lambda f: -f[0])]


@dataclass(frozen=True)
class Highlight:
    name: str                   # the registry name, e.g. "oak_tree"
    category: str               # resource, bank, enemy, loot, other...
    box: Rect
    distance: int               # pixels from the player

    @property
    def center(self) -> tuple[int, int]:
        return self.box.center


@dataclass
class View:
    in_game: bool                       # the fixed-mode frame is where it should be
    highlights: list[Highlight] = field(default_factory=list)
    inventory: list[str | None] = field(default_factory=lambda: [None] * SLOTS)
    hp: float | None = None             # 0..1 from the health bar; None when it isn't drawn
    busy: bool | None = None            # the player moved since the last look; None on the first

    def nearest(self, name: str) -> Highlight | None:
        hits = [h for h in self.highlights if h.name == name]
        return min(hits, key=lambda h: h.distance) if hits else None

    def count(self, name: str) -> int:
        return sum(h.name == name for h in self.highlights)

    @property
    def free_slots(self) -> int:
        return sum(s is None for s in self.inventory)

    def items(self) -> Counter:
        return Counter(s for s in self.inventory if s is not None)

    def slots_with(self, item: str) -> list[int]:
        return [i for i, s in enumerate(self.inventory) if s == item]


class Eyes:
    def __init__(self, registry: Registry | None = None, layout: Layout = Layout(),
                 area: str = "default", world_tolerance: int = 25, item_tolerance: int = 8):
        self.registry = registry or Registry.load()
        self.layout = layout
        self.area = area
        self.world_tol = world_tolerance
        self.item_tol = item_tolerance
        self.items = self.registry.items()
        self.frame = np.array(json.loads(FRAME_FILE.read_text()), dtype=np.int32)
        self.hp_color = self.registry["status_hp"].rgb
        self._last_player = None

    def look(self, img: np.ndarray) -> View:
        view = View(in_game=self.in_game(img))
        if not view.in_game:
            self._last_player = None
            return view
        view.highlights = self.highlights(img)
        view.inventory = [self.slot(img, i) for i in range(SLOTS)]
        view.hp = self.hp(img)
        view.busy = self.busy(img)
        return view

    # --- the pieces ---------------------------------------------------------------------
    def in_game(self, img: np.ndarray, tol: int = 12, need: float = 0.85) -> bool:
        """The stone frame around the 3D view matches the real client's (logged in, fixed
        mode, canvas where we think it is). The login screen has no frame."""
        pts = self.frame
        got = img[pts[:, 1], pts[:, 0], :3].astype(np.int16)
        return float((np.abs(got - pts[:, 2:]) <= tol).all(axis=1).mean()) >= need

    def highlights(self, img: np.ndarray) -> list[Highlight]:
        px, py = self.layout.player
        out = []
        for c in self.registry.world(self.area):
            for box in find_blobs(img, c.rgb, self.world_tol, self.layout.viewport):
                cx, cy = box.center
                out.append(Highlight(c.name, c.category, box, int(np.hypot(cx - px, cy - py))))
        return sorted(out, key=lambda h: h.distance)

    def slot(self, img: np.ndarray, i: int, min_pixels: int = 6) -> str | None:
        """The tagged item in slot i, UNTAGGED for an item without a tag, None when empty.

        Tag outlines hug the sprite and can poke a pixel or two out of the slot. An empty
        slot is flat panel with none of the black outline every item sprite has (measured
        by skillbot: empty slots have std ~2 and no dark pixels, items 50+)."""
        s = self.layout.slot(i)
        area = s.grow(2).crop(img)
        best, best_n = None, min_pixels - 1
        for name, rgb in self.items.items():
            n = int(color_mask(area, rgb, self.item_tol).sum())
            if n > best_n:
                best, best_n = name, n
        if best:
            return best
        a = s.crop(img)[..., :3]
        flat = int((a.max(axis=-1) < 30).sum()) < 4 and float(a.std(axis=(0, 1)).mean()) < 8
        return None if flat else UNTAGGED

    def hp(self, img: np.ndarray) -> float | None:
        """How full the Status Bars health bar is. It fills from the bottom and RuneLite
        draws it half see-through, so any clearly red pixel counts; a gap of a few rows is
        a tick line, a longer one is the top of the fill."""
        crop = self.layout.hp_bar.crop(img)
        rgb = crop[..., :3].astype(np.int16)
        red = (rgb[..., 0] >= 90) & (rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2]) >= 50)
        rows = (red | color_mask(crop, self.hp_color, self.world_tol)).any(axis=1)
        if not rows.any():
            return None
        top, gap = len(rows), 0
        for i in range(len(rows) - 1, -1, -1):
            if rows[i]:
                top, gap = i, 0
            else:
                gap += 1
                if gap > 3:
                    break
        return (len(rows) - top) / len(rows)

    def busy(self, img: np.ndarray, radius: int = 20, share: float = 0.03) -> bool | None:
        """Did the player's character change since the last look? Chopping, mining, fighting
        and walking all animate; standing idle doesn't. Counts pixels that clearly changed,
        so faint flicker doesn't count. Not checked on the real client yet."""
        px, py = self.layout.player
        crop = img[py - radius:py + radius, px - radius:px + radius, :3].astype(np.int16)
        last, self._last_player = self._last_player, crop
        if last is None:
            return None
        changed = (np.abs(crop - last) > 30).any(axis=-1)
        return float(changed.mean()) > share


def _near(px: int) -> str:
    return "right next to you" if px < 60 else "close" if px < 150 else "far"


def describe(view: View, registry: Registry | None = None) -> str:
    """The View as the short text lines the brain reads."""
    if not view.in_game:
        return "Screen: not in the game (login screen, loading, or the client moved)"
    lines = []
    if view.hp is not None:
        lines.append(f"HP: {round(view.hp * 100)}%")
    if view.busy is not None:
        lines.append("You are: " + ("busy (your character is doing something)" if view.busy
                                    else "idle"))
    used = sum(view.items().values())
    things = ", ".join(f"{n} {name.replace('_', ' ')}" for name, n in view.items().most_common())
    lines.append(f"Inventory: {used}/{SLOTS}" + (f": {things}" if things else " (empty)"))
    seen = {}
    for h in view.highlights:                       # nearest first
        seen.setdefault(h.name, []).append(h)
    if seen:
        parts = [f"{len(hs)} {name.replace('_', ' ')} ({_near(hs[0].distance)})"
                 for name, hs in seen.items()]
        lines.append("Highlighted nearby: " + "; ".join(parts))
    else:
        lines.append("Highlighted nearby: nothing")
    return "\n".join(lines)
