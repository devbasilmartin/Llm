"""Wearing things: equip from the inventory's menu, unequip from the Equipment tab, and
what he's wearing in his prompt."""
from superbond2.actions import Actions
from superbond2.brain import Brain, Owner
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.memory import Memory
from superbond2.sim import lumbridge
from test_brain import Scripted

EYES = Eyes()


def kitted():
    game = lumbridge()
    game.give("bronze_sword")
    game.give("wooden_shield")
    game.give("iron_scimitar")
    return game


def test_wield_wear_and_swap():
    game = kitted()
    act = Actions(SimBody(game), EYES)
    r = act.equip("bronze sword")
    assert r.ok and r.said == "wield bronze sword; wearing: bronze sword (weapon)"
    assert "bronze_sword" not in game.inventory
    act.equip("wooden shield")
    r = act.equip("iron scimitar")                        # the sword goes back in the bag
    assert r.said == "wield iron scimitar; wearing: iron scimitar (weapon), wooden shield (shield)"
    assert "bronze_sword" in game.inventory


def test_take_off():
    game = kitted()
    act = Actions(SimBody(game), EYES)
    act.equip("wooden shield")
    r = act.unequip("wooden shield")
    assert r.ok and r.said == "took off wooden shield; wearing: nothing"
    assert "wooden_shield" in game.inventory and game._tab == "inventory"


def test_mistakes():
    act = Actions(SimBody(kitted()), EYES)
    assert act.equip("rune platebody").said == "no rune_platebody in your inventory"
    r = act.equip("trout")
    assert not r.ok and r.said.startswith("trout isn't something to wear (its menu: Use Trout")
    assert "you're not wearing bronze_sword (wearing: nothing)" == act.unequip("bronze sword").said


def test_what_he_wears_is_in_his_prompt(tmp_path):
    game = kitted()
    memory = Memory(tmp_path / "m")
    model = Scripted(("equip", {"item": "bronze sword"}), ("wait", {"seconds": 1}))
    b = Brain(model, Actions(SimBody(game), EYES), memory, Owner(log=lambda s: None), log=lambda s: None)
    b.turn()
    assert "Wearing: nothing" in model.prompts[0]
    b.turn()
    assert "Wearing: bronze sword (weapon)" in model.prompts[1]
