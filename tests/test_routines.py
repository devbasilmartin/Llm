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


def test_a_pass_with_nothing_to_do_waits_and_tries_again():
    r = Routine.from_dict(simple_routine("oak loop", "Chop oaks as they grow back.",
                                         ["click_nearest oak_tree"], until="inventory full"))
    game = lumbridge(seed=3)
    for t in game.things:
        if t.name == "oak_tree":
            t.gone_until = 20                      # both regrowing when it starts
    result = runner(game).run(r)
    assert result.ok, result.said
    assert any("nothing to do yet" in line for line in result.log)
    assert game.inventory.count("oak_logs") == SLOTS - 4


def test_a_loop_that_never_does_anything_still_ends():
    r = Routine.from_yaml("""
name: spin
about: Never does anything.
max_actions: 20
steps:
  - repeat:
    until: inventory full
    do:
      - if: busy
        then:
          - wait: 1
""")
    result = runner(lumbridge()).run(r)
    assert not result.ok and "limit of 20 actions" in result.said


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


# --- the simple form ----------------------------------------------------------------------
from superbond2.routines import simple_routine, step_from_line  # noqa: E402


@pytest.mark.parametrize("line, step", [
    ("click_nearest oak_tree", {"if": "see oak_tree", "then": [{"click_nearest": "oak_tree"}]}),
    ("click_nearest cow if idle", {"if": "idle", "then": [{"click_nearest": "cow"}]}),
    ("  wait   2 ", {"wait": 2}),
    ("wait 2.5", {"wait": 2}),
    ("click_item trout if hp below 50%", {"if": "hp below 50%", "then": [{"click_item": "trout"}]}),
    ("stop out of food if not have trout", {"if": "not have trout", "then": [{"stop": "out of food"}]}),
    ("Drop_All oak_logs", {"drop_all": "oak_logs"}),
])
def test_one_line_steps(line, step):
    assert step_from_line(line) == step


@pytest.mark.parametrize("line, says", [
    ("chop oak_tree", "no action called 'chop'"),
    ("wait a bit", "wait needs a number"),
    ("click_nearest", "needs something after it"),
    ("", "is empty"),
])
def test_one_line_mistakes(line, says):
    with pytest.raises(RoutineError, match=says):
        step_from_line(line)


def test_simple_form_shapes():
    once = simple_routine("x y", "z", ["wait 1"])
    assert once["steps"] == [{"wait": 1}]
    loop = simple_routine("x y", "z", ["wait 1"], until="inventory full", after=["drop_all logs"], rounds=2)
    assert loop["steps"] == [{"repeat": 2, "do": [
        {"repeat": None, "until": "inventory full", "do": [{"wait": 1}]}, {"drop_all": "logs"}]}]
    assert simple_routine("x y", "z", ["wait 1"], times=4)["steps"] == [{"repeat": 4, "do": [{"wait": 1}]}]
    assert simple_routine("x y", "z", "wait 1; wait 2")["steps"] == [{"wait": 1}, {"wait": 2}]
    with pytest.raises(RoutineError, match="at least one step"):
        simple_routine("x y", "z", [])
    for r in (once, loop):
        Routine.from_dict(r)                    # they're real routines


def test_a_simple_routine_runs():
    r = Routine.from_dict(simple_routine(
        "chop and drop oaks", "Chop oaks until full, then drop the logs.",
        ["click_nearest oak_tree if idle and see oak_tree", "wait 2"],
        until="inventory full", after=["drop_all oak_logs"], rounds=2))
    result = runner(lumbridge(seed=4)).run(r)
    assert result.ok, result.said
    assert sum("dropped" in line for line in result.log) == 2


def test_conditions_take_names_with_spaces():
    assert condition("have oak logs")(view(inventory=["oak_logs"] + [None] * 27))
    assert condition("idle and not see oak tree")(view())


def test_the_summary_says_what_came_in_along_the_way():
    r = Routine.from_dict(simple_routine(
        "chop and drop oaks", "Chop, then drop.", ["click_nearest oak_tree if idle and see oak_tree", "wait 2"],
        until="inventory full", after=["drop_all oak logs"]))
    result = runner(lumbridge(seed=4)).run(r)
    assert f"Gained along the way: +{SLOTS - 4} oak logs." in result.said
    assert result.said.endswith("Inventory now vs. before: nothing changed")


def test_stray_empty_steps_are_skipped():
    r = simple_routine("chop", "x", ["click_nearest oak_tree", "", "wait 2", "  "], after=["", "click_nearest bank"])
    assert len(r["steps"]) == 3
