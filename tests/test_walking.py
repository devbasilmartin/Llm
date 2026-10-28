"""walk_to: minimap clicks toward a named place, checking where he is as he goes."""
from superbond2.actions import Actions, load_places
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.routines import Routine, Runner, simple_routine
from superbond2.sim import lumbridge

EYES = Eyes()


def test_walks_there_a_bit_at_a_time():
    game = lumbridge()
    act = Actions(SimBody(game), EYES)
    r = act.walk_to("Draynor bank")
    tx, ty, _ = load_places()["draynor bank"]
    assert r.ok and r.said.startswith("walked to draynor bank (")
    assert max(abs(game.pos[0] - tx), abs(game.pos[1] - ty)) <= 2


def test_places_by_part_of_the_name_and_unknown_ones():
    act = Actions(SimBody(lumbridge()), EYES)
    assert act.walk_to("varrock west").ok
    r = act.walk_to("Hogwarts")
    assert not r.ok and "I don't know a place called 'Hogwarts'" in r.said and "draynor bank" in r.said


def test_a_wall_in_the_way_is_reported():
    game = lumbridge()
    game.walls = {(x, y) for x in range(3100, 3350) for y in range(3225, 3228)}   # north of him
    r = Actions(SimBody(game), EYES).walk_to("grand exchange")
    assert not r.ok and "a wall or a door in the way?" in r.said


def test_another_floor_needs_stairs():
    r = Actions(SimBody(lumbridge()), EYES).walk_to("lumbridge bank")
    assert not r.ok and "on floor 2 and you're on floor 0" in r.said


def test_no_position_readout_says_so():
    class Blind(SimBody):
        def position(self):
            return None
    r = Actions(Blind(lumbridge()), EYES).walk_to("draynor bank")
    assert not r.ok and "can't tell where I am" in r.said


def test_a_routine_can_walk():
    game = lumbridge()
    act = Actions(SimBody(game), EYES)
    r = Runner(act).run(Routine.from_dict(simple_routine("to draynor", "x", ["walk_to draynor bank"])))
    assert r.ok and game.pos[0] < 3100


# --- doors, gates, stairs, ladders --------------------------------------------------------------
def doored():
    """A wall across the way north, with a door in it, and a ladder."""
    game = lumbridge()
    gap = {(x, 3226) for x in range(3221, 3224)}
    game.walls = {(x, 3226) for x in range(3150, 3300)} - gap
    door = next(t for t in game.things if t.label == "Door")
    door.blocks = frozenset(gap)
    game.walls |= gap
    game.add("tree", "static", 300, 60, 20, 40, label="Ladder", verb="Climb-up",
             options=("Climb-down",), marked=False)
    return game


def test_a_closed_door_stops_him_until_he_opens_it():
    game = doored()
    act = Actions(SimBody(game), EYES)
    r = act.walk_to("grand exchange")
    assert not r.ok and "interact it with Open" in r.said
    assert "Door (object" in act.survey().said
    r = act.interact("Door", "Open")
    assert r.ok and r.said.startswith("chose Open Door")
    assert act.walk_to("grand exchange").ok


def test_climbing_a_ladder_changes_the_floor():
    game = doored()
    act = Actions(SimBody(game), EYES)
    act.survey()
    r = act.interact("Ladder", "Climb-up")
    assert r.ok and r.said.endswith("you're on floor 1 now") and game.pos[2] == 1
    assert act.interact("Ladder", "Climb-down").ok and game.pos[2] == 0


def test_interact_says_what_the_menu_has():
    act = Actions(SimBody(doored()), EYES)
    assert "survey to find things" in act.interact("Door", "Open").said     # not surveyed yet
    act.survey()
    r = act.interact("Door", "Kick")
    assert not r.ok and "Door's menu has no 'Kick': Open Door, Walk here" in r.said


def test_a_routine_opens_a_door():
    game = doored()
    act = Actions(SimBody(game), EYES)
    act.survey()
    r = Runner(act).run(Routine.from_dict(simple_routine("through", "x", ["interact Door Open",
                                                                          "walk_to grand exchange"])))
    assert r.ok, r.said
