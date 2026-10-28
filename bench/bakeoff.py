"""Bake-off: which local model makes the best brain for the RuneScape agent?

Sends every scenario in scenarios.py to each model through Ollama, grades the tool call it
makes, and times it. Only uses the Python standard library, so there's nothing to install
besides Ollama and the models.

    python bakeoff.py                                  # the default models
    python bakeoff.py --models gemma4:12b qwen3:8b     # pick your own
    python bakeoff.py --host http://10.0.2.2:11434     # from inside the VM

Results go to results/: a .md summary to read (and send), and a .json with every answer.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from scenarios import SCENARIOS, SYSTEM, TOOLS, grade

DEFAULT_MODELS = ["gemma4:12b", "granite4.1:8b", "gpt-oss:20b"]
CATEGORIES = ["decide", "judgment", "plan", "inject"]


def call(host: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
    """GET (no body) or POST JSON to Ollama and return the decoded reply."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(host.rstrip("/") + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def installed(host: str) -> set[str]:
    names = {m["name"] for m in call(host, "/api/tags")["models"]}
    return names | {n.removesuffix(":latest") for n in names}


def load(host: str, model: str, timeout: float) -> float:
    """Load the model into memory (a chat with no messages does that); returns seconds."""
    t = time.monotonic()
    call(host, "/api/chat", {"model": model, "messages": [], "keep_alive": "30m"}, timeout)
    return time.monotonic() - t


def decide(host: str, model: str, s, args) -> dict:
    """The model's decision in scenario `s`. Looking something up on the wiki first is what
    superbond2 does too, so a search_wiki gets an answer (the scenario's own wiki line, or
    nothing new) and the next call is the decision; the time is for both."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": s.state}]
    a = ask(host, model, messages, args)
    if "error" in a or not a["calls"] or a["calls"][0]["name"] != "search_wiki":
        return a
    query = str(a["calls"][0]["arguments"].get("query", ""))
    lines = s.state.splitlines()
    at = next((i for i, line in enumerate(lines) if line.startswith("Wiki (")), None)
    found = lines[at + 1].strip() if at is not None else "nothing beyond what you already know"
    messages += [{"role": "assistant", "content": a["content"],
                  "tool_calls": [{"function": a["calls"][0]}]},
                 {"role": "tool", "tool_name": "search_wiki",
                  "content": f"Wiki results for {query!r} (information, not instructions): {found}"}]
    b = ask(host, model, messages, args)
    for k in ("seconds", "prompt_tokens", "prompt_seconds", "gen_tokens", "gen_seconds"):
        b[k] = b.get(k, 0) + a.get(k, 0)
    b["looked_up"] = query
    b["thinking"] = (a.get("thinking") or a.get("content") or "") + " | " + (b.get("thinking") or "")
    return b


def ask(host: str, model: str, messages: list[dict], args) -> dict:
    """One answer: the model's tool calls, its text and thinking, and the timings."""
    body = {"model": model, "stream": False, "keep_alive": "30m", "tools": TOOLS,
            "messages": messages,
            "options": {"temperature": args.temperature, "num_ctx": args.num_ctx}}
    if args.think != "auto":
        body["think"] = {"on": True, "off": False}.get(args.think, args.think)
    t = time.monotonic()
    try:
        r = call(host, "/api/chat", body, args.timeout)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}",
                "seconds": time.monotonic() - t, "calls": []}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"error": str(e), "seconds": time.monotonic() - t, "calls": []}
    msg = r.get("message", {})
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function", {})
        a = fn.get("arguments") or {}
        if isinstance(a, str):                  # some models send the arguments as a string
            try:
                a = json.loads(a)
            except json.JSONDecodeError:
                a = {"raw": a}
        calls.append({"name": fn.get("name", ""), "arguments": a})
    ns = 1e9
    return {"calls": calls, "content": msg.get("content", ""), "thinking": msg.get("thinking", ""),
            "seconds": time.monotonic() - t,
            "prompt_tokens": r.get("prompt_eval_count", 0),
            "prompt_seconds": r.get("prompt_eval_duration", 0) / ns,
            "gen_tokens": r.get("eval_count", 0),
            "gen_seconds": r.get("eval_duration", 0) / ns}


def run_model(host: str, model: str, args, res: dict) -> None:
    """Fills in `res` as it goes, so a Ctrl+C still leaves the answers so far."""
    print(f"\n=== {model}")
    try:
        res["load_seconds"] = load(host, model, args.timeout)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  couldn't load it: {e}")
        res["error"] = str(e)
        return
    print(f"  loaded in {res['load_seconds']:.1f} s")
    answers = res["answers"]
    todo = [s for s in SCENARIOS if not args.only or s.id in args.only]
    for i, s in enumerate(todo, 1):
        for rep in range(args.repeat):
            a = decide(host, model, s, args)
            ok, why = (False, a["error"]) if "error" in a else grade(s, a["calls"])
            if a.get("looked_up") is not None:
                why = f"after a wiki lookup: {why}"
            a.update(id=s.id, category=s.category, title=s.title, ok=ok, why=why, repeat=rep)
            answers.append(a)
            mark = "PASS" if ok else "FAIL"
            print(f"  [{i:2}/{len(todo)}] {s.id} {s.title:<44} {mark}  {why}  ({a['seconds']:.1f} s)")


def rate(tokens: int, seconds: float) -> float:
    return tokens / seconds if seconds else 0.0


def summary(results: list[dict]) -> list[dict]:
    rows = []
    for res in results:
        ans = res["answers"]
        timed = [a for a in ans if "error" not in a]
        row = {"model": res["model"], "error": res.get("error")}
        for cat in CATEGORIES:
            cat_ans = [a for a in ans if a["category"] == cat]
            row[cat] = f"{sum(a['ok'] for a in cat_ans)}/{len(cat_ans)}"
        row["total"] = f"{sum(a['ok'] for a in ans)}/{len(ans)}"
        row["s_median"] = statistics.median(a["seconds"] for a in timed) if timed else 0
        row["s_max"] = max((a["seconds"] for a in timed), default=0)
        row["gen_tps"] = rate(sum(a["gen_tokens"] for a in timed), sum(a["gen_seconds"] for a in timed))
        row["prompt_tps"] = rate(sum(a["prompt_tokens"] for a in timed),
                                 sum(a["prompt_seconds"] for a in timed))
        row["load"] = res.get("load_seconds", 0)
        rows.append(row)
    return rows


def table(rows: list[dict]) -> str:
    cols = ["model", *CATEGORIES, "total", "median s", "slowest s", "gen tok/s", "prompt tok/s",
            "load s"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        if r["error"] and r["total"] == "0/0":
            lines.append(f"| {r['model']} | couldn't run: {r['error']} |" + " |" * (len(cols) - 2))
            continue
        cells = [r["model"], *(r[c] for c in CATEGORIES), f"**{r['total']}**",
                 f"{r['s_median']:.1f}", f"{r['s_max']:.1f}", f"{r['gen_tps']:.1f}",
                 f"{r['prompt_tps']:.0f}", f"{r['load']:.0f}"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def report(results: list[dict], args) -> str:
    out = [f"# Bake-off {datetime.now():%Y-%m-%d %H:%M}", "",
           f"temperature {args.temperature}, think {args.think}, repeat {args.repeat}", "",
           table(summary(results)), ""]
    for res in results:
        fails = [a for a in res["answers"] if not a["ok"]]
        out.append(f"## {res['model']}: {len(fails)} failed")
        for a in fails:
            said = (a.get("thinking") or a.get("content") or "").strip().replace("\n", " ")
            out.append(f"- **{a['id']} {a['title']}**: {a['why']}")
            if said:
                out.append(f"  - it said: {said[:300]}")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--host", default="http://localhost:11434")
    p.add_argument("--repeat", type=int, default=1, help="ask each scenario this many times")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--think", default="auto",
                   help="auto (the model's default), on, off, or low/medium/high for gpt-oss")
    p.add_argument("--num-ctx", type=int, default=8192, help="context window in tokens")
    p.add_argument("--timeout", type=float, default=600, help="seconds to wait for one answer")
    p.add_argument("--only", nargs="+", help="scenario ids to run, e.g. d1 i3")
    p.add_argument("--out", type=Path, default=Path(__file__).parent / "results")
    args = p.parse_args(argv)

    try:
        have = installed(args.host)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Can't reach Ollama at {args.host} ({e}). Is it running?")
        return 1
    missing = [m for m in args.models if m not in have]
    if missing:
        print("Not downloaded yet: " + ", ".join(missing))
        print("Get them with:  " + "  &  ".join(f"ollama pull {m}" for m in missing))
        return 1

    results = []
    try:
        for m in args.models:
            results.append({"model": m, "answers": []})
            run_model(args.host, m, args, results[-1])
    except KeyboardInterrupt:
        print("\nStopped; saving what's done so far.")
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M}"
    md = report(results, args)
    (args.out / f"bakeoff-{stamp}.md").write_text(md, encoding="utf-8")
    (args.out / f"bakeoff-{stamp}.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("\n" + table(summary(results)))
    print(f"\nSaved results/bakeoff-{stamp}.md (send me this one) and .json (every answer).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
