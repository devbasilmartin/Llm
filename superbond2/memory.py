"""superbond2's memory: plain files you can open and read.

    notebook.md       what he's learned, in his own words (it starts with who he is and your offer)
    notebook-archive.md  older notes, after he boiled them down into lessons
    firsts.yaml       the first time he got each item
    journal.md        his diary
    goals.yaml        the goal he's on, and the ones before it
    accounts.yaml     a line about each of his accounts ("ironman", "my main"), from the owner
    accounts/<name>/  per account: its own goals.yaml
    reflexes.yaml     when to eat, and what counts as food (his choice)
    decisions.jsonl   every turn: what he saw, what he did, what happened
    routines/         his routines (routines.py)

The model forgets everything between turns: what's written here, and the last few turns, is
all he knows. He's one player with several accounts, like a real person: what he learns,
his routines and his journal are shared; each account has its own goals.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from .routines import Library

OFFER = [
    "I'm superbond2, named after the owner's first RuneScape account from when they were a kid. "
    "I love this game.",
    "Milestones the owner suggested (all optional, my choice): Vampire Slayer, Stronghold of "
    "Security, Obor, Dragon Slayer, and one day the fire cape.",
    "The owner's deal: only Dragon Slayer earns membership. Beat Dragon Slayer and the owner "
    "upgrades me to members.",
    "I start with nothing known about the game. I can only work with what I see on screen: "
    "the highlights nearby and my inventory.",
    "The highlights come from RuneLite plugins: Object Markers outlines objects (the owner's "
    "marks in named colors, mine in `marked`), NPC Indicators outlines NPCs, Ground Items "
    "outlines loot, Player Indicators other players, Inventory Tags my items, Status Bars my HP. "
    "Quest Helper, when it's on, outlines the next step of a quest as `quest_target`.",
]
DEFAULT_REFLEXES = {"eat_below": 40, "flee_below": 25, "loot": [], "food": ["trout", "shrimps", "lobster", "cooked_meat",
                                              "anchovies", "shark", "swordfish"]}
MAX_NOTE = 300              # characters in one note
MAX_NOTES = 200


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Memory:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.notebook_file = self.folder / "notebook.md"
        self.archive_file = self.folder / "notebook-archive.md"
        self.journal_file = self.folder / "journal.md"
        self.goals_file = self.folder / "goals.yaml"
        self.reflex_file = self.folder / "reflexes.yaml"
        self.decisions_file = self.folder / "decisions.jsonl"
        self.firsts_file = self.folder / "firsts.yaml"
        self.accounts_file = self.folder / "accounts.yaml"
        self.routines = Library(self.folder / "routines")
        self.account: str | None = None
        self.levels_file = self.folder / "levels.yaml"
        self.quests_file = self.folder / "quests.yaml"
        if not self.notebook_file.exists():
            self.notebook_file.write_text("# superbond2's notebook\n\n")
            for note in OFFER:
                self.add_note(note)

    # --- notebook -------------------------------------------------------------------------
    def notes(self) -> list[str]:
        return [line[2:].strip() for line in self.notebook_file.read_text().splitlines()
                if line.startswith("- ")]

    def add_note(self, text: str) -> str:
        text = " ".join(str(text).split())[:MAX_NOTE]
        if not text:
            return "an empty note isn't kept"
        if text in self.notes():
            return "already in your notebook"
        if len(self.notes()) >= MAX_NOTES:
            return f"your notebook is full ({MAX_NOTES} notes)"
        with self.notebook_file.open("a") as f:
            f.write(f"- {text}\n")
        return "noted"

    def consolidate(self, lessons: list[str], keep_newest: int = 10) -> tuple[int, int]:
        """Replace the older notes (not the offer, not the newest few) with `lessons`; the old
        ones go to notebook-archive.md. Returns (notes replaced, lessons kept)."""
        notes = self.notes()
        head, old, new = notes[:len(OFFER)], notes[len(OFFER):-keep_newest], notes[-keep_newest:]
        lessons = list(dict.fromkeys(" ".join(str(x).split())[:MAX_NOTE] for x in lessons if str(x).strip()))
        if not old or not lessons:
            return 0, 0
        with self.archive_file.open("a") as f:
            f.write(f"## Before {_now()}\n\n" + "".join(f"- {n}\n" for n in old) + "\n")
        self.notebook_file.write_text("# superbond2's notebook\n\n" +
                                      "".join(f"- {n}\n" for n in head + lessons + new))
        return len(old), len(lessons)

    # --- accounts -------------------------------------------------------------------------
    def play_as(self, account: str | None) -> None:
        """Goals from now on are this account's."""
        self.account = account
        self.goals_file = (self.folder / "accounts" / account / "goals.yaml" if account
                           else self.folder / "goals.yaml")
        self.levels_file = self.goals_file.with_name("levels.yaml")
        self.quests_file = self.goals_file.with_name("quests.yaml")
        self.goals_file.parent.mkdir(parents=True, exist_ok=True)

    def accounts(self) -> dict[str, str]:
        """The owner's line about each account, e.g. {"iron": "ironman: no trading"}."""
        if not self.accounts_file.exists():
            return {}
        raw = yaml.safe_load(self.accounts_file.read_text()) or {}
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    # --- levels (per account) -------------------------------------------------------------
    def levels(self) -> dict[str, int]:
        return (yaml.safe_load(self.levels_file.read_text()) or {}) if self.levels_file.exists() else {}

    def set_levels(self, levels: dict[str, int]) -> None:
        self.levels_file.parent.mkdir(parents=True, exist_ok=True)
        self.levels_file.write_text(yaml.safe_dump(dict(levels), sort_keys=False))

    def quests(self) -> dict:
        return (yaml.safe_load(self.quests_file.read_text()) or {}) if self.quests_file.exists() else {}

    def set_quests(self, quests: dict) -> None:
        self.quests_file.parent.mkdir(parents=True, exist_ok=True)
        self.quests_file.write_text(yaml.safe_dump(dict(quests), sort_keys=False))

    # --- goals ----------------------------------------------------------------------------
    def goals(self) -> list[dict]:
        if not self.goals_file.exists():
            return []
        return yaml.safe_load(self.goals_file.read_text()) or []

    def goal(self) -> dict | None:
        g = self.goals()
        return g[-1] if g and not g[-1].get("vetoed") else None

    def veto_goal(self, why: str = "") -> dict | None:
        """The owner said no to the current goal. Returns it, or None if there's none."""
        goal = self.goal()
        if goal is not None:
            g = self.goals() + [{**goal, "vetoed": True, "why": why, "set": _now()}]
            self.goals_file.write_text(yaml.safe_dump(g, sort_keys=False, allow_unicode=True))
        return goal

    def turns_since_goal(self, now: int) -> int | None:
        g = self.goal()
        return None if g is None or "turn" not in g else now - g["turn"]

    def set_goal(self, goal: str, reason: str, turn: int = 0) -> None:
        g = self.goals() + [{"goal": str(goal).strip(), "reason": str(reason).strip(), "set": _now(),
                             "turn": turn}]
        self.goals_file.write_text(yaml.safe_dump(g, sort_keys=False, allow_unicode=True))

    # --- journal --------------------------------------------------------------------------
    def write_journal(self, entry: str) -> None:
        with self.journal_file.open("a") as f:
            f.write(f"**{_now()}** {' '.join(str(entry).split())}\n\n")

    # --- firsts ---------------------------------------------------------------------------
    def first(self, item: str) -> bool:
        """True the first time he ever gets `item` (and remembers it)."""
        seen = yaml.safe_load(self.firsts_file.read_text()) if self.firsts_file.exists() else {}
        seen = seen or {}
        if item in seen:
            return False
        seen[item] = _now()
        self.firsts_file.write_text(yaml.safe_dump(seen, allow_unicode=True))
        return True

    # --- reflexes -------------------------------------------------------------------------
    def reflexes(self) -> dict:
        if not self.reflex_file.exists():
            return dict(DEFAULT_REFLEXES)
        return {**DEFAULT_REFLEXES, **(yaml.safe_load(self.reflex_file.read_text()) or {})}

    def set_reflexes(self, eat_below: int, food: list[str], flee_below: int | None = None,
                     loot: list[str] | None = None) -> None:
        r = {"eat_below": int(eat_below), "food": food}
        old = self.reflexes() if self.reflex_file.exists() else {}
        r["flee_below"] = int(flee_below) if flee_below is not None else old.get("flee_below", 25)
        r["loot"] = list(loot) if loot is not None else old.get("loot", [])
        self.reflex_file.write_text(yaml.safe_dump(r))

    # --- decision log ---------------------------------------------------------------------
    def log(self, record: dict) -> None:
        with self.decisions_file.open("a") as f:
            f.write(json.dumps({"at": _now(), "account": self.account, **record}) + "\n")
