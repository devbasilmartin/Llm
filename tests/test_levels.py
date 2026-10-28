"""Levels: the XP table, reading the Skills tab, level-ups told and summed up."""
import json
import time

import numpy as np

from superbond2 import levels
from superbond2.actions import Actions
from superbond2.brain import Brain, Owner
from superbond2.discord import daily_summary
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.memory import Memory
from superbond2.sim import lumbridge
from superbond2.text import Reader
from test_brain import Scripted

EYES = Eyes()


def test_the_xp_table():
    assert levels.xp_for_level(2) == 83 and levels.xp_for_level(99) == 13_034_431
    assert levels.level_for_xp(0) == 1 and levels.level_for_xp(83) == 2 and levels.level_for_xp(82) == 1
    assert levels.level_for_xp(10 ** 9) == 99


def test_the_prompt_line():
    lv = levels.starting_levels()
    assert levels.line(lv) == "Levels: all 1 (hitpoints 10): a fresh start; combat level 3"
    lv |= {"woodcutting": 15, "attack": 3}
    assert levels.line(lv) == "Levels: woodcutting 15, attack 3; the rest 1; combat level 4"


def test_reading_the_skills_tab():
    reader = Reader(ocr=lambda pic: "7/7")
    img = np.zeros((503, 765, 3), np.uint8)
    lay = reader.layout
    for i in range(len(levels.SKILLS)):
        x = lay.skills_origin[0] + (i % 3) * lay.skills_step[0] + lay.skills_cell[0] // 2
        y = lay.skills_origin[1] + (i // 3) * lay.skills_step[1]
        img[y + 8:y + 16, x + 4:x + 24] = (255, 255, 0)              # yellow numbers
    got = reader.levels(img)
    assert got is not None and set(got) == set(levels.SKILLS) and set(got.values()) == {7}
    assert Reader(ocr=lambda pic: "?").levels(np.zeros((503, 765, 3), np.uint8)) is None


def test_a_level_up_is_told_posted_and_summed(tmp_path):
    game = lumbridge(seed=2)
    memory = Memory(tmp_path / "m")
    memory.set_goal("Woodcutting 5", "oaks")
    told = []
    chop = {"name": "chop", "about": "x", "steps": ["click_nearest oak_tree if idle and see oak_tree",
                                                     "wait 2"], "until": "inventory full"}
    model = Scripted(("wait", {"seconds": 1}), ("run_routine", chop), ("wait", {"seconds": 2}))
    b = Brain(model, Actions(SimBody(game), EYES), memory, Owner(log=told.append), log=lambda s: None)
    b.turn()
    assert memory.levels()["woodcutting"] == 1
    b.turn()                                          # 20-odd oak logs: woodcutting goes up
    assert memory.levels()["woodcutting"] > 1
    assert any(m.startswith("[to owner] 🎉 Level up! Woodcutting") for m in told)
    b.turn()
    assert "🎉 level up! woodcutting 1 ->" in model.prompts[2]
    assert "Levels: woodcutting" in model.prompts[2]
    summary = daily_summary(memory, time.strftime("%Y-%m-%d"))
    assert "🎉 Levels: woodcutting 1 → " in summary
    events = [json.loads(line) for line in memory.decisions_file.read_text().splitlines()]
    assert any(e.get("event") == "level" for e in events)
