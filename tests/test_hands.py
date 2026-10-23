import numpy as np
import pytest

from superbond2.actions import ACTIONS, Actions, changes, do
from superbond2.eyes import Eyes
from superbond2.hands import RealBody, SimBody, Stopped
from superbond2.sim import lumbridge

EYES = Eyes()


@pytest.fixture
def game():
    return lumbridge()


@pytest.fixture
def act(game):
    return Actions(SimBody(game), EYES)


def test_clicking_an_oak_starts_chopping_and_waiting_ends_with_logs(act, game):
    r = act.click_nearest("oak_tree")
    assert r.ok and "you're busy now" in r.said
    r = act.wait_until_idle(timeout=300)
    assert r.ok and "oak logs" in r.said
    assert game.doing is None


def test_something_not_in_sight_says_what_is(act):
    r = act.click_nearest("yew_tree")
    assert not r.ok
    assert r.said.startswith("no yew_tree in sight (I can see: bank, cow, oak_tree")


def test_drop_all_and_eat(act, game):
    game.give("oak_logs", 5)
    r = act.drop_all("oak_logs")
    assert r.ok and "-5 oak logs" in r.said and act.view.items()["oak_logs"] == 0
    game.hp = 10
    r = act.click_item("trout")
    assert r.ok and "-1 trout" in r.said and "HP 25% -> 42%" in r.said
    assert not act.click_item("lobster").ok
    assert not act.drop_all("lobster").ok


def test_esc_stops_chopping(act, game):
    act.click_nearest("oak_tree")
    r = act.press("esc")
    assert r.ok and game.doing is None
    assert not act.press("f").ok


def test_bank_and_loot_reports(act, game):
    game.give("oak_logs", 3)
    r = act.click_nearest("bank")
    assert "-3 oak logs" in r.said and "-3 trout" in r.said
    act.click_nearest("cow")
    r = act.wait_until_idle(timeout=300)
    assert "1 loot appeared" in r.said
    r = act.click_nearest("loot")
    assert "+1 cowhide" in r.said and "1 loot gone" in r.said


def test_slots_and_waiting(act, game):
    assert not act.click_slot(28).ok
    game.hp = 10
    r = act.click_slot(1)                       # a trout
    assert r.ok and "-1 trout" in r.said
    r = act.wait(5)
    assert r.said == "waited 5s: nothing changed"


def test_the_brain_calls_actions_by_name(act):
    assert {a["function"]["name"] for a in ACTIONS} == \
        {"click_nearest", "click_item", "click_slot", "drop_all", "press", "wait", "wait_until_idle"}
    assert all(a["function"]["description"] for a in ACTIONS)
    assert do(act, "click_nearest", {"name": "bank"}).ok
    assert not do(act, "fly", {}).ok
    assert "wrong arguments" in do(act, "click_nearest", {"target": "bank"}).said


def test_leaving_the_game_is_reported(act):
    before = act.look()
    after = EYES.look(np.zeros((503, 765, 3), np.uint8))
    assert changes(before, after) == "the game is no longer on screen"


# --- the real body, with a stand-in for pyautogui ------------------------------------------
class FakeGui:
    class FailSafeException(Exception):
        pass

    def __init__(self):
        self.pos, self.calls = (500, 400), []

    def position(self):
        return self.pos

    def size(self):
        return 1280, 800

    def moveTo(self, x, y, duration=0):
        self.calls.append(("move", x, y))
        self.pos = (x, y)

    def click(self):
        self.calls.append(("click",))

    def keyDown(self, k):
        self.calls.append(("down", k))

    def keyUp(self, k):
        self.calls.append(("up", k))

    def press(self, k):
        self.calls.append(("press", k))


class FakeScreen:
    def to_screen(self, pt):
        return pt[0] + 100, pt[1] + 50

    def grab(self):
        return None


def test_real_body_clicks_where_the_canvas_is():
    gui = FakeGui()
    body = RealBody(FakeScreen(), gui=gui)
    body.click((10, 20))
    body.click((30, 40), shift=True)
    body.key("space")
    assert gui.calls == [("move", 110, 70), ("click",),
                         ("move", 130, 90), ("down", "shift"), ("click",), ("up", "shift"),
                         ("press", "space")]
    with pytest.raises(ValueError):
        body.key("f")                           # no typing, so no chatting


@pytest.mark.parametrize("corner", [(0, 0), (1279, 0), (2, 799), (1279, 798)])
def test_mouse_in_a_corner_stops_everything(corner):
    gui = FakeGui()
    body = RealBody(FakeScreen(), gui=gui)
    gui.pos = corner
    for act in (body.grab, lambda: body.click((5, 5)), lambda: body.key("esc"), lambda: body.wait(1)):
        with pytest.raises(Stopped):
            act()
    assert gui.calls == []


def test_an_edge_is_not_a_corner():
    gui = FakeGui()
    gui.pos = (0, 400)
    RealBody(FakeScreen(), gui=gui).click((5, 5))
    assert gui.calls[-1] == ("click",)


def test_pyautoguis_own_failsafe_also_stops():
    gui = FakeGui()

    def boom(*a, **k):
        raise FakeGui.FailSafeException()
    gui.moveTo = boom
    with pytest.raises(Stopped):
        RealBody(FakeScreen(), gui=gui).click((5, 5))
