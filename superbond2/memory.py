"""superbond2's memory: plain files you can open and read.

    notebook.md       what he's learned, in his own words (it starts with who he is and your offer)
    firsts.yaml       the first time he got each item
    journal.md        his diary
    goals.yaml        the goal he's on, and the ones before it
    reflexes.yaml     when to eat, and what counts as food (his choice)
    decisions.jsonl   every turn: what he saw, what he did, what happened
    routines/         his routines (routines.py)

The model forgets everything between turns: what's written here, and the last few turns, is
all he knows.
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
]
DEFAULT_REFLEXES = {"eat_below": 40, "food": ["trout", "shrimps", "lobster", "cooked_meat",
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
        self.journal_file = self.folder / "journal.md"
        self.goals_file = self.folder / "goals.yaml"
        self.reflex_file = self.folder / "reflexes.yaml"
        self.decisions_file = self.folder / "decisions.jsonl"
        self.firsts_file = self.folder / "firsts.yaml"
        self.routines = Library(self.folder / "routines")
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

    # --- goals ----------------------------------------------------------------------------
    def goals(self) -> list[dict]:
        if not self.goals_file.exists():
            return []
        return yaml.safe_load(self.goals_file.read_text()) or []

    def goal(self) -> dict | None:
        g = self.goals()
        return g[-1] if g else None

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

    def set_reflexes(self, eat_below: int, food: list[str]) -> None:
        self.reflex_file.write_text(yaml.safe_dump({"eat_below": int(eat_below), "food": food}))

    # --- decision log ---------------------------------------------------------------------
    def log(self, record: dict) -> None:
        with self.decisions_file.open("a") as f:
            f.write(json.dumps({"at": _now(), **record}) + "\n")
