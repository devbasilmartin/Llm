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
    b = Brain(slow, Actions(SimBody(game), EYES), memory, owner or Owner(log=lambda s: None),
              log=lambda s: None, fast=fast)
    b.background_min = 0                    # the sim's routines are over in a moment
    return b


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
    fast = Scripted(*[("wait", {"seconds": i}) for i in (1, 2, 3)],
                    ("think_it_over", {"why": "a cow is attacking me"}),
                    ("set_goal", {"goal": "x", "reason": "y"}), WAIT)
    slow = Scripted(WAIT, WAIT)
    b = two(game, memory, fast, slow)
    b.turn(), b.turn(), b.turn()
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


CHOP = {"name": "chop oaks", "about": "Chop until full.", "steps": ["click_nearest oak_tree if idle and see oak_tree", "wait 2"],
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
    b.turn()                                         # one turn after: not yet
    assert slow.prompts == [] and b.background is None


def test_background_thinking_stands_in_for_stepping_back(game, memory):
    fast = Scripted(("run_routine", CHOP), ("run_routine", CHOP), WAIT)
    slow = Scripted(("journal", {"entry": "Oaks all day!"}))
    b = two(game, memory, fast, slow)
    b.journaled = 10 ** 6
    b.turns = b.last_slow = 3
    b.turns = 4                                      # two turns after the last thoughtful one
    b.turn()
    b.turn()                                         # the next routine: done thinking by then
    assert slow.kinds == ["background"] and b.last_slow == 6
    b.turn()
    assert fast.kinds == ["fast"] * 3                # no extra thoughtful turn needed


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


def test_doing_it_by_hand_three_times_hands_over_to_write_the_routine(game, memory):
    chop = ("click_nearest", {"name": "oak_tree"})
    fast = Scripted(chop, WAIT, chop, WAIT, chop, WAIT, WAIT)
    slow = Scripted(("save_routine", CHOP))
    b = two(game, memory, fast, slow)
    b.journaled = 10 ** 6
    for _ in range(7):
        b.turn()
    assert slow.kinds == ["slow"] and "save it as a routine" in slow.prompts[0]
    assert "chop oaks" in memory.routines.names()


def test_a_routine_that_doesnt_exist_yet_is_for_the_thoughtful_brain(game, memory):
    fast, slow = Scripted(("run_routine", {"name": "oak loop"})), Scripted(WAIT)
    b = two(game, memory, fast, slow)
    b.turn()
    b.turn()
    assert slow.prompts[0].endswith("there's no routine called 'oak loop' yet.")


def test_no_asking_to_think_again_right_after_thinking(game, memory):
    fast = Scripted(("think_it_over", {"why": "same old thing"}))
    b = two(game, memory, fast, Scripted())
    b.turns = b.last_slow = 10
    t = b.turn()
    assert not t.ok and t.result == "you thought it over 1 turns ago; carry on with the plan"
    assert b.need_thought == ""


def test_the_fast_brain_reads_short_recent_turns(game, memory):
    fast = Scripted(WAIT)
    b = two(game, memory, fast, Scripted())
    b.recent = ["9. run_routine(...) -> " + "x" * 800]
    b.turn()
    line = next(line for line in fast.prompts[0].splitlines() if line.startswith("9. "))
    assert len(line) == 220 and line.endswith("...")


def test_only_long_routines_get_background_thinking(game, memory):
    from superbond2.brain import BACKGROUND_MIN
    fast, slow = Scripted(("run_routine", CHOP), ("run_routine", CHOP)), Scripted()
    b = two(game, memory, fast, slow)
    b.background_min = BACKGROUND_MIN
    b.journaled = 10 ** 6
    b.turns, b.last_slow = 10, 0
    b.turn()                                         # first run: how long it takes isn't known
    assert slow.prompts == [] and memory.routines.stats("chop oaks")["seconds"] < BACKGROUND_MIN
    b.turn()                                         # quick in the sim: still no
    assert slow.prompts == []


def test_routine_times_are_a_running_mean(tmp_path):
    from superbond2.routines import Library, RunResult
    lib = Library(tmp_path)
    from superbond2.routines import simple_routine
    r = lib.save(simple_routine("chop", "x", ["wait 2"]))
    ok = RunResult(True, "done", 1, [])
    lib.record(r, ok, 100)
    lib.record(r, ok, 200)
    assert lib.stats("chop")["seconds"] == 130.0


def test_after_waiting_for_background_thinking_he_looks_again(game, memory):
    import threading
    fast = Scripted(WAIT)
    b = two(game, memory, fast, Scripted())
    b.actions.look()

    def think():                                     # meanwhile, the game moved on
        game.give("oak_logs", 5)
    t = threading.Thread(target=think)
    t.start()
    b.background = (t, {}, "prompt")
    b.turn()
    assert "5 oak logs" in fast.prompts[0]


class LoggingOut:
    def __init__(self, game):
        self.game = game

    def log_out(self):
        self.game.screen = "login"


def test_a_reflex_logout_skips_the_model(game, memory):
    fighting(game)
    game.hp = 9
    fast, slow = Scripted(), Scripted()
    b = two(game, memory, fast, slow)
    b.reflexes.session = LoggingOut(game)
    b.reflexes.fled = 30                             # already ran once, and still dropping
    t = b.turn()
    assert t.result == "reflex: fled the fight and logged out" and t.ok
    assert fast.prompts == [] and slow.prompts == []
