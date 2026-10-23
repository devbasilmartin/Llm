import numpy as np
import pytest

from superbond2.colors import Registry
from superbond2.eyes import UNTAGGED, Eyes, describe
from superbond2.layout import CANVAS_H, CANVAS_W, SLOTS
from superbond2.screen import find_canvas
from superbond2.sim import GRASS, INK, PANEL, PLAYER, SPRITE, SimGame, lumbridge

REG = Registry.load()


@pytest.fixture
def eyes():
    return Eyes(REG)


def test_world_colors_in_one_area_cant_be_mistaken_for_each_other():
    tol = Eyes(REG).world_tol
    world = REG.world("default")
    for i, a in enumerate(world):
        for b in world[i + 1:]:
            assert np.abs(np.subtract(a.rgb, b.rgb)).max() > tol, (a.name, b.name)


def test_the_sims_own_colors_arent_highlight_colors(eyes):
    for c in REG.world("default"):
        for bg in (GRASS, PANEL, PLAYER, SPRITE, INK):
            assert np.abs(np.subtract(c.rgb, bg)).max() > eyes.world_tol, (c.name, bg)


def test_sees_every_highlight_with_its_name(eyes):
    view = eyes.look(lumbridge().grab())
    assert view.in_game
    counts = {n: view.count(n) for n in ("oak_tree", "tree", "rock", "cow", "bank", "other_player")}
    assert counts == {"oak_tree": 2, "tree": 1, "rock": 1, "cow": 1, "bank": 1, "other_player": 1}
    assert len(view.highlights) == 7
    assert [h.distance for h in view.highlights] == sorted(h.distance for h in view.highlights)


def test_highlight_boxes_cover_the_object(eyes):
    game = lumbridge()
    bank = next(t for t in game.things if t.name == "bank")
    found = eyes.look(game.grab()).nearest("bank").box
    assert abs(found.x - bank.box.x) <= 1 and abs(found.y - bank.box.y) <= 1
    assert abs(found.w - bank.box.w) <= 2 and abs(found.h - bank.box.h) <= 2


def test_reads_the_inventory_tags_and_sees_untagged_items(eyes):
    game = SimGame(REG)
    game.give("bronze_axe", tool=True)
    game.give("oak_logs", 5)
    game.give("trout", 2)
    view = eyes.look(game.grab())
    assert view.inventory[:8] == [UNTAGGED] + ["oak_logs"] * 5 + ["trout"] * 2
    assert view.inventory[8:] == [None] * (SLOTS - 8)
    assert view.free_slots == SLOTS - 8
    assert view.slots_with("trout") == [6, 7]


@pytest.mark.parametrize("hp", [40, 31, 10, 1])
def test_reads_hp_from_the_health_bar(eyes, hp):
    game = SimGame(REG)
    game.hp = hp
    assert eyes.look(game.grab()).hp == pytest.approx(hp / 40, abs=0.02)


def test_no_health_bar_means_unknown_hp(eyes):
    img = SimGame(REG).grab()
    bar = eyes.layout.hp_bar
    img[bar.y:bar.y + bar.h, bar.x:bar.x + bar.w] = PANEL
    assert eyes.look(img).hp is None


def test_busy_while_chopping_idle_when_stopped(eyes):
    game = lumbridge()
    assert eyes.look(game.grab()).busy is None           # nothing to compare with yet
    assert eyes.look(game.grab()).busy is False
    game.click(game.things[0].box.center)
    flips = []
    for _ in range(4):
        game.advance(0.6)
        flips.append(eyes.look(game.grab()).busy)
    assert all(flips)
    game.key("esc")
    eyes.look(game.grab())
    assert eyes.look(game.grab()).busy is False


def test_off_the_game_screen_sees_nothing(eyes):
    view = eyes.look(np.zeros((CANVAS_H, CANVAS_W, 3), np.uint8))
    assert not view.in_game and view.highlights == [] and view.hp is None
    assert describe(view).startswith("Screen: not in the game")


def test_describe_is_short_and_readable(eyes):
    game = lumbridge()
    game.give("oak_logs", 4)
    eyes.look(game.grab())
    text = describe(eyes.look(game.grab()))
    assert "HP: 100%" in text
    assert "You are: idle" in text
    assert "Inventory: 8/28: 4 oak logs, 3 trout, 1 untagged" in text
    assert "2 oak tree" in text and "1 bank" in text and "1 other player" in text


def test_finds_the_canvas_anywhere_on_the_desktop():
    rng = np.random.default_rng(0)
    desktop = rng.integers(0, 255, (900, 1400, 3), dtype=np.uint8)
    desktop[45:45 + CANVAS_H, 123:123 + CANVAS_W] = lumbridge().grab()
    at, share = find_canvas(desktop)
    assert at == (123, 45) and share > 0.99


def test_no_canvas_on_the_desktop_finds_nothing():
    rng = np.random.default_rng(0)
    at, _ = find_canvas(rng.integers(0, 255, (700, 1000, 3), dtype=np.uint8))
    assert at is None
