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

from .eyes import Eyes, View
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
        self.look()

    def look(self) -> View:
        """A fresh View, from two pictures a moment apart: if the character moved between
        them, he's busy. Comparing with an older look could land on the same frame of a
        repeating animation (a swing every few ticks) and call a busy character idle."""
        first = self.body.grab()
        self.body.wait(GLANCE)
        self.view = self.eyes.look(self.body.grab(), before=first)
        return self.view

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
        return self._after(before, f"clicked the nearest {name}")

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
    ints = {"slot", "seconds", "timeout"}
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
    _spec("wait_until_idle", Actions.wait_until_idle.__doc__, timeout="Give up after this many seconds."),
]


def do(actions: Actions, name: str, args: dict) -> Result:
    """Run one action the brain asked for. A bad name or bad arguments is a failed action
    the brain hears about, not a crash."""
    if name not in {a["function"]["name"] for a in ACTIONS}:
        return Result(False, f"there's no action called {name}")
    args = {k: int(v) if k in ("slot", "seconds", "timeout") and str(v).strip().isdigit() else v
            for k, v in args.items()}                  # models often send "5" for 5
    try:
        return getattr(actions, name)(**args)
    except TypeError as e:
        return Result(False, f"{name} got the wrong arguments: {e}")
    except ValueError as e:
        return Result(False, f"{name}: {e}")
