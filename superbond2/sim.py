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
from .eyes import BANK_FILL, FRAME_FILE, SHOP_FILL
from .layout import CANVAS_H, CANVAS_W, SLOTS, Layout, Rect

PANEL = (62, 53, 41)             # the stone interface
GRASS = (54, 76, 42)
SPRITE = (140, 110, 90)          # any item or object sprite
INK = (10, 10, 10)               # the black outline every item sprite has
PLAYER = (90, 70, 160)
TICK = 0.6                       # one game tick, in seconds
GATHER_XP = {"logs": ("woodcutting", 25), "oak_logs": ("woodcutting", 37.5),
             "willow_logs": ("woodcutting", 67.5), "copper_ore": ("mining", 17.5),
             "tin_ore": ("mining", 17.5), "iron_ore": ("mining", 35)}
WEARABLE = {"bronze_sword": ("weapon", "Wield"), "bronze_scimitar": ("weapon", "Wield"),
            "iron_scimitar": ("weapon", "Wield"), "wooden_shield": ("shield", "Wield"),
            "anti_dragon_shield": ("shield", "Wield"), "bronze_full_helm": ("head", "Wear"),
            "leather_body": ("body", "Wear"), "bronze_platelegs": ("legs", "Wear"),
            "leather_boots": ("feet", "Wear"), "leather_gloves": ("hands", "Wear")}
# use one on the other: (item, item or thing) -> (what it makes, skill, XP)
LIGHT = {"logs": 40, "oak_logs": 60, "willow_logs": 90}
COOK = {"raw_shrimps": ("shrimps", 30), "raw_anchovies": ("anchovies", 30),
        "raw_trout": ("trout", 70), "raw_beef": ("cooked_meat", 30)}
VALUE = {"rune_pickaxe": 32000, "bronze_pickaxe": 1, "bronze_axe": 16, "cowhide": 1,
         "oak_logs": 20, "logs": 4}          # the game's item values, for selling (some)
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
    # npc: what they say. {node: [step, ...]}, starting at "start". A step is
    # ("say", who, text), ("choose", [(option, node), ...]), ("give", item) or ("flag", name).
    talk: dict | None = None
    options: tuple = ()          # more right-click options: ("Climb-up", "Climb-down")
    blocks: frozenset = frozenset()   # a closed door or gate: the tiles it shuts
    at: tuple | None = None      # where in the world it is (x, y, floor); None: always in view
    goes: tuple | None = None    # stairs, ladders, trapdoors: where climbing takes you
    needs: tuple = ()            # a monster that can't be killed without these items
    shop: dict | None = None     # a shopkeeper: item -> price

    def here(self, t: float) -> bool:
        return t >= self.gone_until


# what the game calls things, and their left-click option, by registry name
LABELS = {"oak_tree": ("Oak tree", "Chop down"), "tree": ("Tree", "Chop down"),
          "willow_tree": ("Willow tree", "Chop down"), "rock": ("Copper rocks", "Mine"),
          "cow": ("Cow", "Attack"), "enemy": ("Goblin", "Attack"), "bank": ("Bank booth", "Bank"),
          "other_player": ("Zezima", "Follow"), "loot": ("Cowhide", "Take")}
HOVER_KIND = {"gather": "object", "bank": "object", "static": "object", "monster": "npc", "npc": "npc",
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
        # logging in: screen is "login", "welcome" (click here to play) or "game"; with the
        # launcher, "closed" (no client), then "title" (a Play button) and "welcome"
        self.screen = "game"
        self.session_ok = True               # whether a launcher session still works
        self.accounts: dict[str, str] = {}   # username -> password the sim accepts
        self.player_name: str | None = None
        self._fields, self._field = ["", ""], None
        self._tab = "inventory"
        self.menu_open: tuple[Thing | None, list] | None = None
        self.bank_open = False               # clicking a booth opens it, like the real game
        # a dialogue in the chatbox: {"speaker", "text", "options", "more"}, or None
        self.dialogue: dict | None = None
        self.convo: tuple[Thing, str, int] | None = None   # who, which node, which step
        self.flags: set[str] = set()                        # what conversations have set
        self.quest_points = 0
        self.xp: Counter = Counter()          # skill -> XP
        self.equipment: dict[str, str] = {}   # slot -> item
        self.using: int | None = None          # "Use" picked on this slot: the next click is what on
        self.cooking: str | None = None        # raw food waiting on "how many?" (space: all)
        self.coins = 0                         # the stack in the "coins" slot
        self.shop_open: Thing | None = None
        self.pos = [3222, 3218, 0]           # where he stands: x, y (north), floor
        self.walk_to: tuple[int, int] | None = None         # the tile a minimap click aimed at
        self.path: list = []                                # the tiles on the way there
        self.walls: set[tuple[int, int]] = set()            # tiles nobody can walk through
        self._frame = np.array(json.loads(FRAME_FILE.read_text()), dtype=np.int32)

    # --- setting up a scene ---------------------------------------------------------------
    def add(self, name: str, kind: str, x: int, y: int, w: int = 30, h: int = 40, **kw) -> Thing:
        thing = Thing(name, kind, Rect(self.layout.viewport.x + x, self.layout.viewport.y + y, w, h), **kw)
        label, verb = LABELS.get(name, (name.replace("_", " ").capitalize(), "Examine"))
        thing.label, thing.verb = thing.label or label, thing.verb or verb
        self.things.append(thing)
        return thing

    def give(self, item: str, n: int = 1, tool: bool = False) -> None:
        if item == "coins":                    # coins stack in one slot
            self.coins += n
            if "coins" not in self.inventory:
                self._put("coins")
            return
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
        lay = self.layout
        dx, dy = pt[0] - lay.minimap_center[0], pt[1] - lay.minimap_center[1]
        if dx * dx + dy * dy <= lay.minimap_radius ** 2:     # the minimap: walk there (north up)
            self.doing, self.bank_open = None, False
            self.walk_to = (self.pos[0] + round(dx / lay.minimap_tile),
                            self.pos[1] - round(dy / lay.minimap_tile))
            self.path = self._route(tuple(self.pos[:2]), self.walk_to)
            return
        if self.bank_open:                  # with quantity "All": a slot banks all of that item
            slot = self.layout.slot_at(pt)
            item = self.inventory[slot] if slot is not None else None
            if item is not None:
                self.bank[item] += self.inventory.count(item)
                self.inventory = [None if s == item else s for s in self.inventory]
            return
        for name, at in self.layout.tabs.items():
            if abs(pt[0] - at[0]) <= 12 and abs(pt[1] - at[1]) <= 12:
                self._tab = name
                return
        if self._tab == "logout" and abs(pt[0] - self.layout.logout_button[0]) <= 40 and \
                abs(pt[1] - self.layout.logout_button[1]) <= 12:
            self.screen, self.doing, self._tab = "login", None, "inventory"
            return
        if self._tab == "equipment":         # the panel shows what he wears, not the bag
            for where, at in self.layout.equipment_slots.items():
                if abs(pt[0] - at[0]) <= 14 and abs(pt[1] - at[1]) <= 14 and where in self.equipment:
                    if self._put(self.equipment[where]):
                        del self.equipment[where]
            return
        slot = self.layout.slot_at(pt)
        if self.using is not None:
            first, self.using = self.inventory[self.using], None
            target = self.inventory[slot] if slot is not None else \
                next((t.label.lower() for t in self.things if self._visible(t) and t.box.grow(2).contains(pt)), None)
            return self._combine(first, target)
        if slot is not None:
            return self._click_slot(slot, shift)
        if not self.layout.viewport.contains(pt):
            return
        for thing in self.things:
            if self._visible(thing) and thing.box.grow(2).contains(pt):
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
        if self.convo is not None and k != "esc":
            return self._dialogue_key(k)
        if self.cooking is not None and k == "space":     # "how many?": all of them
            return self._cook_all()
        if self.dialogue is not None and k == "space":     # a line on its own: gone
            self.dialogue = None
            return
        if k == "esc":
            self.doing, self.bank_open, self.shop_open = None, False, None

    def advance(self, seconds: float) -> None:
        """Let the world run: gathering, fighting, respawns, one tick at a time."""
        end = self.t + seconds
        while self._last_tick + TICK <= end + 1e-9:
            self._last_tick += TICK
            self.t = self._last_tick
            self._tick()
        self.t = end

    NEAR = 15                            # tiles: how far things stay in view

    def _visible(self, thing: Thing) -> bool:
        if not thing.here(self.t):
            return False
        if thing.at is None:
            return True
        x, y, floor = thing.at
        return floor == self.pos[2] and max(abs(x - self.pos[0]), abs(y - self.pos[1])) <= self.NEAR

    # --- hovering and right-click menus -------------------------------------------------
    def _under(self, pt) -> Thing | None:
        if not self.layout.viewport.contains(pt):
            return None
        for thing in self.things:
            if self._visible(thing) and thing.box.grow(2).contains(pt):
                return thing
        return None

    def hover(self, pt):
        from .text import Hover
        shop_i = self._shop_slot_at(pt) if self.screen == "game" else None
        if shop_i is not None:
            label = list(self.shop_open.shop)[shop_i].replace("_", " ").capitalize()
            return Hover(f"Value {label}", label, "item")
        slot = self.layout.slot_at(pt) if self.screen == "game" else None
        if slot is not None and self.inventory[slot] is not None:     # an item: "Use Garlic"
            label = self.inventory[slot].replace("_", " ").capitalize()
            return Hover(f"Use {label}", label, "item")
        thing = self._under(pt) if self.screen == "game" else None
        if thing is None:
            return None
        return Hover(f"{thing.verb} {thing.label}", thing.label, HOVER_KIND.get(thing.kind, "object"))

    def open_menu(self, pt, shift: bool = False) -> list:
        lay = self.layout

        def rows_for(options):
            return [(o, (int(pt[0]), int(pt[1]) + lay.menu_header + lay.menu_row * i + lay.menu_row // 2))
                    for i, o in enumerate(options)]
        shop_i = self._shop_slot_at(pt)
        if shop_i is not None:
            item = list(self.shop_open.shop)[shop_i]
            label = item.replace("_", " ").capitalize()
            rows = rows_for([f"Value {label}"] + [f"Buy {n} {label}" for n in (1, 5, 10, 50)] +
                            [f"Examine {label}"])
            self.menu_open = (("shop", item), rows)
            return rows
        slot = self.layout.slot_at(pt) if self._tab == "inventory" else None
        if slot is not None and self.shop_open is not None and self.inventory[slot] is not None:
            label = self.inventory[slot].replace("_", " ").capitalize()
            rows = rows_for([f"Value {label}"] + [f"Sell {n} {label}" for n in (1, 5, 10, 50)] +
                            [f"Examine {label}"])
            self.menu_open = (("sell", slot), rows)
            return rows
        if slot is not None and self.inventory[slot] is not None:
            item = self.inventory[slot]
            label = item.replace("_", " ").capitalize()
            verb = WEARABLE[item][1] if item in WEARABLE else "Use"
            options = [f"{verb} {label}"] + (["Use"] if item in WEARABLE else []) + \
                [f"Drop {label}", f"Examine {label}", "Cancel"]
            lay = self.layout
            rows = [(o, (int(pt[0]), int(pt[1]) + lay.menu_header + lay.menu_row * i + lay.menu_row // 2))
                    for i, o in enumerate(options)]
            self.menu_open = (("slot", slot), rows)
            return rows
        thing = self._under(pt)
        options = ["Walk here", "Cancel"]
        if thing is not None:
            options = [f"{thing.verb} {thing.label}"] + [f"{o} {thing.label}" for o in thing.options] + \
                ["Walk here", f"Examine {thing.label}", "Cancel"]
            if thing.shop:
                options.insert(1, f"Trade {thing.label}")
            if shift and HOVER_KIND.get(thing.kind) == "object":
                options.insert(1, "Unmark object" if thing.marked else "Mark object")
        lay = self.layout
        rows = [(o, (int(pt[0]), int(pt[1]) + lay.menu_header + lay.menu_row * i + lay.menu_row // 2))
                for i, o in enumerate(options)]
        self.menu_open = (thing, rows)
        return rows

    # --- dialogue -------------------------------------------------------------------------
    PARCHMENT = (194, 178, 145)          # the chatbox's background while someone talks
    LINE = 16                            # pixels per line of dialogue text

    def _route(self, start, goal, reach: int = 40) -> list:
        """The way the game walks you: around walls, to the clicked tile, or as close to it as
        it can get (searching a box `reach` tiles around where you stand)."""
        from collections import deque
        sx, sy = start
        came = {start: None}
        todo = deque([start])
        best = start
        def far(t):
            return max(abs(t[0] - goal[0]), abs(t[1] - goal[1]))
        while todo:
            t = todo.popleft()
            if far(t) < far(best):
                best = t
            if t == goal:
                break
            for ddx in (-1, 0, 1):
                for ddy in (-1, 0, 1):
                    n = (t[0] + ddx, t[1] + ddy)
                    if n in came or n in self.walls or abs(n[0] - sx) > reach or abs(n[1] - sy) > reach:
                        continue
                    if ddx and ddy and ((t[0] + ddx, t[1]) in self.walls or (t[0], t[1] + ddy) in self.walls):
                        continue                            # no cutting corners through walls
                    came[n] = t
                    todo.append(n)
        path = []
        while best != start:
            path.append(best)
            best = came[best]
        return path[::-1]

    def _use(self, thing: Thing, option: str) -> None:
        """Doors, gates, stairs and ladders."""
        self.doing = None
        if option == "Open":
            self.walls -= thing.blocks
            thing.verb = "Close"
        elif option == "Close":
            self.walls |= thing.blocks
            thing.verb = "Open"
        elif option in ("Climb-up", "Climb", "Climb-down", "Enter") and thing.goes:
            self.pos[:] = list(thing.goes)
            self.walk_to, self.path = None, []
        elif option in ("Climb-up", "Climb"):
            self.pos[2] += 1
        elif option == "Climb-down":
            self.pos[2] = max(0, self.pos[2] - 1)
        elif option == "Search" and thing.gives and thing.hp == 0:
            if self._put(thing.gives):
                thing.hp = 1                                # searched: found it once

    def _talk(self, thing: Thing, node: str, i: int) -> None:
        """Run the conversation from (node, i): effects happen on the way, and it stops at the
        next thing to say or choose (or ends)."""
        steps = thing.talk.get(node, [])
        while i < len(steps):
            step = steps[i]
            if step[0] == "give":
                self._put(step[1])
            elif step[0] == "flag":
                self.flags.add(step[1])
            elif step[0] == "take" and step[1] == "coins":
                self._pay(step[2] if len(step) > 2 else 1)
            elif step[0] == "take":
                if step[1] in self.inventory:
                    self.inventory[self.inventory.index(step[1])] = None
            elif step[0] == "need" and step[1] not in self.inventory:
                node, steps, i = step[2], thing.talk[step[2]], 0     # haven't got it: go there
                continue
            elif step[0] == "if" and step[1] in self.flags:
                node, steps, i = step[2], thing.talk[step[2]], 0     # already done that
                continue
            elif step[0] == "qp":
                self.quest_points += step[1]
            elif step[0] == "say":
                self.convo = (thing, node, i)
                self.dialogue = {"speaker": step[1], "text": step[2], "more": True}
                return
            elif step[0] == "choose":
                self.convo = (thing, node, i)
                self.dialogue = {"options": [o for o, _ in step[1]]}
                return
            i += 1
        self.convo, self.dialogue = None, None

    def _dialogue_key(self, k: str) -> None:
        thing, node, i = self.convo
        step = thing.talk[node][i]
        if step[0] == "say" and k == "space":
            self._talk(thing, node, i + 1)
        elif step[0] == "choose" and k.isdigit() and 1 <= int(k) <= len(step[1]):
            self._talk(thing, step[1][int(k) - 1][1], 0)

    def _dialogue_lines(self) -> list[str]:
        d = self.dialogue
        if d.get("options"):
            return list(d["options"])
        words, lines, line = d["text"].split(), [], ""
        for w in words:                                  # wrap like the chatbox does
            if len(line) + len(w) + 1 > 60 and line:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        return lines + [line] if line else lines

    def _line_center(self, i: int) -> tuple[int, int]:
        from .text import TITLE_BAND
        box = self.layout.chatbox
        return box.x + box.w // 2, box.y + TITLE_BAND + 10 + i * self.LINE

    def read_dialogue(self):
        """What the dialogue says, the way the eyes would read it."""
        from .text import Dialogue
        d = self.dialogue
        if d is None:
            return None
        if d.get("options"):
            return Dialogue("", "", [(o, self._line_center(i)) for i, o in enumerate(d["options"])],
                            False)
        return Dialogue(d["speaker"], d["text"], [], bool(d.get("more")))

    def _draw_dialogue(self, img) -> None:
        from .text import CONTINUE, INK_BLACK, TITLE
        box, d = self.layout.chatbox, self.dialogue
        img[box.y:box.y + box.h, box.x:box.x + box.w] = self.PARCHMENT
        title = "Select an Option" if d.get("options") else d["speaker"]
        w = 7 * len(title)
        cx = box.x + box.w // 2
        img[box.y + 5:box.y + 13, cx - w // 2:cx + w // 2] = TITLE
        for i, line in enumerate(self._dialogue_lines()[:5]):
            x, y = self._line_center(i)
            w = min(box.w - 20, 6 * len(line))
            img[y - 4:y + 4, x - w // 2:x + w // 2] = INK_BLACK
        if d.get("more"):
            img[box.y + box.h - 14:box.y + box.h - 6, cx - 70:cx + 70] = CONTINUE

    def _choose(self, pt) -> None:
        thing, rows = self.menu_open
        self.menu_open = None
        option = next((o for o, at in rows if abs(at[1] - pt[1]) <= 7 and abs(at[0] - pt[0]) <= 100), None)
        if isinstance(thing, tuple) and thing[0] in ("shop", "sell"):
            words = (option or "").split(" ")
            if len(words) > 1 and words[0] in ("Buy", "Sell") and words[1].isdigit():
                (self._buy if words[0] == "Buy" else self._sell)(thing[1], int(words[1]))
            return
        if isinstance(thing, tuple) and thing[0] == "slot":     # an item's menu
            if option == "Use" or (option and option.startswith("Use ")):
                self.using = thing[1]
            elif option and option.split(" ")[0] in ("Wield", "Wear"):
                self._wear(thing[1])
            elif option and option.startswith("Drop"):
                self.inventory[thing[1]] = None
            return
        if option is None or thing is None:
            return
        if option == "Mark object":
            thing.marked, thing.name = True, "marked"
        elif option == "Unmark object":
            thing.marked = False
        elif option.startswith(thing.verb):
            self._click_thing(thing)
        elif option.startswith("Trade") and thing.shop:
            self.shop_open, self.doing = thing, None
        elif option.split(" ")[0] in thing.options:
            self._use(thing, option.split(" ")[0])

    def type_text(self, text: str) -> None:
        if self.screen == "login" and self._field is not None:
            self._fields[self._field] += text

    def _click_login(self, pt) -> None:
        lay = self.layout
        if self.screen == "login" and abs(pt[0] - lay.login_existing_user[0]) <= 60 and \
                abs(pt[1] - lay.login_existing_user[1]) <= 15:
            self._field = 0
        elif self.screen == "title" and self.session_ok and \
                abs(pt[0] - lay.login_launcher_play[0]) <= 60 and \
                abs(pt[1] - lay.login_launcher_play[1]) <= 15:
            self.screen = "welcome"
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
        elif item in WEARABLE:                 # left-click wields or wears
            self._wear(i)
        elif item in FOOD:
            self.inventory[i] = None
            self.hp = min(self.max_hp, self.hp + FOOD[item])

    def _pay(self, n: int) -> bool:
        if self.coins < n:
            return False
        self.coins -= n
        if self.coins == 0 and "coins" in self.inventory:
            self.inventory[self.inventory.index("coins")] = None
        return True

    # --- shops ------------------------------------------------------------------------------
    def shop_slot(self, i: int) -> Rect:
        lay = self.layout
        x = lay.viewport.x + lay.shop_origin[0] + (i % lay.shop_cols) * lay.shop_step[0]
        y = lay.viewport.y + lay.shop_origin[1] + (i // lay.shop_cols) * lay.shop_step[1]
        return Rect(x, y, 32, 32)

    def _shop_slot_at(self, pt) -> int | None:
        if self.shop_open is None:
            return None
        for i in range(len(self.shop_open.shop)):
            if self.shop_slot(i).contains(pt):
                return i
        return None

    def _buy(self, item: str, n: int) -> None:
        price = self.shop_open.shop[item]
        for _ in range(n):
            if None not in self.inventory or not self._pay(price):
                return
            self._put(item)

    def _sell(self, slot: int, n: int) -> None:
        item = self.inventory[slot]
        price = max(1, int(self.shop_open.shop.get(item, VALUE.get(item, 2)) * 0.4))
        for _ in range(n):
            if item not in self.inventory:
                return
            self.inventory[self.inventory.index(item)] = None
            self.give("coins", price)

    def _combine(self, first, target) -> None:
        pair = {first, target}
        if "tinderbox" in pair and pair - {"tinderbox"} and (pair - {"tinderbox"}).pop() in LIGHT:
            logs = (pair - {"tinderbox"}).pop()
            self.inventory[self.inventory.index(logs)] = None
            self.xp["firemaking"] += LIGHT[logs]
            self.add("door", "static", 240, 190, 20, 20, label="Fire", verb="Examine", marked=False,
                     at=tuple(self.pos), respawn=60)
        elif first in COOK and target in ("fire", "range"):
            self.cooking = first
            self.dialogue = {"speaker": "Cooking", "text": "How many would you like to cook? "
                             "(space: all)", "more": False}

    def _cook_all(self) -> None:
        made, xp = COOK[self.cooking]
        for i, item in enumerate(self.inventory):
            if item == self.cooking:
                self.inventory[i] = made
                self.xp["cooking"] += xp
        self.cooking, self.dialogue = None, None

    def _wear(self, i: int) -> None:
        item = self.inventory[i]
        where = WEARABLE[item][0]
        self.inventory[i] = self.equipment.get(where)       # what was worn goes in the bag
        self.equipment[where] = item

    def read_equipment(self) -> dict[str, str]:
        return dict(self.equipment)

    def _click_thing(self, thing: Thing) -> None:
        if thing.kind == "bank":
            self.doing, self.bank_open = None, True
        elif thing.kind == "static":
            self._use(thing, thing.verb)
        elif thing.kind == "npc" and thing.talk:
            self.doing = None
            self._talk(thing, "start", 0)
        elif thing.kind == "loot":
            if self._put(thing.gives):
                self.things.remove(thing)
        elif thing.kind in ("gather", "monster"):
            if self.doing is not thing:
                self.doing = thing
                self._next_action = self.t + 4 * TICK

    def _tick(self) -> None:
        if self.walk_to is not None:                        # a tile a tick, along the route
            if self.path:
                self.pos[0], self.pos[1] = self.path.pop(0)
            if not self.path:
                self.walk_to = None
        thing = self.doing
        if thing is not None and not self._visible(thing):
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
            skill, xp = GATHER_XP.get(thing.gives, (None, 0))
            if skill:
                self.xp[skill] += xp
            if self.rng.random() < thing.deplete:
                thing.gone_until = self.t + thing.respawn
                self.doing = None
            elif None not in self.inventory:
                self.doing = None

    def levels(self) -> dict[str, int]:
        from .levels import level_for_xp, starting_levels
        out = starting_levels()
        out["hitpoints"] = max(10, level_for_xp(self.xp["hitpoints"] + 1154))
        for skill, xp in self.xp.items():
            if skill != "hitpoints":
                out[skill] = level_for_xp(xp)
        return out

    def _fight(self, thing: Thing) -> None:
        hit = self.rng.randint(0, 3)
        thing.hp -= hit
        self.xp["attack"] += 4 * hit
        self.xp["hitpoints"] += 1.33 * hit
        if thing.hp <= 0 and thing.needs and not all(n in self.inventory for n in thing.needs):
            thing.hp = 25                                   # rises again: it needs more than that
            self.dialogue = {"speaker": thing.label, "text": "You can't kill me like that, mortal!",
                             "more": False}
        elif thing.hp <= 0 and thing.needs:
            self.doing, thing.gone_until = None, 1e12     # gone for good
            self._quest_done(thing)
            return
        if thing.hp <= 0:
            thing.gone_until = self.t + thing.respawn
            thing.hp = 8
            self.doing = None
            if thing.gives:
                x, y = thing.box.x - self.layout.viewport.x, thing.box.y - self.layout.viewport.y
                loot = self.add("loot", "loot", x + 5, y + thing.box.h - 12, 18, 10, gives=thing.gives)
                loot.at = thing.at
            return
        self.hp -= self.rng.randint(0, 2)
        if self.hp <= 0:                                  # dead: respawn with nothing
            self.deaths += 1
            self.hp, self.doing = self.max_hp, None
            self.inventory = [None] * SLOTS

    def _quest_done(self, thing: Thing) -> None:
        """A quest boss beaten: whatever its script says happens then."""
        if thing.talk and "defeated" in thing.talk:
            self._talk(thing, "defeated", 0)

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
        if self.shop_open is not None:
            img[vp.y + 4:vp.y + vp.h - 4, vp.x + 4:vp.x + vp.w - 4] = SHOP_FILL
            for i in range(len(self.shop_open.shop)):
                r = self.shop_slot(i)
                img[r.y + 6:r.y + r.h - 6, r.x + 6:r.x + r.w - 6] = SPRITE
        elif self.bank_open:                         # the bank window covers the 3D view
            img[vp.y + 4:vp.y + vp.h - 4, vp.x + 4:vp.x + vp.w - 4] = BANK_FILL
        else:
            for thing in self.things:
                if self._visible(thing):
                    self._draw_thing(img, thing)
            self._draw_player(img)
        for i, item in enumerate(self.inventory):
            if item is not None:
                self._draw_item(img, i, item)
        self._draw_hp(img)
        if self.dialogue is not None:
            self._draw_dialogue(img)
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
