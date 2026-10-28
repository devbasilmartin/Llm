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
