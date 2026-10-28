"""use X on Y: light a fire, cook on it or a range ("how many?": all), as an action and a step."""
from superbond2.actions import Actions
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.routines import Routine, Runner, simple_routine
from superbond2.sim import lumbridge

EYES = Eyes()


def camp():
    game = lumbridge()
    game.give("tinderbox", tool=True)
    game.give("logs")
    game.give("raw_shrimps", 4)
    return game


def test_light_a_fire_and_cook_on_it():
    game = camp()
    act = Actions(SimBody(game), EYES)
    r = act.use("tinderbox", "logs")
    assert r.ok and "-1 logs" in r.said and game.xp["firemaking"] == 40
    assert "Fire (object" in act.survey().said
    r = act.use("raw shrimps", "Fire")
    assert r.ok and "-4 raw shrimps" in r.said and "+4 shrimps" in r.said
    assert game.xp["cooking"] == 120 and game.dialogue is None


def test_cook_on_a_range():
    game = camp()
    game.add("range", "static", 320, 60, 30, 30, label="Range", verb="Cook")
    act = Actions(SimBody(game), EYES)
    assert "+4 shrimps" in act.use("raw shrimps", "range").said


def test_use_mistakes():
    act = Actions(SimBody(camp()), EYES)
    assert act.use("knife", "logs").said == "no knife in your inventory"
    assert "no fire to use it on" in act.use("raw shrimps", "fire").said


def test_a_routine_lights_and_cooks():
    game = camp()
    act = Actions(SimBody(game), EYES)
    r = Runner(act).run(Routine.from_dict(simple_routine("camp", "x", ["use tinderbox on logs"])))
    assert r.ok and game.xp["firemaking"] == 40
