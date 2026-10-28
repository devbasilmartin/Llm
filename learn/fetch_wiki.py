"""Step 1 of the learning track: OSRS Wiki pages as plain text, to train a tiny model on.

    python -m learn.fetch_wiki                 # 300 pages into learn/data/
    python -m learn.fetch_wiki --pages 1000 --start "Dragon"

It asks the wiki's API for 50 pages' text at a time (so 300 pages is 6 requests), with the
same manners as superbond2's wiki tools: a User-Agent that says who's asking, at most one
request a second, and a week's cache. The text is the OSRS Wiki's, under CC BY-NC-SA 3.0:
fine for learning at home, and it stays out of git (learn/data/ is ignored).

Out come learn/data/wiki/<page>.txt, one per page, and learn/data/wiki.txt, all of them
joined, for training.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from superbond2.wiki import Wiki, to_text

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BATCH = 50                      # pages per request: the API's limit for page text
MIN_CHARS = 200                 # shorter than this is a stub or a list: not much to learn from
SKIP = re.compile(r"\((disambiguation|interface item|flatpack)\)$")   # lists and copies
MAGIC = re.compile(r"__[A-Z]+__")                                     # __NOTOC__ and friends


def safe_name(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _()'-]", "_", title).strip()[:100] or "page"


def fetch(wiki: Wiki, pages: int, start: str = "") -> list[tuple[str, str]]:
    """(title, plain text) for up to `pages` articles, in the wiki's alphabetical order."""
    out: list[tuple[str, str]] = []
    params = {"action": "query", "generator": "allpages", "gapnamespace": 0,
              "gapfilterredir": "nonredirects", "gaplimit": BATCH, "prop": "revisions",
              "rvprop": "content", "rvslots": "main"}
    if start:
        params["gapfrom"] = start
    cont: dict = {}
    while len(out) < pages:
        data = wiki._api(**params, **cont)
        found = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p["title"])
        for page in found:
            if SKIP.search(page["title"]):
                continue
            revs = page.get("revisions") or [{}]
            wikitext = revs[0].get("slots", {}).get("main", {}).get("*") or revs[0].get("*") or ""
            text = MAGIC.sub("", to_text(wikitext)).strip()
            if len(text) >= MIN_CHARS:
                out.append((page["title"], text))
        cont = data.get("continue") or {}
        if not cont or not found:
            break
    return out[:pages]


def save(pages: list[tuple[str, str]], folder: Path = DATA) -> Path:
    (folder / "wiki").mkdir(parents=True, exist_ok=True)
    for title, text in pages:
        (folder / "wiki" / f"{safe_name(title)}.txt").write_text(text + "\n", encoding="utf-8")
    joined = folder / "wiki.txt"
    joined.write_text("".join(f"== {t} ==\n{x}\n\n" for t, x in pages), encoding="utf-8")
    return joined


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--pages", type=int, default=300)
    p.add_argument("--start", default="", help="start the alphabet here, e.g. Dragon")
    args = p.parse_args(argv)
    pages = fetch(Wiki(DATA / "cache"), args.pages, args.start)
    joined = save(pages)
    size = joined.stat().st_size
    print(f"{len(pages)} pages, {size / 1e6:.1f} MB of text in {joined}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
