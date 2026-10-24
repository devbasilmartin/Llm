import numpy as np
import pytest

from superbond2.actions import ACTIONS, Actions
from superbond2.eyes import Eyes
from superbond2.hands import RealBody, SimBody
from superbond2.layout import Layout
from superbond2.sim import lumbridge
from superbond2.text import MENU_FILL, Reader, split_name

EYES = Eyes()


@pytest.fixture
def game():
    return lumbridge()


@pytest.fixture
def act(game):
    return Actions(SimBody(game), EYES)


# --- survey, mark, inspect on the simulated game ----------------------------------------------
def test_survey_finds_everything_highlighted_or_not(act):
    r = act.survey()
    for name in ("Man (npc", "Door (object", "Willow tree (object", "Cow (npc", "Bank booth (object",
                 "Copper rocks (object", "Zezima (player"):
        assert name in r.said, name
    assert "Bank booth (object, behind, highlighted as bank)" in r.said
    assert "Willow tree (object, ahead)" in r.said          # not highlighted: nothing said


def test_mark_outlines_it_for_good(act, game):
    act.survey()
    assert act.view.count("marked") == 0
    r = act.mark("willow tree")
    assert r.ok and "it shows as `marked` now" in r.said
    assert act.look().count("marked") == 1
    assert act.inspect("marked").said == "that marked is Willow tree (Chop down Willow tree)"
    again = act.mark("Willow tree")
    assert not again.ok and "already marked" in again.said


def test_what_cant_be_marked(act, game):
    assert "survey first" in act.mark("Door").said
    act.survey()
    assert "only objects can be marked" in act.mark("Man").said
    assert "no Yew tree in your last survey" in act.mark("Yew tree").said
    willow = next(t for t in game.things if t.label == "Willow tree")
    willow.gone_until = 1e9                                  # chopped down since the survey
    assert "survey again" in act.mark("Willow tree").said


def test_inspect_says_what_a_shared_highlight_really_is(act):
    assert act.inspect("rock").said == "that rock is Copper rocks (Mine Copper rocks)"
    assert not act.inspect("yew_tree").ok


def test_the_brain_and_routines_get_the_right_actions():
    from superbond2.brain import TOOL_NAMES
    from superbond2.routines import ACTION_NAMES
    assert {"survey", "mark", "inspect"} <= TOOL_NAMES
    assert {a["function"]["name"] for a in ACTIONS} >= {"survey", "mark", "inspect"}
    assert "survey" not in ACTION_NAMES                      # not a routine step


# --- reading text --------------------------------------------------------------------------
def write(img, x, y, w, rgb):
    """A stand-in for a word: a block of text-colored pixels with a black shadow."""
    img[y + 1:y + 9, x + 1:x + w + 1] = (0, 0, 0)
    img[y:y + 8, x:x + w] = rgb


def test_the_name_color_says_what_kind_of_thing_it_is():
    reader = Reader(ocr=lambda pic: "Chop down Oak tree / 2 more options")
    img = np.full((503, 765, 3), (60, 90, 40), np.uint8)
    write(img, 6, 6, 40, (255, 255, 255))                    # "Chop down" in white
    write(img, 50, 6, 30, (0, 255, 255))                     # "Oak tree" in cyan
    h = reader.hover(img)
    assert (h.text, h.name, h.kind) == ("Chop down Oak tree", "Oak tree", "object")
    write(img, 50, 6, 30, (255, 255, 0))
    assert reader.hover(img).kind == "npc"


def test_nothing_under_the_mouse():
    img = np.full((503, 765, 3), (60, 90, 40), np.uint8)
    assert Reader(ocr=lambda pic: "should not be called").hover(img) is None   # no text pixels
    write(img, 6, 6, 40, (255, 255, 255))
    assert Reader(ocr=lambda pic: "Walk here").hover(img) is None


def test_the_same_text_picture_is_read_once():
    calls = []
    reader = Reader(ocr=lambda pic: calls.append(1) or "Walk here")
    img = np.full((503, 765, 3), (60, 90, 40), np.uint8)
    write(img, 6, 6, 40, (255, 255, 255))
    for _ in range(5):
        reader.hover(img)
    assert len(calls) == 1


def test_menu_rows_are_found_below_the_mouse():
    lay = Layout()
    img = np.full((503, 765, 3), (60, 90, 40), np.uint8)
    x, y = 200, 100
    img[y:y + lay.menu_header + 3 * lay.menu_row, x - 60:x + 60] = MENU_FILL
    for i in range(3):
        mid = y + lay.menu_header + i * lay.menu_row + lay.menu_row // 2
        write(img, x - 50, mid - 4, 30 + 8 * i, (255, 255, 255))   # different words, different shapes
    words = iter(["Chop down Oak tree", "Mark object", "Walk here"])
    rows = Reader(ocr=lambda pic: next(words)).menu(img, (x, y))
    assert [t for t, _ in rows] == ["Chop down Oak tree", "Mark object", "Walk here"]
    assert rows[1][1] == (x, y + lay.menu_header + lay.menu_row + lay.menu_row // 2)


@pytest.mark.parametrize("text, name", [("Chop down Oak tree", "Oak tree"), ("Mine Copper rocks", "Copper rocks"),
                                        ("Talk-to Hans", "Hans"), ("Attack Goblin (level-2)", "Goblin (level-2)")])
def test_split_name(text, name):
    assert split_name(text) == name


def test_no_tesseract_says_how_to_get_it(monkeypatch):
    import builtins
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__",
                        lambda n, *a, **k: (_ for _ in ()).throw(ImportError()) if n == "pytesseract" else real(n, *a, **k))
    from superbond2.text import tesseract
    with pytest.raises(RuntimeError, match="sudo apt install tesseract-ocr"):
        tesseract(np.zeros((4, 4), np.uint8))


# --- the real body's mouse, with a stand-in for pyautogui -------------------------------------
def test_shift_right_click_for_the_menu():
    from test_hands import FakeGui, FakeScreen
    gui = FakeGui()
    gui.click = lambda button="left": gui.calls.append(("click", button))
    body = RealBody(FakeScreen(), gui=gui)
    body.reader = type("R", (), {"menu": lambda self, img, pt: [("Mark object", (5, 30))]})()
    rows = body.open_menu((5, 5), shift=True)
    assert gui.calls == [("move", 105, 55), ("down", "shift"), ("click", "right"), ("up", "shift")]
    assert rows == [("Mark object", (5, 30))]
