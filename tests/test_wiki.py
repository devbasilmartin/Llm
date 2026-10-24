import urllib.parse

import pytest

from superbond2.wiki import MAX_TEXT, USER_AGENT, Wiki, WikiError, clip, to_text

QUEST = """{{External|rs|rsc=Vampire slayer}}
{{otheruses|the quest|the slayer task|Slayer task/Vampyres}}
{{Infobox Quest
|name = Vampyre Slayer
|image = [[File:Vampyre Slayer.png|300px]]
|release = [[28 January]] [[2001]]
|members = No
}}
'''Vampyre Slayer''' is a [[free-to-play]] [[quest]] in [[Draynor Village]]. Slay [[Count Draynor]].
"""
DETAILS = """==Details==
{{Quest details
|start = Talk to [[Morgan]] in [[Draynor Village]].
|startmap = 3098,3268
|items = *[[Hammer]] (1 [[coin]])
* [[Beer]] (2 [[coins]])
|recommended = * {{SCP|Combat|20|link=yes}}
* [[Garlic]]<ref>A note.</ref>
|kills = [[Count Draynor]] ''(level 34)''
}}
{| class="wikitable"
! a !! b
|}
[[File:Morgan chathead.png|left|frameless]]
"""
SECTIONS = [{"line": "Details", "index": "1"}, {"line": "Walkthrough", "index": "2"},
            {"line": "Count Draynor", "index": "3"}]


def fake_get(log):
    def get(url):
        q = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
        log.append(q)
        if q.get("list") == "search":
            if q["srsearch"] == "nothing here":
                return {"query": {"search": []}}
            return {"query": {"search": [
                {"title": "Vampyre Slayer", "snippet": "<span class=\"searchmatch\">Vampyre</span> Slayer is a "
                                                       "free-to-play quest &amp; more"},
                {"title": "Count Draynor", "snippet": "The Count."}]}}
        if q["page"] not in ("Vampire Slayer", "Vampyre Slayer"):
            return {"error": {"code": "missingtitle"}}
        if q["prop"] == "sections":
            return {"parse": {"title": "Vampyre Slayer", "sections": SECTIONS}}
        text = {"0": QUEST, "1": DETAILS}.get(q["section"], "==Walkthrough==\nTalk to [[Morgan]].")
        return {"parse": {"title": "Vampyre Slayer", "wikitext": {"*": text}}}
    return get


@pytest.fixture
def log():
    return []


@pytest.fixture
def wiki(log, tmp_path):
    return Wiki(tmp_path / "cache", get=fake_get(log), sleep=lambda s: None)


def test_wikitext_becomes_plain_text():
    text = to_text(QUEST + DETAILS)
    assert text.startswith("members: No\n\nVampyre Slayer is a free-to-play quest in Draynor Village. "
                           "Slay Count Draynor.")
    assert "start: Talk to Morgan in Draynor Village." in text
    assert "- Beer (2 coins)" in text and "Combat 20" in text
    assert "kills: Count Draynor (level 34)" in text
    assert "## Details" in text
    for gone in ("File:", "[[", "{{", "startmap", "release", "wikitable", "A note", "<ref"):
        assert gone not in text


def test_long_pages_are_cut():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    out = clip(text)
    assert len(out) <= MAX_TEXT + 30 and out.endswith("(...more on the page)")
    assert clip("short") == "short"


def test_search(wiki):
    out = wiki.search("vampire slayer")
    assert out.startswith("1. Vampyre Slayer: Vampyre Slayer is a free-to-play quest & more\n2. Count Draynor")
    assert "read_wiki" in out
    assert wiki.search("nothing here") == "nothing on the wiki for 'nothing here'"
    assert "search for something" in wiki.search("  ")


def test_read_follows_redirects_and_lists_sections(wiki):
    where, text = wiki.read("Vampire Slayer")
    assert where == "Vampyre Slayer"
    assert "free-to-play quest" in text
    assert text.endswith("Sections: Details, Walkthrough, Count Draynor")


def test_read_a_section_by_name_or_part_of_it(wiki):
    where, text = wiki.read("Vampyre Slayer", "details")
    assert where == "Vampyre Slayer, details" and "kills: Count Draynor" in text
    assert "Talk to Morgan" in wiki.read("Vampyre Slayer", "walk")[1]
    with pytest.raises(WikiError, match="no section 'Rewards'. Sections: Details, Walkthrough"):
        wiki.read("Vampyre Slayer", "Rewards")
    with pytest.raises(WikiError, match="no wiki page called 'Dragon Slayer 3'"):
        wiki.read("Dragon Slayer 3")


def test_cached_and_polite(log, tmp_path):
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s
    wiki = Wiki(tmp_path / "cache", get=fake_get(log), clock=lambda: t[0], sleep=sleep)
    wiki.read("Vampyre Slayer")
    assert len(log) == 2 and slept == [1.0]               # sections, then text: a second apart
    wiki.read("Vampyre Slayer")
    assert len(log) == 2                                 # from the cache


def test_the_wiki_knows_who_is_asking():
    assert "superbond2" in USER_AGENT and "github.com/devbasilmartin/Llm" in USER_AGENT
