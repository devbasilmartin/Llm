"""Vampyre Slayer from start to finish in the sim, with nothing but superbond2's own actions:
walking, talking, choosing, stairs, searching, buying, fighting."""
from superbond2.actions import Actions
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.sim_quests import vampyre_world

EYES = Eyes()


def ok(r):
    assert r.ok, r.said
    return r.said


def test_vampyre_slayer_start_to_finish():
    game = vampyre_world()
    act = Actions(SimBody(game), EYES)
    # Morgan
    ok(act.walk_to("morgan's house"))
    assert "Morgan: \"Please help us!" in ok(act.talk_to("Morgan"))
    ok(act.continue_dialogue())
    assert "Blue Moon Inn" in ok(act.choose("Yes"))
    ok(act.continue_dialogue())
    assert "vampyre slayer started" in game.flags
    # the garlic, upstairs
    assert "Staircase" in ok(act.survey())
    assert "floor 1" in ok(act.interact("Staircase", "Climb-up"))
    ok(act.survey())
    assert "+1 garlic" in ok(act.interact("Cupboard", "Search"))
    ok(act.survey())
    ok(act.interact("Staircase", "Climb-down"))
    # a beer for Dr Harlow, and his stake
    ok(act.walk_to("blue moon inn"))
    assert "Buy an old man a drink?" in ok(act.talk_to("Dr Harlow"))
    assert "No beer, no help" in ok(act.continue_dialogue())
    act.continue_dialogue()
    assert "stake" not in game.inventory                    # no beer, no stake
    ok(act.talk_to("Bartender"))
    ok(act.continue_dialogue())
    ok(act.choose(1))
    ok(act.continue_dialogue())
    assert "beer" in game.inventory and game.coins == 8
    ok(act.talk_to("Dr Harlow"))
    ok(act.continue_dialogue())
    assert "stake" in game.inventory
    act.continue_dialogue()
    assert "+1 hammer" in ok(act.click_nearest("loot"))
    # the Count
    ok(act.walk_to("draynor manor"))
    ok(act.survey())
    ok(act.interact("Stairs", "Climb-down"))
    assert act.look().count("enemy") == 1
    ok(act.click_nearest("enemy"))
    act.wait_until_idle(timeout=300)
    assert "Aaargh!" in act._said()
    act.continue_dialogue()
    assert "Quest complete" in act._said()
    assert "vampyre slayer done" in game.flags and game.quest_points == 3
    assert game.deaths == 0


def test_without_the_hammer_the_count_rises_again():
    game = vampyre_world()
    act = Actions(SimBody(game), EYES)
    game.pos[:] = [3077, 9771, 0]
    game.give("stake")
    ok(act.click_nearest("enemy"))
    act.wait_until_idle(timeout=120)
    assert "can't kill me like that" in act._said()
    assert "vampyre slayer done" not in game.flags
