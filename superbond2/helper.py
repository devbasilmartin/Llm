"""The helper: runs on the VM and does a few fixed jobs when the owner asks on Discord, so
the project can be looked after from a phone.

    !status             is he playing, what's running, Ollama, the code version, disk space
    !models             the models Ollama has
    !pull gemma4:12b    download a model (progress as it goes)
    !bakeoff [models]   run the bake-off; the results come back as a file
    !update             get the newest code (and restart the helper if it changed)
    !tests              run the tests
    !play MODEL [CHARACTER] [MINUTES]    let superbond2 play
    !log [N]            the last lines of his play log
    !kill               stop whatever the helper started, right away
    !help               this list

Messages starting with `!` are for the helper. Everything else is for superbond2 himself
(`stop`, `pause`, `veto`, advice). The helper only does what's on this list, with the
arguments checked, and only for the owner's Discord account: it isn't a remote shell.

Start it with `python -m superbond2 helper`; `python -m superbond2 helper --autostart`
makes it start with the VM's desktop, where superbond2 can see the screen.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from .discord import Discord, DiscordError

REPO = Path(__file__).resolve().parent.parent
BRANCH = "bench-bakeoff"
MODEL = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9._-]+)?(:[a-z0-9._-]+)?$")
CHARACTER = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
HELP = __doc__.split("\n\n")[1]
AUTOSTART = Path.home() / ".config" / "autostart" / "superbond2-helper.desktop"


def _gb(n: float) -> str:
    return f"{n / 1e9:.1f} GB"


class Helper:
    def __init__(self, discord: Discord, host: str = "http://10.0.2.2:11434", repo: Path = REPO,
                 popen=subprocess.Popen, opener=urllib.request.urlopen, log=print):
        self.discord, self.host, self.repo = discord, host.rstrip("/"), Path(repo)
        self.popen, self.opener, self.log = popen, opener, log
        self.job: tuple[str, threading.Thread] | None = None      # one long job at a time
        self.proc: subprocess.Popen | None = None                 # the job's process, if any
        self.playing: subprocess.Popen | None = None
        self.restart = False

    # --- talking ----------------------------------------------------------------------------
    def say(self, text: str) -> None:
        try:
            self.discord.post(text)
        except DiscordError as e:
            self.log(f"(couldn't post: {e})")

    def serve(self, every: float = 3.0) -> None:
        self.discord.new_messages()                 # start from now
        self.say("🧰 Helper here. `!help` for what I can do.")
        while not (self.restart and not self._busy()):
            try:
                heard = self.discord.new_messages()
            except DiscordError as e:
                self.log(f"(couldn't read Discord: {e})")
                heard = []
            for text in heard:
                if text.startswith("!"):
                    self.handle(text)
            time.sleep(every)
        self.say("🔄 Restarting with the new code...")
        os.execv(sys.executable, [sys.executable, "-m", "superbond2", "helper"])

    def handle(self, text: str) -> None:
        word, *args = text[1:].split()
        fn = getattr(self, f"do_{word.lower()}", None) if word else None
        if fn is None:
            return self.say(f"I don't know `!{word}`. `!help` lists what I can do.")
        try:
            fn(*args)
        except TypeError:
            self.say(f"`!{word}` doesn't take those. `!help` shows how.")
        except Exception as e:                      # noqa: BLE001  report, keep serving
            self.say(f"⚠️ `!{word}` failed: {type(e).__name__}: {e}")

    # --- jobs that take a while ---------------------------------------------------------------
    def _busy(self) -> bool:
        return bool(self.job and self.job[1].is_alive())

    def _playing_pid(self) -> int | None:
        """superbond2's process, whoever started it: from the lock file he keeps while playing."""
        if self.playing is not None and self.playing.poll() is None:
            return self.playing.pid
        lock = self.repo / "data" / "playing.lock"
        try:
            pid = int(lock.read_text().strip())
        except (OSError, ValueError):
            return None
        return pid if Path(f"/proc/{pid}").exists() else None

    def _start(self, name: str, fn, *args) -> None:
        if self._busy():
            return self.say(f"Busy with {self.job[0]}. `!status` to check, `!kill` to stop it.")
        t = threading.Thread(target=self._run_job, args=(name, fn, args), daemon=True)
        self.job = (name, t)
        t.start()

    def _run_job(self, name: str, fn, args) -> None:
        try:
            fn(*args)
        except Exception as e:                      # noqa: BLE001
            self.say(f"⚠️ {name} failed: {type(e).__name__}: {e}")
        finally:
            self.proc = None

    def _command(self, cmd: list[str], on_line=None) -> tuple[int, list[str]]:
        """Run a command in the repo, keeping its output (and handing each line to `on_line`)."""
        self.proc = self.popen(cmd, cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, bufsize=1)
        lines = []
        for line in self.proc.stdout:
            line = line.rstrip()
            lines.append(line)
            if on_line:
                on_line(line)
        return self.proc.wait(), lines

    def _ollama(self, path: str, body: dict | None = None, timeout: float = 10):
        req = urllib.request.Request(self.host + path, method="POST" if body else "GET",
                                     data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
        return self.opener(req, timeout=timeout)

    # --- the commands ---------------------------------------------------------------------------
    def do_help(self) -> None:
        self.say("```\n" + HELP + "\n```")

    def do_status(self) -> None:
        lines = []
        lines.append("🎮 superbond2 is playing." if self._playing_pid() else
                     "💤 superbond2 isn't playing.")
        if self._busy():
            lines.append(f"⚙️ Working on: {self.job[0]}.")
        try:
            with self._ollama("/api/ps") as r:
                loaded = [m["name"] for m in json.load(r).get("models", [])]
            lines.append("🧠 Ollama is up" + (f", loaded: {', '.join(loaded)}." if loaded else
                                              ", nothing loaded."))
        except OSError as e:
            lines.append(f"🧠 Can't reach Ollama at {self.host} ({getattr(e, 'reason', e)}). Is it "
                         "running on Windows, with OLLAMA_HOST=0.0.0.0?")
        _, git = self._git("log", "-1", "--format=%h %s")
        lines.append(f"📦 Code: {git[0] if git else 'unknown'}.")
        lines.append(f"💾 Disk free: {_gb(shutil.disk_usage(self.repo).free)}.")
        self.say("\n".join(lines))

    def do_models(self) -> None:
        with self._ollama("/api/tags") as r:
            models = json.load(r).get("models", [])
        self.say("Models: " + ", ".join(f"{m['name']} ({_gb(m.get('size', 0))})" for m in models)
                 if models else "Ollama has no models yet. `!pull gemma4:12b` gets one.")

    def do_pull(self, model: str) -> None:
        if not MODEL.match(model):
            return self.say(f"`{model}` doesn't look like a model name (like gemma4:12b).")
        self._start(f"downloading {model}", self._pull, model)

    def _pull(self, model: str) -> None:
        self.say(f"⬇️ Downloading {model}...")
        shown, last = -1, None
        with self._ollama("/api/pull", {"model": model, "stream": True}, timeout=600) as r:
            for raw in r:
                msg = json.loads(raw or b"{}")
                if msg.get("error"):
                    return self.say(f"⚠️ {model}: {msg['error']}")
                last = msg.get("status")
                if msg.get("total") and msg.get("completed") is not None:
                    pct = int(100 * msg["completed"] / msg["total"])
                    if pct // 25 > shown and msg["total"] > 50e6:      # the big part, every 25%
                        shown = pct // 25
                        self.say(f"{model}: {pct}% of {_gb(msg['total'])}")
        self.say(f"✅ {model} is ready." if last == "success" else
                 f"⚠️ {model}: the download ended at '{last}'. `!pull {model}` again resumes it.")

    def do_bakeoff(self, *models: str) -> None:
        bad = [m for m in models if not MODEL.match(m)]
        if bad:
            return self.say(f"Not model names: {', '.join(bad)}")
        self._start("the bake-off", self._bakeoff, list(models))

    def _bakeoff(self, models: list[str]) -> None:
        cmd = [sys.executable, "bench/bakeoff.py", "--host", self.host]
        if models:
            cmd += ["--models", *models]
        self.say("🏁 Bake-off started. On this CPU it takes a while; I'll post as each model goes.")
        done = [0]

        def progress(line: str) -> None:
            if line.startswith("=== ") or "couldn't load" in line or "loaded in" in line:
                self.say(line.strip())
            elif re.match(r"\s*\[\s*\d+/\d+\]", line):
                done[0] += 1
                if done[0] % 7 == 0:
                    self.say(f"  {line.strip()[:120]}")
        code, lines = self._command(cmd, progress)
        results = sorted((self.repo / "bench" / "results").glob("bakeoff-*.md"))
        if code != 0 or not results:
            return self.say("⚠️ The bake-off stopped:\n" + "\n".join(lines[-8:]))
        self.say("✅ Bake-off done:\n" + "\n".join(lines[-14:]))
        try:
            self.discord.post_file(results[-1], "Here's the full report. Send it to Claude.")
        except DiscordError as e:
            self.say(f"(couldn't attach the report: {e}; it's {results[-1]})")

    def _git(self, *args: str) -> tuple[int, list[str]]:
        p = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)
        return p.returncode, (p.stdout + p.stderr).strip().splitlines()

    def do_update(self) -> None:
        _, before = self._git("rev-parse", "HEAD")
        code, out = self._git("pull", "--ff-only", "origin", BRANCH)
        if code != 0:
            return self.say("⚠️ Couldn't update:\n" + "\n".join(out[-6:]))
        _, after = self._git("rev-parse", "HEAD")
        if before == after:
            return self.say("Already up to date.")
        _, changed = self._git("diff", "--name-only", before[0], after[0])
        _, now = self._git("log", "-1", "--format=%h %s")
        msg = [f"📦 Updated to {now[0]}."]
        if "requirements.txt" in changed:
            p = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                               cwd=self.repo, capture_output=True, text=True)
            msg.append("Installed the new requirements." if p.returncode == 0 else
                       "⚠️ Installing the requirements failed:\n" + p.stderr[-500:])
        self.say("\n".join(msg))
        if any(c.startswith("superbond2/") for c in changed):
            if self._playing_pid():
                self.say("He's playing on the old code; it's used from his next `!play`.")
            self.restart = True                     # the helper's own code may have changed

    def do_tests(self) -> None:
        self._start("the tests", self._tests)

    def _tests(self) -> None:
        self.say("🧪 Running the tests (a few minutes)...")
        code, lines = self._command([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
        tail = [line for line in lines if line.strip()][-6:]
        self.say(("✅ " if code == 0 else "❌ ") + "\n".join(tail))

    def do_stop(self, *_) -> None:
        self.say("Say `stop` (no !) to him to stop at the end of his turn, or `!kill` to stop "
                 "right away.")

    def do_play(self, model: str, character: str = "", minutes: str = "60") -> None:
        if self._playing_pid():
            return self.say("He's already playing. Say `stop` to him, or `!kill`.")
        if not MODEL.match(model):
            return self.say(f"`{model}` doesn't look like a model name.")
        if character.isdigit() and minutes == "60":
            character, minutes = "", character      # !play gemma4:12b 90
        if character and not CHARACTER.match(character):
            return self.say(f"`{character}` isn't a character name.")
        if not minutes.isdigit() or not 1 <= int(minutes) <= 24 * 60:
            return self.say("Minutes should be a number from 1 to 1440.")
        cmd = [sys.executable, "-m", "superbond2", "play", "--model", model, "--host", self.host,
               "--minutes", minutes, "--turns", "100000"]
        if character:
            cmd += ["--character", character]
        log = self.repo / "data" / "play.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M')} play {model} {character} {minutes}\n")
        self.playing = self.popen(cmd, cwd=self.repo, stdout=log.open("a"), stderr=subprocess.STDOUT)
        self.say(f"🎮 Starting him on {model}{' as ' + character if character else ''} for "
                 f"{minutes} minutes. He'll post here himself.")

    def do_log(self, n: str = "15") -> None:
        log = self.repo / "data" / "play.log"
        if not log.exists():
            return self.say("No play log yet.")
        lines = log.read_text(errors="replace").splitlines()[-max(1, min(int(n), 60)):]
        self.say("```\n" + "\n".join(line[:180] for line in lines) + "\n```")

    def do_kill(self) -> None:
        stopped = []
        if self.proc is not None and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)    # the bake-off saves what's done on SIGINT
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            stopped.append(self.job[0] if self.job else "the job")
        pid = self._playing_pid()
        if pid:
            os.kill(pid, signal.SIGINT)              # play's Stopped/finally: releases its lock
            stopped.append("his play")
        self.say("Stopped " + " and ".join(stopped) + "." if stopped else "Nothing to stop.")


def write_autostart(path: Path = AUTOSTART) -> Path:
    """Start the helper with the desktop session (where superbond2 can see the screen)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    log = REPO / "data" / "helper.log"
    path.write_text(f"""[Desktop Entry]
Type=Application
Name=superbond2 helper
Exec=sh -c 'mkdir -p "{log.parent}" && cd "{REPO}" && exec "{sys.executable}" -m superbond2 helper >> "{log}" 2>&1'
X-GNOME-Autostart-enabled=true
""")
    return path
