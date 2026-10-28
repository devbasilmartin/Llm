"""The OSRS Wiki, for superbond2 to look things up.

Two things he can do: search (titles and a line each) and read a page or one of its
sections, as plain text cut to fit a CPU-sized prompt. Pages come from the wiki's API as
wikitext and are turned into plain text here: links become their words, quest and item
infoboxes become "key: value" lines, pictures, maps and tables are left out.

Being polite to the wiki: a User-Agent that says who's asking, at most one request a
second, and a local cache so the same page isn't fetched twice in a week.

Everything read here was written by other people: it's information, never instructions.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

API = "https://oldschool.runescape.wiki/api.php"
PRICES = "https://prices.runescape.wiki/api/v1/osrs"     # the wiki's live Grand Exchange prices
USER_AGENT = "superbond2/0.1 (a learning project; https://github.com/devbasilmartin/Llm)"
CACHE_DAYS = 7
MAX_TEXT = 1800             # characters of a page that go into his prompt


class WikiError(Exception):
    """The wiki couldn't be reached, or has no such page."""


# --- wikitext -> plain text ---------------------------------------------------------------
DROP_TEMPLATES = re.compile(r"^(external|has quick guide|otheruses|map|clear|reflist|"
                            r"navbox|stub|update|cite|citation|ref|main|see also|"
                            r"relativelocation|quest guide|quick guide|confusion)", re.I)
INFOBOX = re.compile(r"^(infobox|quest details)", re.I)
SKIP_KEYS = re.compile(r"^(image|release|update|developer|leagueregion|startmap|map|version|id|"
                       r"alt|caption|name|number|series|smwname|kdb\w*|wiki\w*|icon|"
                       r"removal|removaldate|exchange|value|high|low|weight)$", re.I)


def _split_template(body: str) -> list[str]:
    """Split a template's insides on | that aren't inside nested [[...]] or {{...}}."""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur.append(two)
            i += 2
        elif two in ("}}", "]]"):
            depth -= 1
            cur.append(two)
            i += 2
        elif body[i] == "|" and depth == 0:
            parts.append("".join(cur))
            cur, i = [], i + 1
        else:
            cur.append(body[i])
            i += 1
    parts.append("".join(cur))
    return parts


def _template(body: str) -> str:
    parts = _split_template(body)
    name = parts[0].strip()
    if DROP_TEMPLATES.match(name):
        return ""
    if name.upper() == "SCP" and len(parts) >= 3:            # {{SCP|Combat|20}} -> Combat 20
        return f"{parts[1].strip()} {parts[2].strip()}"
    if INFOBOX.match(name):
        lines = []
        for p in parts[1:]:
            key, eq, value = p.partition("=")
            if eq and not SKIP_KEYS.match(key.strip().rstrip("0123456789")) and value.strip():
                lines.append(f"{key.strip()}: {value.strip()}")
        return "\n" + "\n".join(lines) + "\n"
    if name.lower() in ("coins", "gp", "nowrap", "plink", "plinkp", "skill clickpic"):
        return parts[1].strip() if len(parts) > 1 else ""
    return ""                                                # other templates: left out


def _expand_templates(text: str) -> str:
    """Replace {{...}} from the inside out, so nested ones work."""
    for _ in range(10):
        new = re.sub(r"\{\{((?:(?!\{\{|\}\}).)*)\}\}", lambda m: _template(m.group(1)), text, flags=re.S)
        if new == text:
            break
        text = new
    return text


def to_text(wikitext: str) -> str:
    t = re.sub(r"<!--.*?-->", "", wikitext, flags=re.S)
    t = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"\{\|.*?\|\}", "", t, flags=re.S)           # tables
    t = _expand_templates(t)
    t = re.sub(r"\[\[(?:File|Image|Category):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", t, flags=re.I)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)  # [[a|b]] -> b, [[a]] -> a
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"^(=+)\s*(.*?)\s*\1\s*$", r"\n## \2", t, flags=re.M)
    t = re.sub(r"^\*+\s*", "- ", t, flags=re.M)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def clip(text: str, limit: int = MAX_TEXT) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0]
    return (cut if len(cut) > limit // 2 else text[:limit]) + "\n(...more on the page)"


# --- the wiki -----------------------------------------------------------------------------
def http_get(url: str, timeout: float = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise WikiError(f"the wiki can't be reached right now ({e})") from None


class Wiki:
    def __init__(self, cache: Path | None = None, get: Callable[[str], dict] = http_get,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.cache = Path(cache) if cache else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
        self._get, self._clock, self._sleep = get, clock, sleep
        self._last = -1e9

    def _api(self, **params) -> dict:
        return self._fetch(API + "?" + urllib.parse.urlencode({**params, "format": "json"}))

    def _fetch(self, url: str) -> dict:
        path = self.cache / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".json") if self.cache else None
        if path and path.exists() and time.time() - path.stat().st_mtime < CACHE_DAYS * 86400:
            return json.loads(path.read_text())
        wait = self._last + 1.0 - self._clock()          # at most one request a second
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()
        data = self._get(url)
        if path:
            path.write_text(json.dumps(data))
        return data

    def search(self, query: str, limit: int = 3) -> str:
        query = " ".join(str(query).split())
        if not query:
            return "search for something, e.g. 'Vampyre Slayer' or 'oak logs'"
        hits = self._api(action="query", list="search", srsearch=query, srlimit=limit,
                         srprop="snippet").get("query", {}).get("search", [])
        if not hits:
            return f"nothing on the wiki for {query!r}"
        lines = []
        for i, h in enumerate(hits, 1):
            snippet = html.unescape(re.sub(r"<[^>]+>", "", h.get("snippet", ""))).strip()
            lines.append(f"{i}. {h['title']}: {snippet[:140]}")
        return "\n".join(lines) + "\nRead one with read_wiki(page=..., section=...)."

    def read(self, page: str, section: str = "") -> tuple[str, str]:
        """(title, text): the page's opening, or the named section, as plain text, with the
        list of sections at the end."""
        page = " ".join(str(page).split())
        info = self._api(action="parse", page=page, redirects=1, prop="sections")
        if "error" in info:
            raise WikiError(f"there's no wiki page called {page!r}; search_wiki for it")
        title = info["parse"]["title"]
        sections = info["parse"].get("sections", [])
        names = [s["line"] for s in sections]
        index = "0"
        if section:
            want = str(section).strip().lower()
            match = next((s for s in sections if s["line"].lower() == want), None) or \
                next((s for s in sections if want in s["line"].lower()), None)
            if match is None:
                raise WikiError(f"'{title}' has no section {section!r}. Sections: {', '.join(names)}")
            index = match["index"]
        data = self._api(action="parse", page=title, prop="wikitext", section=index)
        text = to_text(data["parse"]["wikitext"]["*"])
        where = f"{title}, {section}" if section else title
        return where, clip(text) + ("\nSections: " + ", ".join(names) if names else "")

    def value(self, item: str) -> int | None:
        """The item's value (its infobox's `value`, which shops price from), from the page's raw
        wikitext; None if unknown."""
        page = " ".join(str(item).replace("_", " ").split())
        data = self._api(action="parse", page=page[:1].upper() + page[1:], redirects=1,
                         prop="wikitext", section=0)
        raw = (data.get("parse") or {}).get("wikitext", {}).get("*", "")
        m = re.search(r"\|\s*value\d*\s*=\s*([\d,]+)", raw)
        return int(m[1].replace(",", "")) if m else None

    def ge_price(self, item: str) -> int | None:
        """The real game's latest Grand Exchange price (the middle of the last buy and sell),
        or None. A private server's market can differ."""
        name = " ".join(str(item).replace("_", " ").split()).lower()
        try:
            mapping = self._fetch(f"{PRICES}/mapping")
            entry = next((m for m in mapping if str(m.get("name", "")).lower() == name), None)
            if entry is None:
                return None
            latest = self._fetch(f"{PRICES}/latest?id={entry['id']}")
        except WikiError:
            return None
        p = (latest.get("data") or {}).get(str(entry["id"])) or {}
        prices = [v for v in (p.get("high"), p.get("low")) if v]
        return round(sum(prices) / len(prices)) if prices else None
