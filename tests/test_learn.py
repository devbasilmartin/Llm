"""The learning track: fetching the wiki as text (no network: a fake API)."""
from learn.fetch_wiki import fetch, safe_name, save
from superbond2.wiki import Wiki

LONG = "'''Oak logs''' are logs obtained by cutting [[Oak tree|oak trees]]. " * 6


def page(i, title, text):
    return str(i), {"pageid": i, "title": title, "revisions": [{"slots": {"main": {"*": text}}}]}


def fake_api(urls):
    batches = [
        {"query": {"pages": dict([page(1, "Oak logs", "__NOTOC__" + LONG), page(2, "Stub", "Too short."),
                                  page(4, "Oak (disambiguation)", LONG)])},
         "continue": {"gapcontinue": "P", "continue": "gapcontinue||"}},
        {"query": {"pages": dict([page(3, "Pickaxe", LONG.replace("Oak logs", "Pickaxe"))])}},
    ]

    def get(url):
        urls.append(url)
        return batches[len(urls) - 1]
    return get


def test_fetches_in_batches_as_plain_text_and_skips_stubs():
    urls = []
    wiki = Wiki(get=fake_api(urls), clock=lambda: 0.0, sleep=lambda s: None)
    pages = fetch(wiki, 10)
    assert [t for t, _ in pages] == ["Oak logs", "Pickaxe"]
    assert "__NOTOC__" not in pages[0][1]
    assert "[[" not in pages[0][1] and "Oak logs are logs obtained by cutting oak trees" in pages[0][1]
    assert "generator=allpages" in urls[0] and "gaplimit=50" in urls[0]
    assert "gapcontinue=P" in urls[1] and len(urls) == 2


def test_stops_at_the_page_count():
    urls = []
    wiki = Wiki(get=fake_api(urls), clock=lambda: 0.0, sleep=lambda s: None)
    assert len(fetch(wiki, 1)) == 1 and len(urls) == 1


def test_saves_pages_and_one_file_to_train_on(tmp_path):
    joined = save([("Oak logs", "Logs."), ("Dragon/Slayer?", "Hard.")], tmp_path)
    assert joined.read_text() == "== Oak logs ==\nLogs.\n\n== Dragon/Slayer? ==\nHard.\n\n"
    assert (tmp_path / "wiki" / f"{safe_name('Dragon/Slayer?')}.txt").read_text() == "Hard.\n"
