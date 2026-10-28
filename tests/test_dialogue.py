"""Reading dialogue: the eyes see it's open, the reader reads it, the prompt shows it."""
from superbond2.actions import Actions
from superbond2.eyes import Eyes, describe
from superbond2.hands import SimBody
from superbond2.sim import lumbridge
from superbond2.text import Reader

EYES = Eyes()
MORGAN = {"speaker": "Morgan", "more": True,
          "text": "Please help us, a vampyre is terrorising Draynor Village! Will you help us?"}


def test_he_sees_who_says_what():
    game = lumbridge()
    act = Actions(SimBody(game), EYES)
    assert not act.look().dialogue_open and act.view.dialogue is None
    game.dialogue = MORGAN
    view = act.look()
    assert view.dialogue_open and view.dialogue.speaker == "Morgan" and view.dialogue.more
    assert 'Dialogue: Morgan: "Please help us, a vampyre' in describe(view)
    assert "(more: press space to continue)" in describe(view)


def test_options_are_numbered():
    game = lumbridge()
    game.dialogue = {"options": ["Yes, I'll help.", "No, sorry.", "What's a vampyre?"]}
    text = describe(Actions(SimBody(game), EYES).look())
    assert "Dialogue: choose one: 1. Yes, I'll help.; 2. No, sorry.; 3. What's a vampyre?" in text


def test_the_reader_finds_the_lines_on_the_picture():
    """The real client's reader, on the sim's drawing of a dialogue, with a stand-in for
    Tesseract that hands back the words in reading order."""
    game = lumbridge()
    game.dialogue = {"options": ["Yes, I'll help.", "No, sorry."]}
    words = iter(["Select an Option", "Yes, I'll help.", "No, sorry."])
    d = Reader(ocr=lambda pic: next(words)).dialogue(game.grab())
    assert d.speaker == "" and [t for t, _ in d.options] == ["Yes, I'll help.", "No, sorry."]
    assert [at for _, at in d.options] == [at for _, at in game.read_dialogue().options]

    game.dialogue = MORGAN
    words = iter(["Morgan", "Please help us, a vampyre is terrorising Draynor", "Village! Will you help us?"])
    d = Reader(ocr=lambda pic: next(words)).dialogue(game.grab())
    assert d.speaker == "Morgan" and d.more and d.text.endswith("Will you help us?")


def test_no_dialogue_reads_nothing():
    assert Reader(ocr=lambda pic: "should not be called").dialogue(lumbridge().grab()) is None


# --- talking -------------------------------------------------------------------------------
def morgan_scene():
    from superbond2.sim import SimGame
    g = SimGame(seed=1)
    g.add("quest_dialog", "npc", 200, 120, 16, 30, label="Morgan", verb="Talk-to", talk={
        "start": [("say", "Morgan", "Please help us, a vampyre is terrorising Draynor!"),
                  ("choose", [("Yes, I'll help.", "yes"), ("No, sorry.", "no")])],
        "yes": [("say", "Morgan", "Thank you! Take this garlic."), ("give", "garlic"),
                ("flag", "vampyre slayer started")],
        "no": [("say", "Morgan", "Oh... alright.")]})
    return g


def test_a_conversation_from_start_to_finish():
    game = morgan_scene()
    act = Actions(SimBody(game), EYES)
    r = act.talk_to("Morgan")                                # her game name: found by hovering
    assert r.ok and r.said == 'talking to Morgan: Morgan: "Please help us, a vampyre is terrorising Draynor!" (more)'
    assert act.continue_dialogue().said == "next: choose one: 1. Yes, I'll help.; 2. No, sorry."
    r = act.choose("yes")
    assert r.said == "chose 1. Yes, I'll help.; now Morgan: \"Thank you! Take this garlic.\" (more)"
    r = act.continue_dialogue()
    assert r.said == "next: nobody's talking now"
    assert "garlic" in game.inventory and "vampyre slayer started" in game.flags


def test_talking_mistakes_say_what_to_do():
    game = morgan_scene()
    act = Actions(SimBody(game), EYES)
    assert not act.continue_dialogue().ok and not act.choose("1").ok
    assert act.talk_to("Hans").said.startswith("no Hans in sight (I can see: quest_dialog)")
    act.talk_to("quest_dialog")                              # the highlight name works too
    act.continue_dialogue()
    r = act.choose("maybe")
    assert not r.ok and r.said == "no option 'maybe'; the options: 1. Yes, I'll help.; 2. No, sorry."
    assert act.choose(2).ok and "nothing" not in game.flags


def test_a_routine_can_hold_a_conversation():
    from superbond2.routines import Runner, simple_routine, Routine
    game = morgan_scene()
    act = Actions(SimBody(game), EYES)
    r = Routine.from_dict(simple_routine("ask morgan", "Start the quest.",
                                         ["talk_to Morgan", "continue_dialogue", "choose 1", "continue_dialogue"]))
    result = Runner(act).run(r)
    assert result.ok and "garlic" in game.inventory
