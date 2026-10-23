"""The color registry: every RuneLite highlight color has a name and a meaning.

The colors come from colors.yaml, shared with skillbot. Item colors are Inventory Tags;
everything else is drawn in the world (Object Markers, NPC Indicators, Ground Items...).
Minigames reuse colors inside their own `area`, so the eyes only look for the colors of the
area they're in, plus the ones marked `everywhere`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REGISTRY_FILE = Path(__file__).resolve().parent / "colors.yaml"
NOT_HIGHLIGHTS = {"status_hp"}      # plugin colors that aren't things in the world


@dataclass(frozen=True)
class Color:
    name: str
    rgb: tuple[int, int, int]
    category: str                   # item, resource, bank, station, enemy, loot, route...
    area: str = "default"


class Registry:
    def __init__(self, colors: list[Color]):
        self.colors = {c.name: c for c in colors}

    @classmethod
    def load(cls, path: Path = REGISTRY_FILE) -> "Registry":
        raw = yaml.safe_load(Path(path).read_text())
        return cls([Color(name, tuple(v["rgb"]), v["category"], v.get("area", "default"))
                    for name, v in raw.items()])

    def __getitem__(self, name: str) -> Color:
        return self.colors[name]

    def items(self) -> dict[str, tuple]:
        return {c.name: c.rgb for c in self.colors.values() if c.category == "item"}

    def world(self, area: str = "default") -> list[Color]:
        """Highlight colors that can be on screen in `area`."""
        return [c for c in self.colors.values() if c.category != "item"
                and c.name not in NOT_HIGHLIGHTS and c.area in (area, "everywhere")]
