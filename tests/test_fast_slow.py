"""Two brains: a quick model for everyday turns, the thoughtful one when it matters (and
while routines play). And the flee reflex."""
import pytest

from superbond2.actions import Actions
from superbond2.brain import SLOW_EVERY, Brain, Owner, Reflexes
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.memory import Memory
from superbond2.sim import lumbridge
from test_brain import Scripted

EYES = Eyes()
WAIT = ("wait", {"seconds": 1})


@pytest.fixture
def game():
    return lumbridge(seed=2)


@pytest.fixture
def memory(tmp_path):
    m = Memory(tmp_path / "memory")
    m.set_goal("Woodcutting 15", "oaks are right here")
    return m


def two(game, memory, fast, slow, owner=None):
    return Brain(slow, Actions(SimBody(game), EYES), memory, owner or Owner(log=lambda s: None),
                 log=lambda s: None, fast=fast)


def test_one_brain_is_always_the_thoughtful_one(game, memory):
    slow = Scripted(WAIT, WAIT)
    b = Brain(slow, Actions(SimBody(game), EYES), memory, Owner(log=lambda s: None), log=lambda s: None)
    b.turn(), b.turn()
    assert slow.kinds == ["slow", "slow"] and "Time to think it over" not in slow.prompts[0]


def test_everyday_turns_go_to_the_fast_brain_with_a_short_prompt(game, memory):
    fast, slow = Scripted(WAIT, WAIT), Scripted()
    b = two(game, memory, fast, slow)
    t = b.turn()
    assert fast.kinds == ["fast"] and t.brain == "fast" and slow.prompts == []
    assert fast.prompts[0].startswith("Your goal: Woodcutting 15")
    assert "Notebook" not in fast.prompts[0] and "Now:" in fast.prompts[0]


def test_no_goal_is_for_the_thoughtful_brain(game, memory, tmp_path):
    fast, slow = Scripted(), Scripted(("set_goal", {"goal": "Mining 10", "reason": "rocks"}), )
    b = two(game, Memory(tmp_path / "fresh"), fast, slow)
    b.turn()
    assert slow.kinds == ["slow"] and slow.prompts[0].endswith("Time to think it over: you have no goal.")


def test_the_fast_brain_hands_over_when_it_needs_thought(game, memory):
    fast = Scripted(("think_it_over", {"why": "a cow is attacking me"}),
                    ("set_goal", {"goal": "x", "reason": "y"}), WAIT)
    slow = Scripted(WAIT, WAIT)
    b = two(game, memory, fast, slow)
    assert b.turn().result == "you'll think it over next turn"
    b.turn()
    assert slow.prompts[0].endswith("Time to think it over: a cow is attacking me.")
    t = b.turn()                                     # the fast brain can't set goals...
    assert t.ok and "set_goal is for when you think it over" in t.result
    b.turn()                                         # ...so the thoughtful one gets the turn
    assert slow.prompts[1].endswith("Time to think it over: you wanted to set_goal.")
    assert memory.goal()["goal"] == "Woodcutting 15"


def test_a_fast_turn_without_a_tool_call_goes_to_the_thoughtful_brain(game, memory):
    fast, slow = Scripted(None), Scripted(WAIT)
    b = two(game, memory, fast, slow)
    b.turn()
    b.turn()
    assert slow.prompts[0].endswith("the quick turn didn't call a tool.")


def test_the_thoughtful_brain_steps_back_in_now_and_then(game, memory):
    waits = [("wait", {"seconds": 1 + i % 2}) for i in range(40)]   # (the same thing over and
    fast, slow = Scripted(*waits), Scripted(WAIT, WAIT)                # over would get it too)
    b = two(game, memory, fast, slow)
    b.journaled = 10 ** 6                            # (no journal reminder in the way)
    for _ in range(SLOW_EVERY + 1):
        b.turn()
    assert slow.kinds == ["slow"]
    assert slow.prompts[0].endswith("time to step back and check how it's going.")
    assert b.last_slow == SLOW_EVERY


def test_the_owner_speaking_gets_the_thoughtful_brain(game, memory):
    owner = Owner(log=lambda s: None)
    fast, slow = Scripted(WAIT), Scripted(WAIT)
    b = two(game, memory, fast, slow, owner)
    b.turn()
    owner.said.append("the willow by the door is worth a look")
    b.listen()
    b.turn()
    assert slow.prompts[0].endswith("Time to think it over: the owner said something.")


CHOP = {"name": "chop oaks", "about": "Chop until full.", "steps": ["click_nearest oak_tree if idle", "wait 2"],
        "until": "inventory full"}


def test_it_thinks_while_a_routine_plays(game, memory):
    fast = Scripted(("run_routine", CHOP), WAIT)
    slow = Scripted(("note", {"text": "Oaks respawn fast here."}))
    b = two(game, memory, fast, slow)
    b.last_slow, b.turns = 10, 15
    b.journaled = 15
    b.turn()
    b.turn()
    assert slow.kinds == ["background"]
    assert "A routine is playing by itself right now (chop oaks)" in slow.prompts[0]
    assert "Oaks respawn fast here." in memory.notes()
    assert any("(thinking while the routine played) note(" in r for r in b.recent)
    assert b.last_slow == 17 and b.background is None


def test_thinking_during_a_routine_cant_play_the_game(game, memory):
    fast = Scripted(("run_routine", CHOP), WAIT)
    slow = Scripted(("click_nearest", {"name": "bank"}))
    b = two(game, memory, fast, slow)
    b.turns, b.last_slow, b.journaled = 20, 10, 20
    b.turn()
    b.turn()
    assert any("click_nearest can't be done while thinking during a routine" in r for r in b.recent)


def test_no_background_thinking_right_after_a_thoughtful_turn(game, memory):
    fast, slow = Scripted(("run_routine", CHOP)), Scripted()
    b = two(game, memory, fast, slow)
    b.turns = b.last_slow = 3
    b.turn()
    assert slow.prompts == [] and b.background is None


# --- the flee reflex -------------------------------------------------------------------------
class FakeSession:
    def __init__(self):
        self.logged_out = 0

    def log_out(self):
        self.logged_out += 1


def fighting(game):
    game.inventory = [None] * 28                     # no food
    cow = next(t for t in game.things if t.name == "cow")
    cow.hp = 1000
    game.click(cow.box.center)
    assert game.doing is cow
    return cow


def test_with_no_food_he_runs_from_a_fight(game, memory):
    fighting(game)
    game.hp = 9                                      # 22%
    actions = Actions(SimBody(game), EYES)
    reflex = Reflexes(actions, memory)
    stop = reflex(actions.look())
    assert stop == "HP 22% and no food: ran from the fight"
    assert reflex.last.startswith("reflex: HP 22% and no food: ran ")
    assert game.doing is None                        # walked off: the cow isn't being fought
    assert reflex(actions.look()) == "HP 22% and no food"   # safe now; no running in circles


def test_still_losing_hp_after_running_he_logs_out(game, memory):
    fighting(game)
    game.hp = 9
    actions, session = Actions(SimBody(game), EYES), FakeSession()
    reflex = Reflexes(actions, memory, session)
    reflex(actions.look())
    game.hp = 6
    t = game.t
    assert reflex(actions.look()) == "fled the fight and logged out"
    assert session.logged_out == 1 and game.t - t >= Reflexes.REST
    assert "logged out and rested 2 minutes" in reflex.last


def test_he_can_change_when_he_runs(game, memory):
    b = Brain(Scripted(("set_reflexes", {"eat_below": 50, "food": "trout", "flee_below": 10})),
              Actions(SimBody(game), EYES), memory, Owner(log=lambda s: None), log=lambda s: None)
    b.turn()
    assert memory.reflexes()["flee_below"] == 10
    memory.set_reflexes(40, ["trout"])               # eat settings alone keep the flee one
    assert memory.reflexes()["flee_below"] == 10
