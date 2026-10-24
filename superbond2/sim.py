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
    label: str = ""              # its name in the game ("Oak tree")
    verb: str = ""               # its left-click option ("Chop down")
    marked: bool = True          # outlined (marked by the owner, or by him); unmarked ones aren't

    def here(self, t: float) -> bool:
        return t >= self.gone_until


# what the game calls things, and their left-click option, by registry name
LABELS = {"oak_tree": ("Oak tree", "Chop down"), "tree": ("Tree", "Chop down"),
          "willow_tree": ("Willow tree", "Chop down"), "rock": ("Copper rocks", "Mine"),
          "cow": ("Cow", "Attack"), "enemy": ("Goblin", "Attack"), "bank": ("Bank booth", "Bank"),
          "other_player": ("Zezima", "Follow"), "loot": ("Cowhide", "Take")}
HOVER_KIND = {"gather": "object", "bank": "object", "static": "object", "monster": "npc",
              "loot": "item", "player": "player"}


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
        self._last_tick = 0.0                # the world moves on ticks; time in between
        # logging in: screen is "login", "welcome" (click here to play) or "game"
        self.screen = "game"
        self.accounts: dict[str, str] = {}   # username -> password the sim accepts
        self.player_name: str | None = None
        self._fields, self._field = ["", ""], None
        self._tab = "inventory"
        self.menu_open: tuple[Thing | None, list] | None = None
        self._frame = np.array(json.loads(FRAME_FILE.read_text()), dtype=np.int32)

    # --- setting up a scene ---------------------------------------------------------------
    def add(self, name: str, kind: str, x: int, y: int, w: int = 30, h: int = 40, **kw) -> Thing:
        thing = Thing(name, kind, Rect(self.layout.viewport.x + x, self.layout.viewport.y + y, w, h), **kw)
        label, verb = LABELS.get(name, (name.replace("_", " ").capitalize(), "Examine"))
        thing.label, thing.verb = thing.label or label, thing.verb or verb
        self.things.append(thing)
        return thing

    def give(self, item: str, n: int = 1, tool: bool = False) -> None:
        if tool:
            self.tools.add(item)
        for _ in range(n):
            self._put(item)

    # --- input: the same things the hands do ----------------------------------------------
    def click(self, pt, shift: bool = False) -> None:
        if self.screen != "game":
            return self._click_login(pt)
        if self.menu_open is not None:
            return self._choose(pt)
        for name, at in self.layout.tabs.items():
            if abs(pt[0] - at[0]) <= 12 and abs(pt[1] - at[1]) <= 12:
                self._tab = name
                return
        if self._tab == "logout" and abs(pt[0] - self.layout.logout_button[0]) <= 40 and \
                abs(pt[1] - self.layout.logout_button[1]) <= 12:
            self.screen, self.doing, self._tab = "login", None, "inventory"
            return
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
        if self.screen == "login" and self._field is not None:
            if k == "tab":
                self._field = 1 - self._field
            elif k == "backspace":
                self._fields[self._field] = self._fields[self._field][:-1]
            elif k == "enter":
                user, password = self._fields
                if self.accounts.get(user) == password:
                    self.screen, self.player_name = "welcome", user
                self._fields, self._field = ["", ""], None
            return
        if k == "esc":
            self.doing = None

    def advance(self, seconds: float) -> None:
        """Let the world run: gathering, fighting, respawns, one tick at a time."""
        end = self.t + seconds
        while self._last_tick + TICK <= end + 1e-9:
            self._last_tick += TICK
            self.t = self._last_tick
            self._tick()
        self.t = end

    # --- hovering and right-click menus -------------------------------------------------
    def _under(self, pt) -> Thing | None:
        if not self.layout.viewport.contains(pt):
            return None
        for thing in self.things:
            if thing.here(self.t) and thing.box.grow(2).contains(pt):
                return thing
        return None

    def hover(self, pt):
        from .text import Hover
        thing = self._under(pt) if self.screen == "game" else None
        if thing is None:
            return None
        return Hover(f"{thing.verb} {thing.label}", thing.label, HOVER_KIND.get(thing.kind, "object"))

    def open_menu(self, pt, shift: bool = False) -> list:
        thing = self._under(pt)
        options = ["Walk here", "Cancel"]
        if thing is not None:
            options = [f"{thing.verb} {thing.label}", "Walk here", f"Examine {thing.label}", "Cancel"]
            if shift and HOVER_KIND.get(thing.kind) == "object":
                options.insert(1, "Unmark object" if thing.marked else "Mark object")
        lay = self.layout
        rows = [(o, (int(pt[0]), int(pt[1]) + lay.menu_header + lay.menu_row * i + lay.menu_row // 2))
                for i, o in enumerate(options)]
        self.menu_open = (thing, rows)
        return rows

    def _choose(self, pt) -> None:
        thing, rows = self.menu_open
        self.menu_open = None
        option = next((o for o, at in rows if abs(at[1] - pt[1]) <= 7 and abs(at[0] - pt[0]) <= 100), None)
        if option is None or thing is None:
            return
        if option == "Mark object":
            thing.marked, thing.name = True, "marked"
        elif option == "Unmark object":
            thing.marked = False
        elif option.startswith(thing.verb):
            self._click_thing(thing)

    def type_text(self, text: str) -> None:
        if self.screen == "login" and self._field is not None:
            self._fields[self._field] += text

    def _click_login(self, pt) -> None:
        lay = self.layout
        if self.screen == "login" and abs(pt[0] - lay.login_existing_user[0]) <= 60 and \
                abs(pt[1] - lay.login_existing_user[1]) <= 15:
            self._field = 0
        elif self.screen == "welcome" and abs(pt[0] - lay.login_play[0]) <= 80 and \
                abs(pt[1] - lay.login_play[1]) <= 20:
            self.screen = "game"

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
        if self.screen != "game":                     # the login screen: no stone frame
            img = np.full((CANVAS_H, CANVAS_W, 3), (20, 20, 20), np.uint8)
            if self.screen == "welcome":
                img[300:350, 300:470] = (120, 20, 20)  # the red "click here to play"
            return img
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
        if thing.marked:
            _outline(img, b, self.registry[thing.name].rgb, 2)

    def _draw_player(self, img) -> None:
        px, py = self.layout.player
        img[py - 12:py + 12, px - 6:px + 6] = PLAYER
        if self.doing is not None:                # swing: the arm and tool sweep down
            dy = int(-16 + 24 * (self.t % 1.8) / 1.8)            # smoothly, once per 3 ticks
            img[py + dy:py + dy + 12, px + 6:px + 18] = SPRITE

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
    """A starter scene: two oaks, a tree, a copper rock, a cow, the bank, another player, all
    marked; and, not marked, a willow, a door and a man."""
    g = SimGame(seed=seed)
    g.add("oak_tree", "gather", 60, 40, gives="oak_logs", deplete=0.15, respawn=12)
    g.add("oak_tree", "gather", 140, 30, gives="oak_logs", deplete=0.15, respawn=12)
    g.add("tree", "gather", 380, 50, gives="logs", deplete=0.3, respawn=8)
    g.add("rock", "gather", 400, 230, 26, 22, gives="copper_ore", deplete=1.0, respawn=4)
    g.add("cow", "monster", 90, 220, 44, 30, gives="cowhide", hp=8, respawn=15)
    g.add("bank", "bank", 300, 260, 40, 40)
    g.add("other_player", "player", 200, 110, 14, 30)
    g.add("willow_tree", "gather", 230, 40, gives="willow_logs", deplete=0.1, respawn=12, marked=False)
    g.add("door", "static", 470, 140, 20, 34, label="Door", verb="Open", marked=False)
    g.add("enemy", "monster", 20, 140, 14, 30, label="Man", verb="Attack", gives="bones", hp=6,
          respawn=10, marked=False)
    g.give("bronze_axe", tool=True)
    g.give("trout", 3)
    return g
