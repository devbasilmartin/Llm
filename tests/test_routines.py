import pytest

from superbond2.actions import Actions
from superbond2.eyes import Eyes, View
from superbond2.hands import SimBody
from superbond2.layout import SLOTS
from superbond2.routines import Library, Routine, RoutineError, Runner, condition
from superbond2.sim import SimGame, lumbridge

EYES = Eyes()

CHOP_AND_BANK = """
name: chop oaks and bank
about: Chop oaks until the inventory is full, then bank. Twice.
steps:
  - repeat: 2
    do:
      - repeat:
        until: inventory full
        do:
          - if: idle and see oak_tree
            then:
              - click_nearest: oak_tree
          - wait: 2
      - click_nearest: bank
"""


def runner(game, **kw):
    return Runner(Actions(SimBody(game), EYES), **kw)


def view(**kw):
    v = View(in_game=True, hp=1.0, busy=False)
    for k, val in kw.items():
        setattr(v, k, val)
    return v


# --- conditions ---------------------------------------------------------------------------
def test_conditions_read_the_view():
    full = view(inventory=["oak_logs"] * SLOTS)
    assert condition("inventory full")(full)
    assert not condition("inventory empty")(full)
    assert condition("free slots below 5")(view(inventory=["logs"] * 25 + [None] * 3))
    assert condition("idle")(view()) and not condition("busy")(view())
    assert not condition("idle")(view(busy=None))          # unknown isn't idle
    assert condition("hp below 50%")(view(hp=0.3)) and condition("hp above 20%")(view(hp=0.3))
    assert not condition("hp below 50%")(view(hp=None))
    assert condition("have trout")(view(inventory=["trout"] + [None] * 27))
    assert condition("not see oak_tree")(view())
    assert condition("Idle AND not have trout")(view())


def test_unknown_conditions_list_the_known_ones():
    with pytest.raises(RoutineError, match="Conditions are: inventory full"):
        condition("inventory nearly full")


# --- checking what he writes ----------------------------------------------------------------
@pytest.mark.parametrize("text, says", [
    ("name: x\nabout: y\nsteps: []", "should be 2-60 lower-case"),
    ("name: ok name\nabout: ''\nsteps: [{wait: 1}]", "`about:` should say"),
    ("name: ok name\nabout: y\nsteps: []", "must be a list with at least one step"),
    ("name: ok name\nabout: y\nsteps: [{fly: home}]", "no action or step called 'fly'"),
    ("name: ok name\nabout: y\nsteps: [{wait: soon}]", "wait needs a number"),
    ("name: ok name\nabout: y\nsteps: [{click_nearest: oak_tree, wait: 2}]", "one action per step"),
    ("name: ok name\nabout: y\nsteps: [{repeat: forever, do: [{wait: 1}]}]", "needs a number 1-100"),
    ("name: ok name\nabout: y\nsteps: [{if: hungry, then: [{wait: 1}]}]", "condition 'hungry'"),
    ("name: ok name\nabout: y\nsteps: [{if: idle}]", "an if has `if:`, `then:`"),
    ("name: ok name\nabout: y\nsteps: [{wait: 1}]\ncolour: red", "unknown keys: colour"),
    ("name: ok name\nabout: y\nsteps: [{wait: 1}", "isn't valid YAML"),
])
def test_mistakes_get_a_message_that_says_what_to_fix(text, says):
    with pytest.raises(RoutineError, match=says.replace("(", r"\(").replace(")", r"\)")):
        Routine.from_yaml(text)


def test_too_big_or_too_deep_is_refused():
    many = "name: ok name\nabout: y\nsteps:\n" + "  - wait: 1\n" * 41
    with pytest.raises(RoutineError, match="too many steps"):
        Routine.from_yaml(many)
    deep = {"wait": 1}
    for _ in range(5):
        deep = {"repeat": 2, "do": [deep]}
    with pytest.raises(RoutineError, match="too deeply nested"):
        Routine.from_dict({"name": "deep one", "about": "y", "steps": [deep]})


# --- running ------------------------------------------------------------------------------
def test_chop_and_bank_twice():
    game = lumbridge(seed=2)
    result = runner(game).run(Routine.from_yaml(CHOP_AND_BANK))
    assert result.ok, result.said
    assert "done after" in result.said
    assert game.bank["oak_logs"] >= 2 * (SLOTS - 4)          # two full loads banked
    assert any("you're busy now" in line for line in result.log)


def test_a_failed_action_stops_it_and_says_where():
    game = SimGame(seed=1)
    game.add("bank", "bank", 300, 260, 40, 40)
    r = Routine.from_yaml("name: chop\nabout: chop an oak\nsteps:\n  - click_nearest: oak_tree\n")
    result = runner(game).run(r)
    assert not result.ok
    assert "`click_nearest: oak_tree` failed: no oak_tree in sight (I can see: bank)" in result.said


def test_stop_ends_it_early():
    r = Routine.from_yaml("""
name: eat or stop
about: Eat if I can, otherwise stop.
steps:
  - if: have trout
    then:
      - click_item: trout
    else:
      - stop: out of food
  - wait: 1
""")
    game = lumbridge()
    game.inventory = [None] * SLOTS
    result = runner(game).run(r)
    assert result.ok and "stopped (out of food) after 0 actions" in result.said


def test_a_loop_without_actions_is_caught():
    r = Routine.from_yaml("""
name: spin
about: Never does anything.
steps:
  - repeat:
    until: inventory full
    do:
      - if: busy
        then:
          - wait: 1
""")
    result = runner(lumbridge()).run(r)
    assert not result.ok and "did a pass without any action" in result.said


def test_limits_on_actions_and_time():
    forever = "name: forever\nabout: y\nmax_actions: 5\nsteps:\n  - repeat:\n    until: inventory full\n    do:\n      - wait: 1\n"
    result = runner(lumbridge()).run(Routine.from_yaml(forever))
    assert not result.ok and "limit of 5 actions" in result.said and result.actions == 5

    ticks = iter(range(0, 10_000, 60))                     # each look of the clock: +1 minute
    timed = forever.replace("max_actions: 5", "max_minutes: 3")
    result = runner(lumbridge(), clock=lambda: next(ticks)).run(Routine.from_yaml(timed))
    assert not result.ok and "limit of 3 minutes" in result.said


def test_a_reflex_can_stop_a_routine():
    game = lumbridge()
    game.hp = 8
    fight = "name: fight\nabout: y\nsteps:\n  - click_nearest: cow\n  - wait: 30\n"
    guard = lambda v: "HP below 30%" if v.hp is not None and v.hp < 0.3 else None
    result = runner(game, guard=guard).run(Routine.from_yaml(fight))
    assert not result.ok and "stopped by a reflex: HP below 30%" in result.said
    assert result.actions == 1


# --- the library --------------------------------------------------------------------------
def test_library_saves_loads_and_keeps_score(tmp_path):
    lib = Library(tmp_path)
    r = lib.save(CHOP_AND_BANK)
    assert lib.names() == ["chop oaks and bank"]
    assert lib.load("chop oaks and bank").about == r.about
    result = runner(lumbridge(seed=2)).run(lib.load("chop oaks and bank"))
    lib.record(r, result)
    assert lib.stats("chop oaks and bank")["worked"] == 1
    lib.save(CHOP_AND_BANK.replace("Twice.", "Two loads."))      # rewritten: stats stay
    assert lib.stats("chop oaks and bank")["runs"] == 1
    assert "chop oaks and bank: Chop oaks until the inventory is full, then bank. Two loads. " \
           "(ran 1x, worked 1, failed 0)" in lib.summary()
    with pytest.raises(RoutineError, match="no routine called 'mine'.*chop oaks and bank"):
        lib.load("mine")


def test_a_bad_routine_isnt_saved(tmp_path):
    lib = Library(tmp_path)
    with pytest.raises(RoutineError):
        lib.save("name: bad one\nabout: y\nsteps: [{fly: home}]")
    assert lib.names() == [] and lib.summary() == "(no routines saved yet)"
