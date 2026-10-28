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
    game.walls = {(x, y) for x in range(3200, 3230) for y in range(3225, 3228)}   # north of him
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
