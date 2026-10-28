"""superbond2 on Discord: how he reaches the owner, and the owner reaches him, from a phone.

He posts highlights to one private channel (new goals, questions, firsts, journal entries,
switching accounts, why he stopped) and a daily summary. The owner can answer there, or
send a few words:

    stop      stop playing
    pause     wait until `resume`
    resume    carry on
    veto      say no to his current goal (`veto too risky` gives him the reason)
    help      list these

Anything else is advice: it reaches him in his next turn as something the owner said. His
goals stay his to choose. Only the owner's own Discord account is listened to; everyone
else in the channel is ignored, whatever they claim.

The bot's token, the channel and the owner's Discord user ID are in
~/.config/superbond2/discord.env, readable only by you:

    DISCORD_TOKEN=...
    DISCORD_CHANNEL_ID=...
    DISCORD_OWNER_ID=...

The token is never printed, logged or put in his prompt. Everything goes through Discord's
REST API with the standard library; messages are read by polling the channel, which needs
the bot's Message Content Intent turned on in the Developer Portal.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .characters import read_env
from .memory import Memory

CONFIG = Path.home() / ".config" / "superbond2" / "discord.env"
API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
USER_AGENT = "DiscordBot (https://github.com/devbasilmartin/Llm, 0.1)"
MAX_POST = 1900                 # Discord allows 2000 characters a message
MAX_HEARD = 500                 # characters of one owner message he's shown
COMMANDS = ("stop", "pause", "resume", "veto", "help")
HELP = ("Say `stop`, `pause`, `resume`, `veto` (or `veto <why>`) to say no to his goal, or "
        "anything else as advice. When he's asked something, your next message is the answer.")


class DiscordError(Exception):
    """Discord couldn't be reached or said no. The message never includes the token."""


def load_config(path: Path = CONFIG) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise DiscordError(f"no Discord settings: put DISCORD_TOKEN, DISCORD_CHANNEL_ID and "
                           f"DISCORD_OWNER_ID in {path} (see docs/discord.md)")
    if path.stat().st_mode & 0o077:
        raise DiscordError(f"{path} can be read by other users: chmod 600 {path}")
    env = read_env(path)
    missing = [k for k in ("DISCORD_TOKEN", "DISCORD_CHANNEL_ID", "DISCORD_OWNER_ID")
               if not env.get(k)]
    if missing:
        raise DiscordError(f"{path} is missing {', '.join(missing)}")
    for k in ("DISCORD_CHANNEL_ID", "DISCORD_OWNER_ID"):
        if not env[k].isdigit():
            raise DiscordError(f"{k} should be a number (Discord: Developer Mode on, then "
                               "right-click → Copy ID)")
    return env


class Discord:
    """One channel, one owner, through Discord's REST API."""

    def __init__(self, token: str, channel: str, owner: str, opener=urllib.request.urlopen,
                 sleep=time.sleep):
        self._token, self.channel, self.owner = token, str(channel), str(owner)
        self.opener, self.sleep = opener, sleep
        self.after: str | None = None           # the newest message already seen

    @classmethod
    def from_config(cls, path: Path = CONFIG) -> "Discord":
        env = load_config(path)
        return cls(env["DISCORD_TOKEN"], env["DISCORD_CHANNEL_ID"], env["DISCORD_OWNER_ID"])

    def _call(self, method: str, path: str, body: dict | None = None, raw: bytes | None = None,
              content_type: str = "application/json"):
        data = json.dumps(body).encode() if body is not None else raw
        for _ in range(4):
            req = urllib.request.Request(API + path, data=data, method=method, headers={
                "Authorization": f"Bot {self._token}", "User-Agent": USER_AGENT,
                "Content-Type": content_type})
            try:
                with self.opener(req, timeout=20) as r:
                    raw = r.read()
                return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                if e.code == 429:                    # rate limited: wait as long as it says
                    try:
                        wait = float(json.loads(e.read() or b"{}").get("retry_after", 1))
                    except ValueError:
                        wait = 1.0
                    self.sleep(min(wait, 30))
                    continue
                hint = {401: " (the token is wrong)", 403: " (the bot can't see or post in that "
                        "channel: check its permissions)", 404: " (no such channel)"}.get(e.code, "")
                raise DiscordError(f"Discord said {e.code} to {method} {path.split('?')[0]}{hint}") from None
            except (urllib.error.URLError, OSError) as e:
                raise DiscordError(f"couldn't reach Discord: {getattr(e, 'reason', e)}") from None
        raise DiscordError("Discord kept saying slow down")

    def post(self, text: str) -> None:
        text = text.strip()
        while text:
            chunk, text = text[:MAX_POST], text[MAX_POST:]
            self._call("POST", f"/channels/{self.channel}/messages",
                       {"content": chunk, "allowed_mentions": {"parse": []}})   # no pings

    def post_file(self, path: Path, text: str = "") -> None:
        """Attach a file (a bake-off report) to a message."""
        boundary = f"superbond2{time.time_ns()}"
        payload = json.dumps({"content": text, "allowed_mentions": {"parse": []}})
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
                f"Content-Type: application/json\r\n\r\n{payload}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; "
                f"filename=\"{Path(path).name}\"\r\nContent-Type: text/markdown\r\n\r\n").encode()
        body += Path(path).read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        self._call("POST", f"/channels/{self.channel}/messages", raw=body,
                   content_type=f"multipart/form-data; boundary={boundary}")

    def new_messages(self) -> list[str]:
        """The owner's messages since the last look, oldest first. The first look only finds
        where the channel is, so nothing from before he started is replayed."""
        if self.after is None:
            last = self._call("GET", f"/channels/{self.channel}/messages?limit=1") or []
            self.after = last[0]["id"] if last else "0"
            return []
        got = self._call("GET", f"/channels/{self.channel}/messages?after={self.after}&limit=50") or []
        got.sort(key=lambda m: int(m["id"]))
        if got:
            self.after = got[-1]["id"]
        return [" ".join(m.get("content", "").split())[:MAX_HEARD] for m in got
                if str(m.get("author", {}).get("id")) == self.owner
                and not m.get("author", {}).get("bot") and m.get("content", "").strip()]

    def hello(self) -> bool:
        """Connect to the gateway once. Discord has asked bots to do that before they post;
        needs `pip install websocket-client`, and is skipped without it."""
        try:
            import websocket
        except ImportError:
            return False
        try:
            ws = websocket.create_connection(GATEWAY, timeout=20)
            try:
                json.loads(ws.recv())                        # Hello
                ws.send(json.dumps({"op": 2, "d": {"token": self._token, "intents": 0, "properties": {
                    "os": "linux", "browser": "superbond2", "device": "superbond2"}}}))
                for _ in range(10):
                    msg = json.loads(ws.recv())
                    if msg.get("t") == "READY":
                        return True
                    if msg.get("op") == 9:
                        raise DiscordError("Discord refused the bot's login (check the token)")
            finally:
                ws.close()
        except DiscordError:
            raise
        except Exception as e:                               # noqa: BLE001  any socket trouble
            raise DiscordError(f"couldn't connect to Discord's gateway: {type(e).__name__}") from None
        return False


def daily_summary(memory: Memory, day: str) -> str:
    """One post about a day of play (`day` is YYYY-MM-DD), from his decision log, firsts and
    journal."""
    turns, deaths = [], []
    if memory.decisions_file.exists():
        for line in memory.decisions_file.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if str(rec.get("at", "")).startswith(day):
                (deaths if rec.get("event") == "death" else turns).append(rec)
    if not turns:
        return f"📅 {day}: no play today."
    routines = [t for t in turns if t.get("tool") == "run_routine"]
    worked = sum(1 for t in routines if t.get("ok"))
    seconds = [t.get("seconds", 0) for t in turns if t.get("tool")]
    accounts = sorted({t["account"] for t in turns if t.get("account")})
    import yaml
    firsts = yaml.safe_load(memory.firsts_file.read_text()) if memory.firsts_file.exists() else {}
    new = [k.replace("_", " ") for k, at in (firsts or {}).items() if str(at).startswith(day)]
    goals = [t["args"].get("goal") for t in turns if t.get("tool") == "set_goal" and t.get("ok")]
    journal = [line.split("** ", 1)[1] for line in (memory.journal_file.read_text().splitlines()
               if memory.journal_file.exists() else []) if line.startswith(f"**{day}")]
    lines = [f"📅 {day}: {len(turns)} turns" + (f" on {', '.join(accounts)}" if accounts else "")
             + (f", about {sum(seconds) / len(seconds):.0f} s each" if seconds else "") + "."]
    if routines:
        lines.append(f"Routines: {len(routines)} run, {worked} worked.")
    if deaths:
        lines.append(f"💀 Died {len(deaths)} time{'s' if len(deaths) > 1 else ''}.")
    if new:
        lines.append("Firsts: " + ", ".join(new) + ".")
    if goals:
        lines.append("New goals: " + "; ".join(str(g) for g in goals) + ".")
    if journal:
        lines.append(f"From his journal: “{journal[-1]}”")
    return "\n".join(lines)

