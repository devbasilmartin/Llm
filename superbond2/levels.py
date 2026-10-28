"""Skills, levels and XP: the game's own table."""
from __future__ import annotations

import math

# the Skills tab, row by row (3 columns), as the game lays it out (not measured yet)
SKILLS = ["attack", "hitpoints", "mining", "strength", "agility", "smithing", "defence",
          "herblore", "fishing", "ranged", "thieving", "cooking", "prayer", "crafting",
          "firemaking", "magic", "fletching", "woodcutting", "runecraft", "slayer", "farming",
          "construction", "hunter"]


def xp_for_level(level: int) -> int:
    return int(sum(math.floor(n + 300 * 2 ** (n / 7)) for n in range(1, level)) / 4)


TABLE = [xp_for_level(n) for n in range(1, 100)]      # TABLE[k] = xp needed for level k + 1


def level_for_xp(xp: float) -> int:
    level = 1
    while level < 99 and xp >= TABLE[level]:
        level += 1
    return level


def starting_levels() -> dict[str, int]:
    return {s: (10 if s == "hitpoints" else 1) for s in SKILLS}


def changes(before: dict, after: dict) -> list[tuple[str, int, int]]:
    """(skill, from, to) for each skill that went up."""
    return [(s, before.get(s, 1), after[s]) for s in SKILLS if after.get(s, 1) > before.get(s, 1)]


def line(levels: dict) -> str:
    """For the prompt: what's been trained, highest first, and combat basics."""
    trained = sorted(((lv, s) for s, lv in levels.items() if lv > (10 if s == "hitpoints" else 1)),
                     reverse=True)
    if not trained:
        return "Levels: all 1 (hitpoints 10): a fresh start"
    return "Levels: " + ", ".join(f"{s} {lv}" for lv, s in trained) + "; the rest 1"
