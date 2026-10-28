"""The Grand Exchange: buy, sell, collect, and the price guards (high alchemy and the going rate)."""
from superbond2.actions import Actions
from superbond2.eyes import Eyes, describe
from superbond2.hands import SimBody
from superbond2.sim import SimGame
from superbond2.wiki import Wiki

EYES = Eyes()


def exchange():
    g = SimGame(seed=1)
    g.add("quest_dialog", "npc", 200, 120, 16, 30, label="Grand Exchange Clerk", verb="Talk-to",
          options=("Exchange",))
    g.market = {"iron_ore": 120, "rune_pickaxe": 20000, "feather": 3}
    g.give("coins", 10000)
    g.give("rune_pickaxe")
    for _ in range(5):
        g.give("iron_ore")
    return g


def act_on(g):
    a = Actions(SimBody(g), EYES)
    a.value_of = {"rune_pickaxe": 32000, "iron_ore": 17, "feather": 2}.get
    a.ge_price_of = {"rune_pickaxe": 19500, "iron_ore": 118, "feather": 3}.get
    return a


def test_buy_collect_and_sell():
    g = exchange()
    act = act_on(g)
    r = act.ge_buy("feather", 1000, 4)
    assert r.ok and "offered to buy 1000 feather at 4 each" in r.said and g.coins == 6000
    assert "The Grand Exchange is open" in describe(act.view)
    assert act.ge_sell("iron ore", 5, 115).ok
    act.ge_collect()
    assert g.inventory.count("feather") >= 1 and g.coins == 6000 + 5 * 115


def test_an_offer_that_doesnt_fill_waits():
    g = exchange()
    act = act_on(g)
    act.ge_sell("iron ore", 5, 300)                       # asking too much: no buyer
    act.ge_collect()
    assert g.coins == 10000 and not g.offers[0]["filled"]


def test_the_1_gp_scam_and_other_bad_prices_are_refused():
    g = exchange()
    act = act_on(g)
    r = act.ge_sell("rune pickaxe", 1, 1)
    assert not r.ok and "under rune pickaxe's high alchemy value (19,200)" in r.said
    assert "rune_pickaxe" in g.inventory and not g.offers
    r = act.ge_buy("feather", 100, 50)
    assert not r.ok and "far over the going price (about 3 in the real game" in r.said
    assert act.ge_sell("rune pickaxe", 1, 1, sure="yes").ok         # he can, if he means it


def test_no_clerk_no_exchange():
    g = SimGame(seed=1)
    g.give("coins", 100)
    r = act_on(g).ge_buy("feather", 10, 3)
    assert not r.ok and "no Grand Exchange clerk in sight" in r.said


def test_the_wikis_live_price():
    responses = {"/mapping": [{"id": 314, "name": "Feather", "value": 2}],
                 "/latest?id=314": {"data": {"314": {"high": 4, "low": 2}}}}

    def get(url):
        return next(v for k, v in responses.items() if url.endswith(k))
    wiki = Wiki(get=get, clock=lambda: 0.0, sleep=lambda s: None)
    assert wiki.ge_price("feather") == 3 and wiki.ge_price("Nonsense") is None


def test_the_real_body_only_types_names_and_numbers():
    import pytest
    from superbond2.hands import RealBody
    from test_hands import FakeGui, FakeScreen
    gui = FakeGui()
    gui.write = lambda text, interval=0: gui.calls.append(("write", text))
    body = RealBody(FakeScreen(), gui=gui)
    body._type_checked("rune pickaxe")
    body._type_checked("20000")
    assert ("write", "rune pickaxe") in gui.calls and ("write", "20000") in gui.calls
    for bad in ("hi everyone\n", "::yell", "a" * 41, ""):
        with pytest.raises(ValueError):
            body._type_checked(bad)
