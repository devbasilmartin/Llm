"""The simulated game behaves like the real one where superbond2 will rely on it, checked
through the eyes, the way superbond2 will see it."""
from superbond2.eyes import UNTAGGED, Eyes
from superbond2.layout import SLOTS
from superbond2.sim import SimGame, lumbridge

EYES = Eyes()


def see(game):
    return EYES.look(game.grab())


def oak(game):
    return next((t for t in game.things if t.name == "oak_tree" and t.here(game.t)), None)


def test_chopping_fills_the_inventory_then_stops():
    game = lumbridge()
    for _ in range(300):                        # keep clicking an oak while there's room
        if None not in game.inventory:
            break
        if game.doing is None and oak(game):    # both can be chopped down: wait for one
            game.click(oak(game).box.center)
        game.advance(2.4)
    view = see(game)
    assert view.free_slots == 0
    assert view.items()["oak_logs"] == SLOTS - 4          # 3 trout and the axe were there
    assert game.doing is None


def test_the_bank_takes_everything_but_tools():
    game = lumbridge()
    game.give("oak_logs", 10)
    bank = next(t for t in game.things if t.name == "bank")
    game.click(bank.box.center)
    assert see(game).inventory[0] == UNTAGGED and see(game).free_slots == SLOTS - 1
    assert game.bank == {"oak_logs": 10, "trout": 3}


def test_a_depleted_tree_loses_its_highlight_until_it_grows_back():
    game = SimGame(seed=3)
    tree = game.add("tree", "gather", 100, 50, gives="logs", deplete=1.0, respawn=10)
    game.click(tree.box.center)
    while tree.here(game.t):
        game.advance(0.6)
    assert see(game).count("tree") == 0 and game.doing is None
    game.advance(10)
    assert see(game).count("tree") == 1


def test_shift_click_drops_and_clicking_food_eats():
    game = lumbridge()
    game.hp = 20
    game.click(game.layout.slot(1).center)           # trout
    assert game.hp == 27 and see(game).items()["trout"] == 2
    game.click(game.layout.slot(0).center, shift=True)   # the axe
    assert see(game).inventory[0] is None


def test_cows_fight_back_and_drop_loot_you_can_pick_up():
    game = lumbridge()
    cow = next(t for t in game.things if t.name == "cow")
    game.click(cow.box.center)
    for _ in range(100):
        game.advance(0.6)
        if not cow.here(game.t):
            break
    assert not cow.here(game.t) and game.hp < 40
    loot = see(game).nearest("loot")
    assert loot is not None
    game.click(loot.center)
    assert see(game).items()["cowhide"] == 1 and see(game).count("loot") == 0


def test_dying_respawns_you_with_nothing():
    game = lumbridge()
    game.hp = 1
    cow = next(t for t in game.things if t.name == "cow")
    cow.hp = 1000
    game.click(cow.box.center)
    while game.deaths == 0:
        game.advance(0.6)
    view = see(game)
    assert view.hp == 1.0 and view.free_slots == SLOTS
