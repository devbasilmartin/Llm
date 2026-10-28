"""Quest points and the quest log: read, shown, and a finished quest celebrated."""
import time

import numpy as np

from superbond2.actions import Actions
from superbond2.brain import Brain, Owner
from superbond2.discord import daily_summary
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.memory import Memory
from superbond2.sim_quests import vampyre_world
from superbond2.text import Reader
from test_brain import Scripted

EYES = Eyes()


def test_reading_the_quest_tab():
    words = iter(["Quest Points: 4", "Cook's Assistant", "Vampyre Slayer"])
    reader = Reader(ocr=lambda pic: next(words))
    img = np.zeros((503, 765, 3), np.uint8)
    lay = reader.layout
    p, q = lay.quest_points_text, lay.quest_list
    img[p.y + 4:p.y + 12, p.x + 4:p.x + 100] = (255, 152, 31)          # the orange title
    img[q.y + 4:q.y + 12, q.x + 4:q.x + 90] = (0, 255, 0)               # done: green
    img[q.y + 20:q.y + 28, q.x + 4:q.x + 70] = (255, 255, 0)            # started: yellow
    got = reader.quests(img)
    assert got == {"points": 4, "done": ["Cook's Assistant"], "started": ["Vampyre Slayer"]}


def test_a_finished_quest_is_celebrated(tmp_path):
    game = vampyre_world()
    memory = Memory(tmp_path / "m")
    told = []
    model = Scripted(("wait", {"seconds": 1}), ("wait", {"seconds": 2}))
    b = Brain(model, Actions(SimBody(game), EYES), memory, Owner(log=told.append), log=lambda s: None)
    game.flags.add("vampyre slayer started")
    b.turn()
    assert "Quest points: 0 (Dragon Slayer needs 32); started: vampyre slayer" in model.prompts[0]
    game.flags.add("vampyre slayer done")
    game.quest_points = 3
    b.check_quests()
    assert "[to owner] 🏆 Quest complete: vampyre slayer! 0 → 3 quest points." in told
    b.turn()
    assert "Quest points: 3 (Dragon Slayer needs 32); done: vampyre slayer" in model.prompts[1]
    assert "🏆 quest complete: vampyre slayer!" in model.prompts[1]
    assert "🏆 Quests: vampyre slayer (3 quest points)." in daily_summary(memory, time.strftime("%Y-%m-%d"))


# --- Quest Helper -------------------------------------------------------------------------------
def test_reading_quest_helpers_overlay():
    words = iter(["Vampyre Slayer", "Talk to Morgan in Draynor Village."])
    reader = Reader(ocr=lambda pic: next(words))
    img = np.zeros((503, 765, 3), np.uint8)
    r = reader.layout.quest_helper_text
    img[r.y + 2:r.y + 10, r.x + 4:r.x + 100] = (255, 255, 255)
    img[r.y + 16:r.y + 24, r.x + 4:r.x + 200] = (255, 255, 255)
    assert reader.quest_helper(img) == "Vampyre Slayer Talk to Morgan in Draynor Village."
    assert Reader(ocr=lambda pic: "x").quest_helper(np.zeros((503, 765, 3), np.uint8)) is None


def test_quest_helper_guides_him_through_the_quest():
    from superbond2.eyes import describe
    game = vampyre_world()
    act = Actions(SimBody(game), EYES)
    act.walk_to("morgan's house")
    text = describe(act.look())
    assert "Quest Helper: Vampyre Slayer: talk to Morgan in Draynor Village." in text
    assert "Quest Helper's highlights: quest_dialog = who Quest Helper wants you to talk to" in text
    act.talk_to("quest_dialog")                          # straight from the highlight
    act.continue_dialogue()
    act.choose(1)
    act.continue_dialogue()
    assert "garlic from the cupboard upstairs" in describe(act.look())
