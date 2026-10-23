"""A tiny simulated RuneScape, drawn the way RuneLite draws the real one.

It exists so superbond2 can be built and tested without the client. The eyes read its
pictures exactly as they read real screenshots: the same fixed-mode frame, highlight
outlines in the registry's colors, Inventory Tags, the Status Bars health bar. The hands
will drive it with the same clicks and keys they send to the real game.

What it has: things to gather (trees, rocks, fishing spots), monsters that fight back and
drop loot, a bank, food, shift-click dropping, other players, and dying. What it doesn't:
walking (clicking something gets you there), menus, dialogs, the bank interface (clicking
the bank deposits everything except your tools), levels. Those come as superbond2 needs them.
"""
from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .colors import Registry
from .eyes import FRAME_FILE
from .layout import CANVAS_H, CANVAS_W, SLOTS, Layout, Rect

PANEL = (62, 53, 41)             # the stone interface
GRASS = (54, 76, 42)
SPRITE = (140, 110, 90)          # any item or object sprite
INK = (10, 10, 10)               # the black outline every item sprite has
PLAYER = (90, 70, 160)
TICK = 0.6                       # one game tick, in seconds
FOOD = {"trout": 7, "shrimps": 3, "lobster": 12, "cooked_meat": 3}


@dataclass
class Thing:
    """Something in the 3D view: a tree, a rock, a cow, the bank."""
    name: str                    # its highlight color's name in the registry
    kind: str                    # gather / monster / bank / loot / player
    box: Rect
    gives: str | None = None     # gather: the item; monster: its drop; loot: the item
    deplete: float = 0.0         # gather: chance of running out per item
    hp: int = 0                  # monster
    respawn: float = 10.0
    gone_until: float = 0.0      # depleted, dead or picked up until then

    def here(self, t: float) -> bool:
        return t >= self.gone_until


class SimGame:
    def __init__(self, registry: Registry | None = None, layout: Layout = Layout(),
                 hp: int = 40, seed: int = 1):
        self.registry = registry or Registry.load()
        self.layout = layout
        self.rng = random.Random(seed)
        self.t = 0.0
        self.max_hp = self.hp = hp
        self.things: list[Thing] = []
        self.inventory: list[str | None] = [None] * SLOTS
        self.bank: Counter = Counter()
        self.tools: set[str] = set()         # items the bank never takes (untagged in RuneLite)
        self.doing: Thing | None = None      # what the player is chopping/mining/fighting
        self.deaths = 0
        self._next_action = 0.0
        self._frame = np.array(json.loads(FRAME_FILE.read_text()), dtype=np.int32)

    # --- setting up a scene ---------------------------------------------------------------
    def add(self, name: str, kind: str, x: int, y: int, w: int = 30, h: int = 40, **kw) -> Thing:
        thing = Thing(name, kind, Rect(self.layout.viewport.x + x, self.layout.viewport.y + y, w, h), **kw)
        self.things.append(thing)
        return thing

    def give(self, item: str, n: int = 1, tool: bool = False) -> None:
        if tool:
            self.tools.add(item)
        for _ in range(n):
            self._put(item)

    # --- input: the same things the hands do ----------------------------------------------
    def click(self, pt, shift: bool = False) -> None:
        slot = self.layout.slot_at(pt)
        if slot is not None:
            return self._click_slot(slot, shift)
        if not self.layout.viewport.contains(pt):
            return
        for thing in self.things:
            if thing.here(self.t) and thing.box.grow(2).contains(pt):
                return self._click_thing(thing)
        self.doing = None                     # clicked the ground: walk there, stop working

    def key(self, k: str) -> None:
        if k == "esc":
            self.doing = None

    def advance(self, seconds: float) -> None:
        """Let the world run: gathering, fighting, respawns, one tick at a time."""
        end = self.t + seconds
        while self.t + TICK <= end + 1e-9:
            self.t += TICK
            self._tick()
        self.t = end

    # --- what happens ---------------------------------------------------------------------
    def _put(self, item: str) -> bool:
        for i, s in enumerate(self.inventory):
            if s is None:
                self.inventory[i] = item
                return True
        return False

    def _click_slot(self, i: int, shift: bool) -> None:
        item = self.inventory[i]
        if item is None:
            return
        if shift:                              # shift-click drop
            self.inventory[i] = None
        elif item in FOOD:
            self.inventory[i] = None
            self.hp = min(self.max_hp, self.hp + FOOD[item])

    def _click_thing(self, thing: Thing) -> None:
        if thing.kind == "bank":
            self.doing = None
            for i, s in enumerate(self.inventory):
                if s is not None and s not in self.tools:
                    self.bank[s] += 1
                    self.inventory[i] = None
        elif thing.kind == "loot":
            if self._put(thing.gives):
                self.things.remove(thing)
        elif thing.kind in ("gather", "monster"):
            if self.doing is not thing:
                self.doing = thing
                self._next_action = self.t + 4 * TICK

    def _tick(self) -> None:
        thing = self.doing
        if thing is not None and not thing.here(self.t):
            thing = self.doing = None                    # someone else got it / it ran out
        if thing is not None and self.t >= self._next_action - 1e-9:
            self._next_action = self.t + 4 * TICK
            if thing.kind == "gather":
                self._gather(thing)
            else:
                self._fight(thing)

    def _gather(self, thing: Thing) -> None:
        if None not in self.inventory:
            self.doing = None
            return
        if self.rng.random() < 0.5:
            self._put(thing.gives)
            if self.rng.random() < thing.deplete:
                thing.gone_until = self.t + thing.respawn
                self.doing = None
            elif None not in self.inventory:
                self.doing = None

    def _fight(self, thing: Thing) -> None:
        thing.hp -= self.rng.randint(0, 3)
        if thing.hp <= 0:
            thing.gone_until = self.t + thing.respawn
            thing.hp = 8
            self.doing = None
            if thing.gives:
                x, y = thing.box.x - self.layout.viewport.x, thing.box.y - self.layout.viewport.y
                self.add("loot", "loot", x + 5, y + thing.box.h - 12, 18, 10, gives=thing.gives)
            return
        self.hp -= self.rng.randint(0, 2)
        if self.hp <= 0:                                  # dead: respawn with nothing
            self.deaths += 1
            self.hp, self.doing = self.max_hp, None
            self.inventory = [None] * SLOTS

    # --- drawing --------------------------------------------------------------------------
    def grab(self) -> np.ndarray:
        img = np.full((CANVAS_H, CANVAS_W, 3), PANEL, np.uint8)
        pts = self._frame
        img[pts[:, 1], pts[:, 0]] = pts[:, 2:]
        vp = self.layout.viewport
        img[vp.y + 4:vp.y + vp.h - 4, vp.x + 4:vp.x + vp.w - 4] = GRASS
        for thing in self.things:
            if thing.here(self.t):
                self._draw_thing(img, thing)
        self._draw_player(img)
        for i, item in enumerate(self.inventory):
            if item is not None:
                self._draw_item(img, i, item)
        self._draw_hp(img)
        return img

    def _draw_thing(self, img, thing: Thing) -> None:
        b = thing.box
        img[b.y + 2:b.y + b.h - 2, b.x + 2:b.x + b.w - 2] = SPRITE
        _outline(img, b, self.registry[thing.name].rgb, 2)

    def _draw_player(self, img) -> None:
        px, py = self.layout.player
        img[py - 12:py + 12, px - 6:px + 6] = PLAYER
        if self.doing is not None:                # swing: the arm and tool move every tick,
            dy = (-16, -6, 4)[int(round(self.t / TICK)) % 3]   # 3 steps, so looks 2 ticks
            img[py + dy:py + dy + 12, px + 6:px + 18] = SPRITE   # apart still differ

    def _draw_item(self, img, i: int, item: str) -> None:
        s = self.layout.slot(i)
        inner = Rect(s.x + 6, s.y + 6, s.w - 12, s.h - 12)
        img[inner.y:inner.y + inner.h, inner.x:inner.x + inner.w] = SPRITE
        _outline(img, inner, INK, 1)
        rgb = self.registry.items().get(item)
        if rgb is not None and item not in self.tools:
            _outline(img, inner.grow(1), rgb, 1)

    def _draw_hp(self, img) -> None:
        bar = self.layout.hp_bar
        filled = round(bar.h * max(self.hp, 0) / self.max_hp)
        img[bar.y + bar.h - filled:bar.y + bar.h, bar.x:bar.x + bar.w] = self.registry["status_hp"].rgb


def _outline(img, r: Rect, rgb, width: int) -> None:
    for k in range(width):
        img[r.y + k, r.x:r.x + r.w] = rgb
        img[r.y + r.h - 1 - k, r.x:r.x + r.w] = rgb
        img[r.y:r.y + r.h, r.x + k] = rgb
        img[r.y:r.y + r.h, r.x + r.w - 1 - k] = rgb


def lumbridge(seed: int = 1) -> SimGame:
    """A starter scene: two oaks, a tree, a copper rock, a cow, the bank, another player."""
    g = SimGame(seed=seed)
    g.add("oak_tree", "gather", 60, 40, gives="oak_logs", deplete=0.15, respawn=12)
    g.add("oak_tree", "gather", 140, 30, gives="oak_logs", deplete=0.15, respawn=12)
    g.add("tree", "gather", 380, 50, gives="logs", deplete=0.3, respawn=8)
    g.add("rock", "gather", 400, 230, 26, 22, gives="copper_ore", deplete=1.0, respawn=4)
    g.add("cow", "monster", 90, 220, 44, 30, gives="cowhide", hp=8, respawn=15)
    g.add("bank", "bank", 300, 260, 40, 40)
    g.add("other_player", "player", 200, 110, 14, 30)
    g.give("bronze_axe", tool=True)
    g.give("trout", 3)
    return g
