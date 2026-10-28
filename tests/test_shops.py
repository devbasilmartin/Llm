"""Shops: trade, buy in 1/5/10/50s, sell, and a wiki-value guard on selling valuables."""
from superbond2.actions import Actions
from superbond2.eyes import Eyes, describe
from superbond2.hands import SimBody
from superbond2.sim import SimGame
from superbond2.wiki import Wiki

EYES = Eyes()


def store():
    g = SimGame(seed=1)
    g.add("quest_dialog", "npc", 200, 120, 16, 30, label="Shop keeper", verb="Talk-to",
          shop={"bronze_pickaxe": 1, "tinderbox": 1, "pot": 1})
    g.give("coins", 20)
    g.give("cowhide", 2)
    g.give("rune_pickaxe")
    return g


def test_buy_some():
    game = store()
    act = Actions(SimBody(game), EYES)
    assert act.trade("Shop keeper").ok
    assert "A shop is open" in describe(act.view)
    r = act.buy("tinderbox", 7)                          # 5 + 1 + 1
    assert r.ok and game.inventory.count("tinderbox") == 7 and game.coins == 13


def test_sell_and_the_guard():
    game = store()
    act = Actions(SimBody(game), EYES)
    act.value_of = {"rune_pickaxe": 32000, "cowhide": 1}.get
    act.trade("Shop keeper")
    r = act.sell("cowhide", 2)
    assert r.ok and "cowhide" not in game.inventory
    r = act.sell("rune pickaxe", 1)
    assert not r.ok and "worth about 32,000 coins" in r.said and "rune_pickaxe" in game.inventory
    assert act.sell("rune pickaxe", 1, sure="yes").ok and "rune_pickaxe" not in game.inventory


def test_shop_mistakes():
    act = Actions(SimBody(store()), EYES)
    assert act.buy("pot").said.startswith("no shop is open")
    act.trade("Shop keeper")
    r = act.buy("rune scimitar")
    assert not r.ok and "it sells: bronze_pickaxe, tinderbox, pot" in r.said
    act.press("esc")
    assert not act.look().shop_open


def test_the_wikis_value():
    raw = {"Rune pickaxe": "{{Infobox Item\n|name = Rune pickaxe\n|value = 32,000\n}}\nA pickaxe."}

    def get(url):
        title = next((t for t in raw if t.replace(" ", "+").lower() in url.lower()), None)
        return {"parse": {"wikitext": {"*": raw[title]}}} if title else {"error": {"code": "missingtitle"}}
    wiki = Wiki(get=get, clock=lambda: 0.0, sleep=lambda s: None)
    assert wiki.value("rune_pickaxe") == 32000
    assert wiki.value("Nonsense item") is None
