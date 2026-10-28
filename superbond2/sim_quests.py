"""Quests in the simulated game, to try everything together before the real one.

Vampyre Slayer, the way the game tells it, shortened: Morgan in Draynor Village asks for
help; garlic is in his cupboard upstairs; Dr Harlow in the Blue Moon Inn, Varrock, wants a
beer before he hands over a stake; a hammer turns up near the inn; Count Draynor waits in the
basement of Draynor Manor and can't be killed without the stake and hammer. 3 quest points.
"""
from __future__ import annotations

from .sim import SimGame

MORGAN = (3098, 3268, 0)
UPSTAIRS = (3098, 3268, 1)
INN = (3224, 3398, 0)
MANOR = (3109, 3350, 0)
BASEMENT = (3077, 9771, 0)

MORGAN_TALK = {
    "start": [("if", "vampyre slayer started", "again"),
              ("say", "Morgan", "Please help us! A vampyre is killing the people of Draynor."),
              ("choose", [("Yes, I'll help.", "yes"), ("No, sorry.", "no")])],
    "yes": [("say", "Morgan", "Thank you! Find Dr Harlow in the Blue Moon Inn, Varrock: he knows "
                              "how to kill vampyres. And take the garlic from my cupboard upstairs."),
            ("flag", "vampyre slayer started")],
    "no": [("say", "Morgan", "Please, think about it.")],
    "again": [("if", "vampyre slayer done", "thanks"),
              ("say", "Morgan", "Have you killed the vampyre yet? Dr Harlow is in the Blue Moon Inn.")],
    "thanks": [("say", "Morgan", "Thank you, hero! Draynor is safe.")],
}
HARLOW_TALK = {
    "start": [("if", "harlow helped", "again"),
              ("say", "Dr Harlow", "Hic! Buy an old man a drink?"),
              ("need", "beer", "nobeer"), ("take", "beer"), ("give", "stake"), ("flag", "harlow helped"),
              ("say", "Dr Harlow", "Ah, that's better. Here's a stake. Once the Count is down, "
                                   "hammer it into his heart, or he'll rise again.")],
    "nobeer": [("say", "Dr Harlow", "No beer, no help. Hic.")],
    "again": [("say", "Dr Harlow", "Stake and hammer, lad. Stake and hammer.")],
}
BARTENDER_TALK = {
    "start": [("say", "Bartender", "What'll it be?"),
              ("choose", [("A beer, please. (2 coins)", "beer"), ("Nothing, thanks.", "bye")])],
    "beer": [("need", "coins", "broke"), ("take", "coins"), ("give", "beer"),
             ("say", "Bartender", "There you go.")],
    "broke": [("say", "Bartender", "No coins, no beer.")],
    "bye": [("say", "Bartender", "Suit yourself.")],
}
COUNT_TALK = {
    "defeated": [("say", "Count Draynor", "Aaargh! The stake... the hammer..."),
                 ("flag", "vampyre slayer done"), ("qp", 3),
                 ("say", "Quest complete", "Vampyre Slayer done! 3 quest points.")],
}


def vampyre_world(seed: int = 1) -> SimGame:
    """Lumbridge to start, with Vampyre Slayer laid out across Draynor and Varrock."""
    from .sim import lumbridge
    g = lumbridge(seed)
    g.give("coins")
    g.add("quest_dialog", "npc", 150, 120, 16, 30, label="Morgan", verb="Talk-to", talk=MORGAN_TALK,
          at=MORGAN)
    g.add("door", "static", 300, 100, 24, 40, label="Staircase", verb="Climb-up", marked=False,
          at=MORGAN, goes=UPSTAIRS)
    g.add("door", "static", 300, 100, 24, 40, label="Staircase", verb="Climb-down", marked=False,
          at=UPSTAIRS, goes=MORGAN)
    g.add("door", "static", 120, 60, 26, 30, label="Cupboard", verb="Search", marked=False,
          gives="garlic", at=UPSTAIRS)
    g.add("quest_dialog", "npc", 120, 120, 16, 30, label="Dr Harlow", verb="Talk-to",
          talk=HARLOW_TALK, at=INN)
    g.add("quest_dialog", "npc", 330, 110, 16, 30, label="Bartender", verb="Talk-to",
          talk=BARTENDER_TALK, at=INN)
    g.add("loot", "loot", 220, 250, 18, 10, gives="hammer", at=INN)
    g.add("door", "static", 400, 80, 30, 30, label="Stairs", verb="Climb-down", marked=False,
          at=MANOR, goes=BASEMENT)
    g.add("enemy", "monster", 240, 120, 18, 34, label="Count Draynor", verb="Attack", hp=25,
          needs=("stake", "hammer"), talk=COUNT_TALK, at=BASEMENT, respawn=1e12)
    return g
