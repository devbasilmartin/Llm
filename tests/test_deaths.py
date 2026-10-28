"""Noticing a death: from two looks, then told to him, the owner, the log and the summary."""
from superbond2.actions import Actions, died
from superbond2.brain import Brain, Owner
from superbond2.discord import daily_summary
from superbond2.eyes import Eyes, View
from superbond2.hands import SimBody
from superbond2.memory import Memory
from superbond2.sim import lumbridge
from test_brain import Scripted

EYES = Eyes()
FIGHT = {"name": "fight the cow", "about": "x", "steps": ["click_nearest cow if idle", "wait 5"],
         "times": 40}


def view(hp, items):
    v = View(in_game=True, hp=hp)
    v.inventory = items + [None] * (28 - len(items))
    return v


def test_what_counts_as_a_death():
    full = ["bronze_axe"] + ["oak_logs"] * 10
    assert died(view(0.1, full), view(1.0, ["bronze_axe"]))
    assert not died(view(0.1, full), view(0.3, full))           # ate something
    assert not died(view(0.9, full), view(1.0, ["bronze_axe"]))  # banked
    assert not died(view(0.1, ["bronze_axe"]), view(1.0, []))   # nothing to lose: can't tell
    assert not died(View(in_game=False), view(1.0, []))


def test_a_death_mid_fight_is_noticed_told_and_counted(tmp_path):
    game = lumbridge(seed=2)
    game.give("oak_logs", 6)
    cow = next(t for t in game.things if t.name == "cow")
    cow.hp = 10 ** 6
    game.hp = 6
    memory = Memory(tmp_path / "m")
    memory.set_goal("Attack 10", "cows")
    memory.set_reflexes(0, ["trout"], 0)                        # no eating, no running: he chose
    told = []
    model = Scripted(("run_routine", FIGHT), ("wait", {"seconds": 1}))
    b = Brain(model, Actions(SimBody(game), EYES), memory, Owner(log=told.append), log=lambda s: None)
    t = b.turn()
    assert game.deaths == 1
    assert not t.ok and "stopped by a reflex: you died" in t.result
    assert any("💀 you died! Lost: " in r and "oak logs" in r for r in b.recent)
    assert any(m.startswith("[to owner] 💀 I died. Lost: ") for m in told)
    b.turn()
    assert "💀 you died!" in model.prompts[1]
    assert len(b.actions.deaths) == 1 and b.reflexes.deaths_seen == 1   # told once
    import time
    summary = daily_summary(memory, time.strftime("%Y-%m-%d"))
    assert "💀 Died 1 time." in summary and summary.startswith("📅 ") and " 2 turns" in summary
