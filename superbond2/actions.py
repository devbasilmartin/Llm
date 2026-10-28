"""The things superbond2 can do, one game-level action at a time.

Each action looks, acts, looks again, and reports what changed ("you're busy now; +1 oak
logs"). That report is how he finds out whether something worked: it goes back to the
brain, and into his notebook when it teaches him something. An action that can't be done
(nothing with that name in sight) says so instead of raising, so a mistake costs a turn,
not a crash. Only the kill switch (Stopped) gets through.

ACTIONS describes them for the brain, in the same tool format the bake-off uses.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import heartbeat
from .eyes import UNTAGGED, Eyes, View
from .hands import KEYS, Body
from .layout import SLOTS

SETTLE = 1.2           # seconds to let a click take effect before looking again (2 ticks)
GLANCE = 0.3           # the two pictures of one look are this far apart


@dataclass
class Result:
    ok: bool
    said: str               # what happened, in words for the brain

    def __str__(self) -> str:
        return self.said


def as_name(text) -> str:
    """'Oak logs' -> 'oak_logs': reports say names with spaces, the game data uses _."""
    return "_".join(str(text).lower().split())


SELL_GUARD = 1000           # coins: worth more than this, a shop sale needs sure=yes
PLACES_FILE = Path(__file__).resolve().parent / "places.yaml"
ARRIVED = 2                 # tiles from a place that count as there
WALK_STEP = 14              # tiles per minimap click (the minimap shows about 17 each way)
MAX_WALK_STEPS = 60


def load_places() -> dict[str, tuple[int, int, int]]:
    raw = yaml.safe_load(PLACES_FILE.read_text()) or {}
    return {str(k).lower(): tuple(v) for k, v in raw.items()}


def places_for(name: str) -> list[str]:
    """Places on the list named after someone or something ("Morgan" -> "morgan's house")."""
    words = [w for w in str(name).lower().replace("_", " ").split() if len(w) >= 4]
    return [p for p in load_places() if any(w in p for w in words)]


def not_here(name: str, seen: list[str]) -> str:
    """'no X in sight', with what is in sight and, if there is one, a place named after X."""
    hint = places_for(name)
    return (f"no {name} in sight (I can see: {', '.join(seen) or 'nothing'})" +
            (f". There's a place by that name: walk_to {hint[0]}" if hint else
             ". Not everything nearby shows: survey, or walk closer"))


def died(before: View, after: View) -> bool:
    """A death, from two looks: HP was low and is full again (you respawn at full), and most
    of what he carried is gone (you keep only 3 items)."""
    if before.hp is None or after.hp is None or not (before.in_game and after.in_game):
        return False
    had, has = sum(before.items().values()), sum(after.items().values())
    return before.hp < 0.4 and after.hp > 0.9 and had >= 4 and has <= max(3, had // 2)


def changes(before: View, after: View) -> str:
    """What's different between two looks, in words."""
    if not after.in_game:
        return "the game is no longer on screen"
    parts = []
    if after.busy and not before.busy:
        parts.append("you're busy now")
    elif before.busy and after.busy is False:
        parts.append("you're idle now")
    diff = Counter(after.items())
    diff.subtract(before.items())
    for item, n in sorted(diff.items()):
        if n:
            parts.append(f"{n:+d} {item.replace('_', ' ')}")
    if before.hp is not None and after.hp is not None and abs(after.hp - before.hp) >= 0.02:
        parts.append(f"HP {round(before.hp * 100)}% -> {round(after.hp * 100)}%")
    gone = Counter(h.name for h in before.highlights) - Counter(h.name for h in after.highlights)
    new = Counter(h.name for h in after.highlights) - Counter(h.name for h in before.highlights)
    parts += [f"{n} {name.replace('_', ' ')} gone" for name, n in gone.items()]
    parts += [f"{n} {name.replace('_', ' ')} appeared" for name, n in new.items()]
    return "; ".join(parts) or "nothing changed"


class Actions:
    def __init__(self, body: Body, eyes: Eyes):
        self.body, self.eyes = body, eyes
        self.keep: set[str] = set()         # never banked: his reflex food (the brain sets it)
        self.deaths: list[list[str]] = []   # each death noticed: what he lost
        self._untagged: dict[int, str] = {}  # slot -> the name of the untagged item there
        self.wearing: dict[str, str] = {}    # equipment slot -> item, as last read
        self.value_of = lambda item: None    # an item's value (the brain gives it the wiki's)
        self.ge_price_of = lambda item: None  # the real game's GE price (the wiki's), if known
        self.look()

    def look(self) -> View:
        """A fresh View, from two pictures a moment apart: if the character moved between
        them, he's busy. Comparing with an older look could land on the same frame of a
        repeating animation (a swing every few ticks) and call a busy character idle."""
        heartbeat.beat()
        first = self.body.grab()
        self.body.wait(GLANCE)
        last, self.view = getattr(self, "view", None), self.eyes.look(self.body.grab(), before=first)
        self._name_untagged(self.view)
        if hasattr(self.body, "position"):
            self.view.position = self.body.position()
        if hasattr(self.body, "read_quest_helper"):
            self.view.helper = self.body.read_quest_helper()
        if self.view.dialogue_open and hasattr(self.body, "read_dialogue"):
            self.view.dialogue = self.body.read_dialogue()
        if last is not None and died(last, self.view):
            self.deaths.append(sorted((last.items() - self.view.items()).elements()))
        return self.view

    def _name_untagged(self, view: View) -> None:
        """Items with no Inventory Tags color (tools, quest items) get their name from the
        hover text, read once per slot ("Use Garlic") until the slot changes."""
        for i, item in enumerate(view.inventory):
            if item != UNTAGGED:
                self._untagged.pop(i, None)
                continue
            if i not in self._untagged:
                h = self.body.read_hover(self.eyes.layout.slot(i).center) \
                    if hasattr(self.body, "read_hover") else None
                self._untagged[i] = as_name(h.name) if h is not None and h.kind == "item" else ""
            if self._untagged[i]:
                view.inventory[i] = self._untagged[i]

    def _after(self, before: View, did: str, settle: float = SETTLE) -> Result:
        """Look again after acting, and say what changed since `before`: the last look
        reported, so a change that happened between two actions (or while he was
        thinking) is reported once instead of falling through the gap."""
        self.body.wait(settle)
        after = self.look()
        return Result(True, f"{did}: {changes(before, after)}")

    # --- the actions ----------------------------------------------------------------------
    def click_nearest(self, name: str) -> Result:
        """Click the nearest highlight called `name` (a tree, a cow, the bank, loot...)."""
        name = as_name(name)
        before, now = self.view, self.look()
        target = now.nearest(name)
        if target is None:
            seen = sorted({h.name for h in now.highlights})
            return Result(False, f"no {name} in sight (I can see: {', '.join(seen) or 'nothing'})")
        self.body.click(target.center)
        result = self._after(before, f"clicked the nearest {name}")
        if self.view.bank_open:
            result.said += " (the bank is open: bank puts things away, press esc closes it)"
        return result

    def click_item(self, item: str) -> Result:
        """Click the first inventory slot holding `item` (eat it, bury it, use it...)."""
        item = as_name(item)
        before, now = self.view, self.look()
        slots = now.slots_with(item)
        if not slots:
            return Result(False, f"no {item} in the inventory")
        self.body.click(self.eyes.layout.slot(slots[0]).center)
        return self._after(before, f"clicked {item}")

    def click_slot(self, slot: int) -> Result:
        """Click inventory slot 0-27 (left to right, top to bottom), whatever is in it."""
        if not 0 <= slot < SLOTS:
            return Result(False, f"there's no slot {slot}; slots are 0-{SLOTS - 1}")
        before = self.view
        self.body.click(self.eyes.layout.slot(slot).center)
        return self._after(before, f"clicked slot {slot}")

    def drop_all(self, item: str) -> Result:
        """Shift-click every slot holding `item` (needs RuneLite's shift-click drop)."""
        item = as_name(item)
        before, now = self.view, self.look()
        slots = now.slots_with(item)
        if not slots:
            return Result(False, f"no {item} in the inventory")
        for i in slots:
            self.body.click(self.eyes.layout.slot(i).center, shift=True)
            self.body.wait(0.15)
        return self._after(before, f"dropped {len(slots)} {item}", settle=0.6)

    def press(self, key: str) -> Result:
        """Press one key: space, esc, enter or 1-5 (dialogs, menus, closing things)."""
        if key not in KEYS:
            return Result(False, f"I can only press: {', '.join(sorted(KEYS))}")
        before = self.view
        self.body.key(key)
        return self._after(before, f"pressed {key}", settle=0.6)

    # --- exploring: finding things that aren't highlighted, and marking them ---------------
    def _direction(self, pt) -> str:
        px, py = self.eyes.layout.player
        dx, dy = pt[0] - px, pt[1] - py
        side = "left" if dx < -60 else "right" if dx > 60 else ""
        depth = "ahead" if dy < -40 else "behind" if dy > 40 else ""
        where = " ".join(w for w in (depth, side) if w) or "right here"
        far = "far " if (dx * dx + dy * dy) ** 0.5 > 180 else ""
        return far + where

    def survey(self) -> Result:
        """Hover over the whole 3D view and read what's there, highlighted or not. This is how
        you find things you can't see yet: then mark them."""
        view = self.look()
        vp = self.eyes.layout.viewport
        found: dict[str, list] = {}
        cols, rows = 21, 13                     # about 24 px apart, every other row shifted
        step_x, step_y = (vp.w - 24) / (cols - 1), (vp.h - 24) / (rows - 1)   # by half a step,
        for gy in range(rows):                                                # so even narrow
            shift = step_x / 2 if gy % 2 else 0                               # things get hit
            for gx in range(cols - (1 if gy % 2 else 0)):
                pt = (int(vp.x + 12 + shift + gx * step_x), int(vp.y + 12 + gy * step_y))
                h = self.body.read_hover(pt)
                if h is not None:
                    spots = found.setdefault(h.name, [])
                    if not any(abs(pt[0] - q[0]) < 60 and abs(pt[1] - q[1]) < 45 for q, _ in spots):
                        spots.append((pt, h))
        if hasattr(self.body, "close_menu"):
            self.body.close_menu()
        self.surveyed = found
        if not found:
            return Result(True, "surveyed: nothing here but ground")
        parts = []
        for name, spots in sorted(found.items(), key=lambda kv: kv[1][0][1].kind):
            lit = [h.name for h in view.highlights if any(h.box.grow(4).contains(p) for p, _ in spots)]
            seen = f", highlighted as {lit[0]}" if lit else ""
            where = ", ".join(self._direction(p) for p, _ in spots[:3])
            parts.append(f"{name} ({spots[0][1].kind}, {where}{seen})")
        return Result(True, "surveyed: " + "; ".join(parts) +
                      ". mark <name> outlines an object for good.")

    def inspect(self, name: str) -> Result:
        """Hover over the nearest highlight called `name` and read what it really is (a
        `rock` might be Copper rocks; a `marked` one, whatever you marked)."""
        name = as_name(name)
        target = self.look().nearest(name)
        if target is None:
            return Result(False, f"no {name} in sight")
        h = self.body.read_hover(target.center)
        if h is None:
            return Result(False, f"couldn't read what that {name} is")
        return Result(True, f"that {name} is {h.name} ({h.text})")

    def mark(self, name: str) -> Result:
        """Outline an object you found with survey, for good: Object Markers (shift +
        right-click, Mark object). It shows as `marked` from then on."""
        found = getattr(self, "surveyed", {})
        key = next((k for k in found if k.lower() == str(name).strip().lower()), None) or \
            next((k for k in found if str(name).strip().lower() in k.lower()), None)
        if key is None:
            return Result(False, f"no {name} in your last survey; survey first"
                          + (f" (it found: {', '.join(found)})" if found else ""))
        before = self.view
        px, py = self.eyes.layout.player
        for pt, _ in sorted(found[key], key=lambda s: (s[0][0] - px) ** 2 + (s[0][1] - py) ** 2):
            now = self.body.read_hover(pt)
            if now is None or now.name != key:
                continue                        # moved, or it was chopped down
            if now.kind != "object":
                return Result(False, f"{key} is an {now.kind}; only objects can be marked")
            rows = self.body.open_menu(pt, shift=True)
            texts = [t.lower() for t, _ in rows]
            if any(t.startswith("unmark") for t in texts):
                self.body.close_menu()
                return Result(False, f"that {key} is already marked")
            row = next((at for t, at in rows if t.lower().startswith("mark")), None)
            if row is None:
                self.body.close_menu()
                return Result(False, "the menu has no Mark object (is RuneLite's Object Markers "
                              "plugin on?)")
            self.body.click(row)
            result = self._after(before, f"marked the {key}", settle=0.6)
            lit = any(hl.name == "marked" and hl.box.grow(6).contains(pt) for hl in self.view.highlights)
            result.said += "; it shows as `marked` now" if lit else \
                "; but no `marked` outline showed up (is Object Markers' color #80F8D0?)"
            result.ok = lit
            return result
        return Result(False, f"no {key} where your survey saw it anymore; survey again")

    def bank(self, keep: str = "") -> Result:
        """Open the nearest bank and put away everything but your tools and your food (and
        anything in `keep`), then close it. Needs the bank's quantity set to All."""
        before, now = self.view, self.look()
        if not now.bank_open:
            target = now.nearest("bank")
            if target is None:
                seen = sorted({h.name for h in now.highlights})
                return Result(False, f"no bank in sight (I can see: {', '.join(seen) or 'nothing'})")
            self.body.click(target.center)
            for _ in range(10):                      # walking there, then the window
                self.body.wait(0.6)
                if self.look().bank_open:
                    break
            else:
                return Result(False, "clicked the bank, but it didn't open")
        kept = {as_name(k) for k in str(keep or "").split(",") if k.strip()} | self.keep | \
            {n for n in self._untagged.values() if n}      # tools and quest items stay
        banked = []
        for i, item in enumerate(self.view.inventory):
            if item is None or item == UNTAGGED or item in kept or item in banked:
                continue
            self.body.click(self.eyes.layout.slot(i).center)
            self.body.wait(0.6)
            banked.append(item)
        self.body.key("esc")
        held = sorted({i for i in self.view.inventory if i and i != UNTAGGED and i in kept
                       and i not in self._untagged.values()})
        did = ("banked " + ", ".join(b.replace("_", " ") for b in banked) if banked else
               "nothing to bank") + (f" (kept {', '.join(h.replace('_', ' ') for h in held)})"
                                     if held else "")
        return self._after(before, did)

    # --- using one thing on another ---------------------------------------------------------
    def use(self, item: str, on: str = "") -> Result:
        """Use an item on another item or on something nearby: a tinderbox on logs (lights a
        fire), raw fish on a fire or range (cooks all of it), a knife on logs..."""
        if not on:                                       # a routine step: "tinderbox on logs"
            item, _, on = str(item).partition(" on ")
        item, before = as_name(item), self.view
        now = self.look()
        slots = now.slots_with(item)
        if not slots:
            return Result(False, f"no {item} in your inventory")
        pt = None
        others = [i for i in now.slots_with(as_name(on)) if i != slots[0]]
        if others:
            pt = self.eyes.layout.slot(others[0]).center
        elif now.nearest(as_name(on)) is not None:
            pt = now.nearest(as_name(on)).center
        else:
            want = str(on).strip().lower()
            for name, spots in getattr(self, "surveyed", {}).items():
                if name.lower() == want:
                    pt = spots[0][0]
                    break
        if pt is None:
            return Result(False, f"no {on} to use it on (in your inventory, highlighted, or in your "
                                 "last survey)")
        rows = self.body.open_menu(self.eyes.layout.slot(slots[0]).center)
        row = next(((t, at) for t, at in rows if t.lower() == "use" or t.lower().startswith("use ")), None)
        if row is None:
            self.body.close_menu()
            return Result(False, f"{item} can't be used on things (its menu: {', '.join(t for t, _ in rows)})")
        self.body.click(row[1])
        self.body.wait(0.3)
        self.body.click(pt)
        self.body.wait(1.2)
        view = self.look()
        if view.dialogue is not None and not view.dialogue.options and \
                any(w in view.dialogue.text.lower() for w in ("how many", "would you like")):
            self.body.key("space")                       # make all of them
            self.wait_until_idle(60)
        return self._after(before, f"used {item.replace('_', ' ')} on {on}", settle=0.6)

    # --- shops ----------------------------------------------------------------------------------
    def trade(self, name: str) -> Result:
        """Open someone's shop (Trade from their right-click menu): a highlight name or their name."""
        now = self.look()
        target = now.nearest(as_name(name))
        if target is None:
            for h in sorted(now.highlights, key=lambda h: h.distance):
                hover = self.body.read_hover(h.center)
                if hover is not None and hover.name.lower() == str(name).strip().lower():
                    target = h
                    break
        if target is None:
            return Result(False, f"no {name} in sight")
        rows = self.body.open_menu(target.center)
        row = next(((t, at) for t, at in rows if t.lower().startswith("trade")), None)
        if row is None:
            self.body.close_menu()
            return Result(False, f"{name} doesn't run a shop (the menu: {', '.join(t for t, _ in rows)})")
        self.body.click(row[1])
        for _ in range(10):
            self.body.wait(0.6)
            if self.look().shop_open:
                return Result(True, f"{name}'s shop is open")
        return Result(False, f"clicked Trade {name}, but no shop opened")

    def _shop_items(self) -> dict[str, tuple[int, int]]:
        """What's for sale, by hovering the shop's slots ("Value Bronze pickaxe")."""
        lay, out = self.eyes.layout, {}
        for i in range(lay.shop_cols * lay.shop_rows):
            x = lay.viewport.x + lay.shop_origin[0] + (i % lay.shop_cols) * lay.shop_step[0] + 16
            y = lay.viewport.y + lay.shop_origin[1] + (i // lay.shop_cols) * lay.shop_step[1] + 16
            h = self.body.read_hover((x, y))
            if h is None:
                break
            out[as_name(h.name)] = (x, y)
        return out

    def _in_amounts(self, where, verb: str, quantity: int) -> int:
        """Buy or sell `quantity` with the menu's 1/5/10/50 options; `where` gives the point to
        right-click each time (an item moves as slots empty). Returns how many it asked for."""
        done = 0
        while done < quantity:
            pt = where()
            if pt is None:
                break
            rows = self.body.open_menu(pt)
            options = [(int(t.split(" ")[1]), at) for t, at in rows
                       if t.startswith(verb + " ") and t.split(" ")[1].isdigit()]
            fit = [(n, at) for n, at in options if n <= quantity - done]
            if not fit:
                self.body.close_menu()
                break
            n, at = max(fit)
            self.body.click(at)
            self.body.wait(0.6)
            done += n
        return done

    def buy(self, item: str, quantity: int = 1) -> Result:
        """Buy from the open shop."""
        item, before = as_name(item), self.view
        if not self.look().shop_open:
            return Result(False, "no shop is open: trade with a shopkeeper first")
        stock = self._shop_items()
        if item not in stock:
            return Result(False, f"the shop has no {item} (it sells: {', '.join(stock) or 'nothing'})")
        self._in_amounts(lambda: stock[item], "Buy", int(quantity))
        value = self.value_of(item)
        return self._after(before, f"bought {item.replace('_', ' ')}" +
                           (f" (worth about {value} coins each)" if value else ""), settle=0.3)

    def sell(self, item: str, quantity: int = 1, sure: str = "") -> Result:
        """Sell to the open shop. Shops pay little: anything worth over 1,000 coins needs sure=yes."""
        item, before = as_name(item), self.view
        now = self.look()
        if not now.shop_open:
            return Result(False, "no shop is open: trade with a shopkeeper first")
        slots = now.slots_with(item)
        if not slots:
            return Result(False, f"no {item} in your inventory")
        value = self.value_of(item)
        if value and value > SELL_GUARD and str(sure).lower() not in ("yes", "true", "sure"):
            return Result(False, f"{item.replace('_', ' ')} is worth about {value:,} coins and a shop "
                                 "pays a fraction of that: the Grand Exchange is better. If you mean "
                                 "it, sell with sure=yes")
        def where():
            left = self.look().slots_with(item)
            return self.eyes.layout.slot(left[0]).center if left else None
        self._in_amounts(where, "Sell", int(quantity))
        return self._after(before, f"sold {item.replace('_', ' ')}", settle=0.3)

    # --- fighting --------------------------------------------------------------------------------
    def attack(self, name: str, max_level: int = 0) -> Result:
        """Attack the nearest `name` (a highlight, e.g. cow or enemy), skipping any above
        max_level (their level is in the hover text). max_level 0: any."""
        import re
        name, before = as_name(name), self.view
        now = self.look()
        targets = sorted((h for h in now.highlights if h.name == name), key=lambda h: h.distance)
        if not targets:
            seen = sorted({h.name for h in now.highlights})
            return Result(False, f"no {name} in sight (I can see: {', '.join(seen) or 'nothing'})")
        skipped = []
        for h in targets:
            hover = self.body.read_hover(h.center)
            m = re.search(r"\(level-(\d+)\)", hover.name) if hover else None
            level = int(m[1]) if m else None
            if max_level and level is not None and level > int(max_level):
                skipped.append(level)
                continue
            self.body.click(h.center)
            who = hover.name if hover else name
            return self._after(before, f"attacking {who}")
        return Result(False, f"every {name} in sight is over level {max_level} (levels {', '.join(map(str, skipped))})")

    def pick_up(self, item: str = "") -> Result:
        """Pick up loot from the ground: `item` (e.g. bones), or the nearest loot of any kind."""
        want, before = as_name(item) if item else "", self.view
        now = self.look()
        for h in sorted((h for h in now.highlights if h.name == "loot"), key=lambda h: h.distance):
            hover = self.body.read_hover(h.center)
            if want and (hover is None or as_name(hover.name) != want):
                continue
            self.body.click(h.center)
            return self._after(before, f"picked up {hover.name if hover else 'the loot'}")
        return Result(False, f"no {item or 'loot'} on the ground in sight")

    def set_style(self, style: str) -> Result:
        """Which skill fighting trains: attack, strength or defence (the Combat tab)."""
        style = str(style).strip().lower()
        lay = self.eyes.layout
        if style not in lay.combat_styles:
            return Result(False, f"a style is one of: {', '.join(lay.combat_styles)}")
        self.body.click(lay.tabs["combat"])
        self.body.wait(0.6)
        self.body.click(lay.combat_styles[style])
        self.body.wait(0.3)
        self.body.click(lay.tabs["inventory"])
        return Result(True, f"fighting now trains {style}")

    # --- the Grand Exchange ---------------------------------------------------------------------
    def _ge(self) -> Result | None:
        """Open the Grand Exchange through a clerk, if it isn't open; None when it's open."""
        if self.look().ge_open:
            return None
        now = self.view
        for h in sorted(now.highlights, key=lambda h: h.distance):
            rows = self.body.open_menu(h.center)
            row = next(((t, at) for t, at in rows if t.lower().startswith("exchange")), None)
            if row is None:
                self.body.close_menu()
                continue
            self.body.click(row[1])
            for _ in range(10):
                self.body.wait(0.6)
                if self.look().ge_open:
                    return None
        return Result(False, "no Grand Exchange clerk in sight (walk_to grand exchange first)")

    def _price_check(self, kind: str, item: str, price: int, sure: str) -> str | None:
        if str(sure).lower() in ("yes", "true", "sure"):
            return None
        value, ge = self.value_of(item), self.ge_price_of(item)
        name = item.replace("_", " ")
        if kind == "sell" and value and price < int(value * 0.6):
            return (f"{price:,} each is under {name}'s high alchemy value ({int(value * 0.6):,}): "
                    "alching would get more. If you mean it, sure=yes")
        if ge and kind == "sell" and price < ge / 3:
            return (f"{price:,} each is far under the going price (about {ge:,} in the real game; "
                    "this server's may differ). If you mean it, sure=yes")
        if ge and kind == "buy" and price > ge * 3:
            return (f"{price:,} each is far over the going price (about {ge:,} in the real game; "
                    "this server's may differ). If you mean it, sure=yes")
        return None

    def _ge_offer(self, kind: str, item: str, quantity, price, sure: str) -> Result:
        item, quantity, price = as_name(item), int(quantity), int(price)
        if quantity < 1 or price < 1:
            return Result(False, "quantity and price must be at least 1")
        why = self._price_check(kind, item, price, sure)
        if why:
            return Result(False, why)
        failed = self._ge()
        if failed:
            return failed
        slot_pt = None
        if kind == "sell":
            slots = self.view.slots_with(item)
            if not slots:
                return Result(False, f"no {item} in your inventory")
            slot_pt = self.eyes.layout.slot(slots[0]).center
        before = self.view
        why = self.body.ge_offer(kind, item, quantity, price, slot_pt)
        if why:
            return Result(False, why)
        return self._after(before, f"offered to {kind} {quantity} {item.replace('_', ' ')} at "
                                   f"{price:,} each; ge_collect when it's done", settle=0.6)

    def ge_buy(self, item: str, quantity: int, price: int, sure: str = "") -> Result:
        """Offer to buy on the Grand Exchange. Prices far over the going rate need sure=yes."""
        return self._ge_offer("buy", item, quantity, price, sure)

    def ge_sell(self, item: str, quantity: int, price: int, sure: str = "") -> Result:
        """Offer to sell on the Grand Exchange. Under high-alchemy value, or far under the going
        rate, needs sure=yes."""
        return self._ge_offer("sell", item, quantity, price, sure)

    def ge_collect(self) -> Result:
        """Collect what your Grand Exchange offers have bought or earned."""
        failed = self._ge()
        if failed:
            return failed
        before = self.view
        self.body.ge_collect()
        return self._after(before, "collected", settle=0.6)

    # --- equipment ------------------------------------------------------------------------------
    def read_wearing(self) -> dict[str, str]:
        if hasattr(self.body, "read_equipment"):
            self.wearing = self.body.read_equipment() or {}
        return self.wearing

    def _worn(self) -> str:
        return ", ".join(f"{i.replace('_', ' ')} ({w})" for w, i in self.wearing.items()) or "nothing"

    def equip(self, item: str) -> Result:
        """Wear or wield an item from your inventory (armour, a weapon, a shield)."""
        item = as_name(item)
        now = self.look()
        slots = now.slots_with(item)
        if not slots:
            return Result(False, f"no {item} in your inventory")
        rows = self.body.open_menu(self.eyes.layout.slot(slots[0]).center)
        row = next(((t, at) for t, at in rows if t.lower().split(" ")[0] in ("wield", "wear", "equip")), None)
        if row is None:
            self.body.close_menu()
            return Result(False, f"{item} isn't something to wear (its menu: {', '.join(t for t, _ in rows)})")
        self.body.click(row[1])
        self.body.wait(0.6)
        self.look()
        self.read_wearing()
        return Result(True, f"{row[0].lower()}; wearing: {self._worn()}")

    def unequip(self, item: str) -> Result:
        """Take off something you're wearing (it goes into your inventory)."""
        item = as_name(item)
        where = next((w for w, i in self.read_wearing().items() if i == item), None)
        if where is None:
            return Result(False, f"you're not wearing {item} (wearing: {self._worn()})")
        if self.view.free_slots == 0:
            return Result(False, "no room in your inventory to take it off")
        lay = self.eyes.layout
        self.body.click(lay.tabs["equipment"])
        self.body.wait(0.6)
        self.body.click(lay.equipment_slots[where])
        self.body.wait(0.6)
        self.body.click(lay.tabs["inventory"])
        self.look()
        self.read_wearing()
        return Result(True, f"took off {item.replace('_', ' ')}; wearing: {self._worn()}")

    # --- getting around -----------------------------------------------------------------------
    def walk_to(self, place: str) -> Result:
        """Walk to a named place (a bank, a town, a mine...): minimap clicks, a bit at a time."""
        places = load_places()
        want = " ".join(str(place).lower().split())
        name = want if want in places else next((p for p in places if want in p), None)
        if name is None:
            return Result(False, f"I don't know a place called {place!r}. Places: {', '.join(places)}")
        tx, ty, floor = places[name]
        here = self.body.position() if hasattr(self.body, "position") else None
        if here is None:
            return Result(False, "I can't tell where I am: RuneLite's coordinates overlay isn't "
                                 "being read yet")
        if here[2] != floor:
            return Result(False, f"{name} is on floor {floor} and you're on floor {here[2]}: "
                                 "stairs or a ladder first")
        lay = self.eyes.layout
        self.body.click(lay.compass)                    # north up, so the minimap matches the map
        start, stuck, steps = here, 0, 0
        while max(abs(tx - here[0]), abs(ty - here[1])) > ARRIVED and steps < MAX_WALK_STEPS:
            steps += 1
            dx, dy = tx - here[0], ty - here[1]
            far = (dx * dx + dy * dy) ** 0.5            # the minimap is round: a diagonal
            k = min(1.0, WALK_STEP / far)               # click can't go as far out
            pt = (lay.minimap_center[0] + round(dx * k * lay.minimap_tile),
                  lay.minimap_center[1] - round(dy * k * lay.minimap_tile))
            self.body.click(pt)
            last = here
            for _ in range(30):                          # until he stops moving
                self.body.wait(1.2)
                now = self.body.position()
                if now == last:
                    break
                last = now
            if last is None:
                return Result(False, "lost track of where I am while walking")
            stuck = stuck + 1 if max(abs(tx - last[0]), abs(ty - last[1])) >= \
                max(abs(tx - here[0]), abs(ty - here[1])) else 0
            here = last
            if stuck >= 3:
                self.look()
                return Result(False, f"stuck at {here[0]}, {here[1]}, {max(abs(tx - here[0]), abs(ty - here[1]))} "
                                     f"tiles from {name}: a wall or a door in the way? (survey for a "
                                     "door or gate, interact it with Open, and walk on)")
        self.look()
        if max(abs(tx - here[0]), abs(ty - here[1])) > ARRIVED:
            return Result(False, f"gave up walking to {name} after {steps} clicks")
        moved = max(abs(here[0] - start[0]), abs(here[1] - start[1]))
        return Result(True, f"walked to {name} ({moved} tiles)")

    def interact(self, target: str, option: str = "") -> Result:
        """Right-click something and pick an option: Open a door or gate, Climb-up or
        Climb-down stairs and ladders, and anything else its menu offers. `target` is a
        highlight name, or a name from your last survey (Door, Ladder, Staircase)."""
        if not option:                                  # a routine step: "Door Open"
            target, _, option = str(target).strip().rpartition(" ")
        before, now = self.view, self.look()
        pt = None
        hit = now.nearest(as_name(target))
        if hit is not None:
            pt = hit.center
        else:
            want = str(target).strip().lower()
            for name, spots in getattr(self, "surveyed", {}).items():
                if name.lower() == want:
                    pt = spots[0][0]
                    break
        if pt is None:
            return Result(False, f"no {target} in sight; survey to find things that aren't highlighted")
        rows = self.body.open_menu(pt)
        want = str(option).strip().lower()
        row = next(((t, at) for t, at in rows if t.lower().startswith(want)), None)
        if row is None:
            self.body.close_menu()
            return Result(False, f"{target}'s menu has no {option!r}: {', '.join(t for t, _ in rows)}")
        floor = self.body.position()[2] if hasattr(self.body, "position") and self.body.position() else None
        self.body.click(row[1])
        result = self._after(before, f"chose {row[0]}", settle=1.8)
        now_floor = self.body.position()[2] if floor is not None and self.body.position() else None
        if floor is not None and now_floor != floor:
            result.said += f"; you're on floor {now_floor} now"
        return result

    # --- talking ------------------------------------------------------------------------------
    def _said(self) -> str:
        d = self.view.dialogue
        if d is None:
            return "nobody's talking now"
        if d.options:
            return "choose one: " + "; ".join(f"{i}. {t}" for i, (t, _) in enumerate(d.options, 1))
        return f'{d.speaker}: "{d.text}"' + (" (more)" if d.more else "")

    def talk_to(self, name: str) -> Result:
        """Talk to someone: a highlight name (quest_dialog, aubury...) or their name in the
        game (Morgan), if they're highlighted."""
        now = self.look()
        target = now.nearest(as_name(name))
        if target is None:                               # their game name: hover to find them
            for h in sorted(now.highlights, key=lambda h: h.distance):
                hover = self.body.read_hover(h.center)
                if hover is not None and hover.kind == "npc" and hover.name.lower() == str(name).strip().lower():
                    target = h
                    break
        if target is None:
            return Result(False, not_here(name, sorted({h.name for h in now.highlights})))
        rows = self.body.open_menu(target.center)
        row = next(((t, at) for t, at in rows if t.lower().startswith("talk-to")), None)
        if row is None:
            self.body.close_menu()
            return Result(False, f"{name} has nothing to say (the menu: {', '.join(t for t, _ in rows)})")
        self.body.click(row[1])
        for _ in range(10):                              # walking over, then the chat
            self.body.wait(0.6)
            if self.look().dialogue_open:
                break
        else:
            return Result(False, f"clicked Talk-to {name}, but nobody spoke")
        return Result(True, f"talking to {name}: {self._said()}")

    def continue_dialogue(self, _: str = "") -> Result:
        """Go on to the next thing they say (space)."""
        if not self.look().dialogue_open:
            return Result(False, "nobody's talking")
        self.body.key("space")
        self.body.wait(0.6)
        self.look()
        return Result(True, f"next: {self._said()}")

    def choose(self, option: str) -> Result:
        """Pick a dialogue option, by its number (1-5) or its words."""
        d = self.look().dialogue
        if d is None or not d.options:
            return Result(False, "there's no choice to make right now")
        texts = [t for t, _ in d.options]
        want = str(option).strip()
        n = int(want) if want.isdigit() else next(
            (i + 1 for i, t in enumerate(texts) if t.lower() == want.lower()), None) or next(
            (i + 1 for i, t in enumerate(texts) if want.lower() in t.lower()), None)
        if n is None or not 1 <= n <= len(texts):
            return Result(False, f"no option {option!r}; the options: " +
                          "; ".join(f"{i}. {t}" for i, t in enumerate(texts, 1)))
        self.body.key(str(n))
        self.body.wait(0.6)
        self.look()
        return Result(True, f"chose {n}. {texts[n - 1]}; now {self._said()}")

    def walk_away(self) -> Result:
        """Run from the nearest monster: click open ground on the far side of the view.
        For the flee reflex; not one of his tools."""
        before, now = self.view, self.look()
        vp, (px, py) = self.eyes.layout.viewport, self.eyes.layout.player
        threats = [h for h in now.highlights if h.category in ("enemy", "danger") or h.name == "cow"]
        if threats:
            t = min(threats, key=lambda h: h.distance).center
            dx, dy = px - t[0], py - t[1]
        else:
            dx, dy = 0, 1                                # nothing to see: back the way he came
        size = max(1.0, (dx * dx + dy * dy) ** 0.5)
        for reach in (0.8, 0.6, 0.4):                    # as far as the view allows, off any highlight
            for turn in (0, 0.5, -0.5):
                ux, uy = dx / size - turn * dy / size, dy / size + turn * dx / size
                pt = (int(px + ux * vp.w / 2 * reach), int(py + uy * vp.h / 2 * reach))
                if vp.grow(-8).contains(pt) and not any(h.box.grow(6).contains(pt)
                                                         for h in now.highlights):
                    self.body.click(pt)
                    return self._after(before, f"ran {self._direction(pt)}")
        return Result(False, "nowhere clear to run to")

    def wait(self, seconds: float) -> Result:
        """Do nothing for a while (at most 60 seconds) and see what changed."""
        seconds = max(0.6, min(float(seconds), 60))
        before = self.view
        return self._after(before, f"waited {seconds:g}s", settle=seconds)

    def wait_until_idle(self, timeout: float = 60) -> Result:
        """Wait until the character stops (inventory full, tree gone, fight over)."""
        before = self.view
        waited, idle_looks = 0.0, 0
        while waited < timeout:
            self.body.wait(1.2)
            waited += 1.2
            view = self.look()
            idle_looks = idle_looks + 1 if view.busy is False else 0
            if idle_looks >= 2:            # one still frame can be between two swings
                return Result(True, f"idle after {waited:.0f}s: {changes(before, view)}")
        if self.view.busy is False:                # stopped right at the end
            return Result(True, f"idle after {waited:.0f}s: {changes(before, self.view)}")
        # still going isn't a failure: a routine just carries on with its next step
        return Result(True, f"still busy after {timeout:g}s: {changes(before, self.view)}")


def _spec(action: str, description: str, /, **params: str) -> dict:
    ints = {"slot", "seconds", "timeout", "quantity", "price", "max_level"}
    props = {p: {"type": "integer" if p in ints else "string", "description": d}
             for p, d in params.items()}
    return {"type": "function", "function": {
        "name": action, "description": description,
        "parameters": {"type": "object", "properties": props, "required": list(params)}}}


ACTIONS = [
    _spec("click_nearest", Actions.click_nearest.__doc__,
          name="A highlight name from 'Highlighted nearby', e.g. oak_tree, bank, cow, loot."),
    _spec("click_item", Actions.click_item.__doc__, item="An item name from the inventory."),
    _spec("click_slot", Actions.click_slot.__doc__, slot="Slot number, 0-27."),
    _spec("drop_all", Actions.drop_all.__doc__, item="An item name from the inventory."),
    _spec("press", Actions.press.__doc__, key="space, esc, enter, 1, 2, 3, 4 or 5."),
    _spec("wait", Actions.wait.__doc__, seconds="How long, 1-60."),
    _spec("survey", Actions.survey.__doc__),
    _spec("inspect", Actions.inspect.__doc__, name="A highlight name, e.g. rock, enemy, marked."),
    _spec("mark", Actions.mark.__doc__, name="A name from your last survey, e.g. Willow tree."),
    _spec("wait_until_idle", Actions.wait_until_idle.__doc__, timeout="Give up after this many seconds."),
    _spec("use", Actions.use.__doc__, item="An item in your inventory, e.g. tinderbox.",
          on="What to use it on: an item, a highlight or a name from your survey, e.g. logs, range, Fire."),
    _spec("trade", Actions.trade.__doc__, name="The shopkeeper, e.g. Shop keeper."),
    _spec("buy", Actions.buy.__doc__, item="What to buy.", quantity="How many."),
    {"type": "function", "function": {
        "name": "sell", "description": Actions.sell.__doc__,
        "parameters": {"type": "object", "required": ["item", "quantity"], "properties": {
            "item": {"type": "string", "description": "What to sell."},
            "quantity": {"type": "integer", "description": "How many."},
            "sure": {"type": "string", "description": "yes, to sell something valuable anyway."}}}}},
    *[{"type": "function", "function": {
        "name": n, "description": getattr(Actions, n).__doc__,
        "parameters": {"type": "object", "required": ["item", "quantity", "price"], "properties": {
            "item": {"type": "string", "description": "The item."},
            "quantity": {"type": "integer", "description": "How many."},
            "price": {"type": "integer", "description": "Coins each."},
            "sure": {"type": "string", "description": "yes, past the price guard."}}}}}
      for n in ("ge_buy", "ge_sell")],
    {"type": "function", "function": {
        "name": "ge_collect", "description": Actions.ge_collect.__doc__,
        "parameters": {"type": "object", "required": [], "properties": {}}}},
    {"type": "function", "function": {
        "name": "attack", "description": Actions.attack.__doc__,
        "parameters": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string", "description": "A highlight name, e.g. cow, enemy."},
            "max_level": {"type": "integer", "description": "Skip any above this level."}}}}},
    {"type": "function", "function": {
        "name": "pick_up", "description": Actions.pick_up.__doc__,
        "parameters": {"type": "object", "required": [], "properties": {
            "item": {"type": "string", "description": "Optional: what to pick up, e.g. bones."}}}}},
    _spec("set_style", Actions.set_style.__doc__, style="attack, strength or defence."),
    _spec("equip", Actions.equip.__doc__, item="An item in your inventory, e.g. bronze sword."),
    _spec("unequip", Actions.unequip.__doc__, item="Something you're wearing, e.g. wooden shield."),
    _spec("walk_to", Actions.walk_to.__doc__, place="A place name, e.g. draynor bank, grand exchange."),
    _spec("interact", Actions.interact.__doc__, target="A highlight name, or a name from your survey, e.g. Door.",
          option="The menu option, e.g. Open, Climb-up, Climb-down."),
    _spec("talk_to", Actions.talk_to.__doc__, name="A highlight name or the person's name, e.g. Morgan."),
    {"type": "function", "function": {
        "name": "continue_dialogue", "description": Actions.continue_dialogue.__doc__,
        "parameters": {"type": "object", "required": [], "properties": {}}}},
    _spec("choose", Actions.choose.__doc__, option="The option's number (1-5) or its words."),
    {"type": "function", "function": {
        "name": "bank", "description": Actions.bank.__doc__,
        "parameters": {"type": "object", "required": [], "properties": {
            "keep": {"type": "string", "description": "Optional: more items to keep, comma "
                                                      "separated, e.g. bronze arrows."}}}}},
]


def do(actions: Actions, name: str, args: dict) -> Result:
    """Run one action the brain asked for. A bad name or bad arguments is a failed action
    the brain hears about, not a crash."""
    if name not in {a["function"]["name"] for a in ACTIONS}:
        return Result(False, f"there's no action called {name}")
    args = {k: int(v) if k in ("slot", "seconds", "timeout", "quantity", "price", "max_level")
            and str(v).strip().isdigit() else v
            for k, v in args.items()}                  # models often send "5" for 5
    try:
        return getattr(actions, name)(**args)
    except TypeError as e:
        return Result(False, f"{name} got the wrong arguments: {e}")
    except ValueError as e:
        return Result(False, f"{name}: {e}")
