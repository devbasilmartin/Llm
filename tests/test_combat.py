"""Fighting smarter: targets by level, attack styles, burying bones, looting by reflex."""
from superbond2 import levels
from superbond2.actions import Actions
from superbond2.brain import Brain, Owner
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.memory import Memory
from superbond2.sim import SimGame
from test_brain import Scripted

EYES = Eyes()


def field():
    g = SimGame(seed=4)
    g.add("cow", "monster", 60, 200, 40, 30, gives="cowhide", hp=8, level=8)
    g.add("cow", "monster", 300, 200, 40, 30, gives="cowhide", hp=8, level=2)
    return g


def test_the_combat_level():
    lv = levels.starting_levels()
    assert levels.combat_level(lv) == 3
    lv |= {"attack": 40, "strength": 40, "defence": 40, "hitpoints": 40}
    assert levels.combat_level(lv) == 46
    assert levels.line(lv).endswith("; combat level 46")


def test_attack_picks_one_his_size():
    game = field()
    act = Actions(SimBody(game), EYES)
    r = act.attack("cow", max_level=5)
    assert r.ok and r.said.startswith("attacking Cow (level-2)")
    assert game.doing.level == 2
    r = act.attack("cow", max_level=1)
    assert not r.ok and "every cow in sight is over level 1" in r.said


def test_styles_choose_what_fighting_trains():
    game = field()
    act = Actions(SimBody(game), EYES)
    assert act.set_style("strength").ok and game._tab == "inventory"
    act.attack("cow")
    act.wait_until_idle(120)
    assert game.xp["strength"] > 0 and game.xp["attack"] == 0
    assert not act.set_style("magic").ok


def test_burying_bones():
    game = field()
    game.give("bones", 2)
    act = Actions(SimBody(game), EYES)
    act.click_item("bones")
    assert game.xp["prayer"] == 4.5 and game.inventory.count("bones") == 1


def test_the_loot_reflex_picks_up_whats_on_his_list(tmp_path):
    game = field()
    memory = Memory(tmp_path / "m")
    memory.set_goal("Attack 10", "cows")
    memory.set_reflexes(40, ["trout"], 25, ["cowhide"])
    b = Brain(Scripted(("attack", {"name": "cow", "max_level": 5}), ("wait_until_idle", {"timeout": 120}),
                       ("wait", {"seconds": 1})),
              Actions(SimBody(game), EYES), memory, Owner(log=lambda s: None), log=lambda s: None)
    b.turn(), b.turn()
    assert game.inventory.count("cowhide") == 0           # dropped, not yet picked up
    b.turn()
    assert game.inventory.count("cowhide") == 1
    assert any("reflex: picked up Cowhide" in r for r in b.recent)
    assert memory.reflexes()["loot"] == ["cowhide"]
