import json

import pytest

from superbond2.actions import Actions
from superbond2.brain import SYSTEM, TOOL_NAMES, TOOLS, Brain, Owner
from superbond2.eyes import Eyes
from superbond2.hands import SimBody, Stopped
from superbond2.memory import Memory
from superbond2.model import ModelError, Reply, parse_calls
from superbond2.sim import lumbridge

EYES = Eyes()

CHOP_AND_DROP = """name: chop and drop oaks
about: Chop oaks until the inventory is full, then drop the logs.
steps:
  - repeat:
    until: inventory full
    do:
      - if: idle and see oak_tree
        then:
          - click_nearest: oak_tree
      - wait: 2
  - drop_all: oak_logs
"""


class Scripted:
    """Stands in for the model: each turn's answer is the next call in the script (or a
    function of the prompt). Keeps every prompt it was shown."""

    def __init__(self, *script):
        self.script, self.prompts = list(script), []

    def chat(self, messages, tools):
        assert messages[0]["content"] == SYSTEM and tools == TOOLS
        self.prompts.append(messages[1]["content"])
        step = self.script.pop(0)
        if callable(step):
            step = step(messages[1]["content"])
        if isinstance(step, Exception):
            raise step
        if step is None:
            return Reply(content="hmm, let me think", seconds=1.0)
        name, args = step
        return Reply(calls=[{"name": name, "arguments": args}], thinking="ok", seconds=2.0)


@pytest.fixture
def game():
    return lumbridge(seed=2)


@pytest.fixture
def memory(tmp_path):
    return Memory(tmp_path / "memory")


def brain(game, memory, *script, said=None):
    owner = Owner(log=(said.append if said is not None else lambda s: None))
    return Brain(Scripted(*script), Actions(SimBody(game), EYES), memory, owner, log=lambda s: None)


def test_tools_have_unique_names_and_descriptions():
    names = [t["function"]["name"] for t in TOOLS]
    assert len(names) == len(set(names)) == len(TOOL_NAMES)
    assert all(t["function"]["description"] for t in TOOLS)


def test_his_first_prompt_has_the_offer_no_goal_and_what_he_sees(game, memory):
    b = brain(game, memory, ("wait", {"seconds": 1}))
    b.turn()
    p = b.model.prompts[0]
    assert "Your goal: none yet. Pick one with set_goal." in p
    assert "only Dragon Slayer earns membership" in p
    assert "I can only work with what I see on screen" in p
    assert "(no routines saved yet)" in p and "(this is your first turn)" in p
    assert "Highlighted nearby:" in p and p.index("Notebook:") < p.index("Now:")


def test_a_goal_note_and_journal_are_kept_and_shown(game, memory):
    said = []
    b = brain(game, memory,
              ("set_goal", {"goal": "Woodcutting 30", "reason": "oaks are right here"}),
              ("note", {"text": "Oaks run out after a few logs and grow back."}),
              ("journal", {"entry": "First day. Chopping oaks."}),
              ("wait", {"seconds": 1}), said=said)
    for _ in range(4):
        b.turn()
    assert memory.goal()["goal"] == "Woodcutting 30"
    assert said == ["[to owner] New goal: Woodcutting 30. Why: oaks are right here"]
    assert "Oaks run out after a few logs and grow back." in memory.notes()
    assert "First day. Chopping oaks." in memory.journal_file.read_text()
    p = b.model.prompts[3]
    assert "Your goal: Woodcutting 30 (why: oaks are right here)" in p
    assert "- Oaks run out after a few logs and grow back." in p
    assert '1. set_goal({"goal": "Woodcutting 30"' in p and "3. journal(" in p


def test_he_writes_a_routine_runs_it_and_it_keeps_score(game, memory):
    b = brain(game, memory, ("save_routine", {"routine": CHOP_AND_DROP}),
              ("run_routine", {"name": "chop and drop oaks"}), ("wait", {"seconds": 1}))
    assert b.turn().result == "saved routine 'chop and drop oaks'"
    t = b.turn()
    assert t.ok and "chop and drop oaks: done after" in t.result
    b.turn()
    assert "chop and drop oaks: Chop oaks until the inventory is full, then drop the logs. " \
           "(ran 1x, worked 1, failed 0)" in b.model.prompts[2]


def test_a_broken_routine_comes_back_with_what_to_fix(game, memory):
    b = brain(game, memory, ("save_routine", {"routine": "name: x\nabout: y\nsteps: [{fly: home}]"}),
              ("run_routine", {"name": "mine iron"}))
    assert "should be 2-60 lower-case" in b.turn().result
    t = b.turn()
    assert not t.ok and "no routine called 'mine iron'" in t.result


def test_game_actions_work_and_numbers_as_text_are_fine(game, memory):
    b = brain(game, memory, ("click_nearest", {"name": "oak_tree"}), ("wait", {"seconds": "3"}),
              ("click_slot", {"slot": "1"}))
    assert "you're busy now" in b.turn().result
    assert b.turn().result.startswith("waited 3s")
    assert b.turn().ok


def test_mistakes_cost_a_turn_and_repeated_ones_stop_him(game, memory):
    b = brain(game, memory, ("fly", {}), None, ModelError("can't reach it"))
    assert b.play(turns=10) == "stopped: 3 turns in a row without a usable tool call"
    assert "1. (no tool)" not in b.recent[0] and "there's no action called fly" in b.recent[0]
    assert "you didn't call a tool" in b.recent[1]
    assert "the model failed: can't reach it" in b.recent[2]


def test_a_good_turn_resets_the_miss_count(game, memory):
    b = brain(game, memory, None, None, ("wait", {"seconds": 1}), None, None, ("wait", {"seconds": 1}))
    assert b.play(turns=6) == "stopped after 6 turns"


def test_reflexes_eat_before_he_thinks(game, memory):
    game.hp = 10
    b = brain(game, memory, ("wait", {"seconds": 1}))
    b.turn()
    assert game.hp == 17
    assert "1. reflex: clicked trout: -1 trout; HP 25% -> 42%" in b.model.prompts[0]


def test_he_sets_his_own_reflexes(game, memory):
    game.hp = 10
    b = brain(game, memory, ("set_reflexes", {"eat_below": 0, "food": "trout"}), ("wait", {"seconds": 1}))
    b.turn()                                    # the default reflex eats once first
    b.turn()
    assert game.hp == 17                        # ...but not again: he turned it off
    assert "Reflexes: off" in b.model.prompts[1]


def test_no_food_left_is_reported_and_stops_a_routine(game, memory):
    game.hp = 8
    game.inventory = [None] * 28
    cow = next(t for t in game.things if t.name == "cow")
    cow.hp = 1000
    fight = "name: fight cows\nabout: Fight the cow.\nsteps:\n  - click_nearest: cow\n  - wait: 30\n"
    b = brain(game, memory, ("save_routine", {"routine": fight}), ("run_routine", {"name": "fight cows"}))
    b.turn()
    t = b.turn()
    assert "reflex: HP 20% and no food" in b.model.prompts[1]
    assert not t.ok and "stopped by a reflex: HP" in t.result


def test_ask_owner_without_an_answer_and_no_nagging(game, memory):
    said = []
    b = brain(game, memory, ("ask_owner", {"question": "Should I go for Vampire Slayer?"}),
              ("ask_owner", {"question": "Should I go for Vampire Slayer??"}), said=said)
    assert b.turn().result == "no answer yet; carry on with your best judgment"
    t = b.turn()
    assert not t.ok and "you already asked the owner" in t.result
    assert said == ["[question for owner] Should I go for Vampire Slayer?"]


def test_goals_cant_churn(game, memory):
    said = []
    b = brain(game, memory, ("set_goal", {"goal": "Woodcutting 30", "reason": "oaks"}),
              ("set_goal", {"goal": "Mining 30", "reason": "rocks"}),
              ("set_goal", {"goal": "Attack 20", "reason": "Woodcutting 30 can't be done here"}),
              said=said)
    b.turn()
    t = b.turn()
    assert not t.ok and "you set your goal 1 turns ago" in t.result
    assert memory.goal()["goal"] == "Woodcutting 30"
    assert b.turn().ok and memory.goal()["goal"] == "Attack 20"   # he said why
    assert len(said) == 2


def test_every_turn_is_logged(game, memory):
    b = brain(game, memory, ("note", {"text": "hello"}), ("wait", {"seconds": 1}))
    b.play(turns=2)
    rows = [json.loads(line) for line in memory.decisions_file.read_text().splitlines()]
    assert [r["tool"] for r in rows] == ["note", "wait"]
    assert rows[0]["thinking"] == "ok" and "Now:" in rows[0]["state"]


def test_the_kill_switch_goes_straight_through(game, memory):
    def pull(prompt):
        raise Stopped("the mouse is in a screen corner")
    with pytest.raises(Stopped):
        brain(game, memory, pull).play(turns=5)


def test_notebook_keeps_no_duplicates_and_trims(memory):
    assert memory.add_note("a  lesson\n learned") == "noted"
    assert memory.add_note("a lesson learned") == "already in your notebook"
    assert memory.add_note("   ") == "an empty note isn't kept"
    assert len(memory.notes()) == 4                    # the offer (3 notes) and the lesson


def test_parse_calls_handles_string_arguments():
    msg = {"tool_calls": [{"function": {"name": "wait", "arguments": '{"seconds": 5}'}},
                          {"function": {"name": "note", "arguments": "not json"}}]}
    assert parse_calls(msg) == [{"name": "wait", "arguments": {"seconds": 5}},
                                {"name": "note", "arguments": {"raw": "not json"}}]


def test_repeating_something_that_does_nothing_is_pointed_out(game, memory):
    b = brain(game, memory, *[("wait", {"seconds": 1})] * 3)
    results = [b.turn().result for _ in range(3)]
    assert results[1] == "waited 1s: nothing changed"
    assert results[2].endswith("(that's 3 times in a row with nothing changing: try something else)")
