"""superbond2's characters: logging in and out, and staying out of skillbot's way.

A character signs in one of two ways:

- With a password (legacy login): skillbot's file ~/.config/skillbot/profiles/<name>.env
  with SKILLBOT_USERNAME and SKILLBOT_PASSWORD, typed into the login screen.
- Through the launcher (Bolt, with Jagex-style accounts): the launcher starts RuneLite with
  the character's session in JX_* environment variables. `save-session` copies those, and
  the command that started RuneLite, from the running client into
  ~/.config/superbond2/sessions/<name>.json. Logging that character in later starts RuneLite
  the same way and clicks Play.

Logins and sessions are read here and go nowhere else: not into his prompt, his memory, the
decision log or any message. He only ever knows a character by its name ("main", "iron").

There's one client and one mouse, so superbond2 and skillbot can't both play: `claim`
refuses while a skillbot run is going, and leaves a lock file while superbond2 plays.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from .eyes import Eyes
from .layout import Layout

PROFILES = Path.home() / ".config" / "skillbot" / "profiles"
SESSIONS = Path.home() / ".config" / "superbond2" / "sessions"
NAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
LAUNCH_WAIT = 25.0          # seconds for RuneLite to start and show its login screen


class LoginError(Exception):
    """Couldn't log in or out. The message never includes the login itself."""


def read_env(path: Path) -> dict[str, str]:
    """KEY=value lines (optionally `export`, optionally quoted), as skillbot writes them."""
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def _private_write(path: Path, text: str) -> None:
    """Write a file only its owner can read, in a folder only its owner can open."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


class Characters:
    def __init__(self, folder: Path = PROFILES, sessions: Path = SESSIONS):
        self.folder, self.sessions = Path(folder), Path(sessions)

    def names(self) -> list[str]:
        out = set(self.launched())
        if self.folder.is_dir():
            out |= {p.stem for p in self.folder.glob("*.env")
                    if {"SKILLBOT_USERNAME", "SKILLBOT_PASSWORD"} <= read_env(p).keys()}
        return sorted(out)

    def launched(self) -> list[str]:
        """Characters that sign in through the launcher (a saved session)."""
        if not self.sessions.is_dir():
            return []
        return sorted(p.stem for p in self.sessions.glob("*.json"))

    def save_session(self, name: str, pid: int, proc: Path = Path("/proc")) -> list[str]:
        """Copy the session of the RuneLite running as `pid` (started by the launcher) for
        `name`. Returns the names of the variables saved, never their values."""
        if not NAME.match(name):
            raise LoginError("a character name is letters, digits, - and _ (up to 32)")
        here = Path(proc) / str(pid)
        env = {}
        for item in (here / "environ").read_bytes().split(b"\0"):
            key, _, value = item.decode(errors="replace").partition("=")
            if key.startswith("JX_"):
                env[key] = value
        if not env:
            raise LoginError("that RuneLite wasn't started by the launcher (it has no JX_ "
                             "session): start the character from Bolt, then save")
        cmd = [a.decode(errors="replace") for a in (here / "cmdline").read_bytes().split(b"\0") if a]
        cwd = os.readlink(here / "cwd")
        _private_write(self.sessions / f"{name}.json",
                       json.dumps({"cmd": cmd, "cwd": cwd, "env": env}, indent=1))
        return sorted(env)

    def _session(self, name: str) -> dict:
        return json.loads((self.sessions / f"{name}.json").read_text())

    def _login(self, name: str) -> tuple[str, str]:
        path = self.folder / f"{name}.env"
        env = read_env(path) if path.exists() else {}
        if not env.get("SKILLBOT_USERNAME") or not env.get("SKILLBOT_PASSWORD"):
            known = ", ".join(self.names()) or "none"
            raise LoginError(f"no login for a character called {name!r} (characters: {known}). "
                             f"Add {self.folder}/{name}.env with SKILLBOT_USERNAME and "
                             "SKILLBOT_PASSWORD, as skillbot uses.")
        return env["SKILLBOT_USERNAME"], env["SKILLBOT_PASSWORD"]


class Client:
    """Starting and closing RuneLite, for characters that sign in through the launcher."""

    def __init__(self, proc: Path = Path("/proc"), popen=subprocess.Popen):
        self.proc, self.popen = Path(proc), popen

    def running(self) -> list[int]:
        """RuneLite processes: java running RuneLite, or RuneLite's own executable."""
        out = []
        for d in self.proc.glob("[0-9]*"):
            try:
                args = [a.decode(errors="replace") for a in (d / "cmdline").read_bytes().split(b"\0") if a]
            except OSError:
                continue
            if not args or int(d.name) == os.getpid():
                continue
            exe = Path(args[0]).name.lower()
            if "runelite" in exe or (exe.startswith("java") and
                                     any("runelite" in a.lower() for a in args[1:])):
                out.append(int(d.name))
        return out

    def newest(self) -> int | None:
        def started(pid: int) -> int:
            stat = (self.proc / str(pid) / "stat").read_text()
            return int(stat.rsplit(")", 1)[1].split()[19])
        pids = self.running()
        return max(pids, key=started) if pids else None

    def start(self, session: dict) -> None:
        self.popen(session["cmd"], cwd=session.get("cwd") or None,
                   env={**os.environ, **session["env"]}, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def stop(self, seconds: float = 15) -> None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for pid in self.running():
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
            end = time.monotonic() + seconds
            while self.running() and time.monotonic() < end:
                time.sleep(0.5)
            if not self.running():
                return


class Session:
    """Logs characters in and out: through the game's own login screen, or by starting
    RuneLite with a session the launcher made."""

    def __init__(self, body, eyes: Eyes, characters: Characters, layout: Layout = Layout(),
                 client: Client | None = None):
        self.body, self.eyes, self.characters, self.layout = body, eyes, characters, layout
        self.client = client or Client()
        self.current: str | None = None

    def in_game(self) -> bool:
        return self.eyes.in_game(self.body.grab())

    def _wait_for(self, want: bool, seconds: float) -> bool:
        waited = 0.0
        while waited < seconds:
            if self.in_game() == want:
                return True
            self.body.wait(1.0)
            waited += 1.0
        return self.in_game() == want

    def log_in(self, name: str, attempts: int = 3) -> None:
        if name in self.characters.launched():
            return self._launch_in(name, attempts)
        user, password = self.characters._login(name)
        if self.in_game():
            raise LoginError("already logged in; log out first")
        b, lay = self.body, self.layout
        for _ in range(attempts):
            b.click(lay.login_existing_user)
            b.wait(1.0)
            for _ in range(30):                 # clear a username the client remembered
                b.press_login("backspace")
            b.type_login(user)
            b.press_login("tab")
            b.type_login(password)
            b.press_login("enter")
            b.wait(8.0)
            b.click(lay.login_play)             # "Click here to play"
            if self._wait_for(True, 20):
                self.current = name
                return
            b.press_login("esc")
            b.wait(5.0)
        raise LoginError(f"couldn't log {name} in after {attempts} tries (wrong login, the server "
                         "down, or the login screen's buttons aren't where we think)")

    def _launch_in(self, name: str, attempts: int) -> None:
        if self.in_game():
            raise LoginError("already logged in; log out first")
        session = self.characters._session(name)
        b, lay = self.body, self.layout
        for _ in range(attempts):
            self.client.stop()                  # whichever character's client was open
            self.client.start(session)
            b.wait(LAUNCH_WAIT)
            b.click(lay.login_launcher_play)    # "Play" on a launcher-signed-in login screen
            b.wait(8.0)
            b.click(lay.login_play)             # "Click here to play"
            if self._wait_for(True, 20):
                self.current = name
                return
        raise LoginError(f"couldn't log {name} in through the launcher after {attempts} tries. "
                         f"Its saved session may have run out: start {name} from Bolt and run "
                         f"`python -m superbond2 save-session {name}` again")

    def log_out(self, attempts: int = 6) -> None:
        """From the logout tab. The game refuses for 10 seconds after combat, so it retries."""
        b, lay = self.body, self.layout
        for _ in range(attempts):
            if not self.in_game():
                self.current = None
                return
            b.press_login("esc")                 # close whatever is open
            b.click(lay.tabs["logout"])
            b.wait(0.6)
            b.click(lay.logout_button)
            if self._wait_for(False, 8):
                self.current = None
                return
            b.wait(5.0)
        raise LoginError("couldn't log out (in combat?)")


# --- one client, one mouse ---------------------------------------------------------------
def skillbot_running(run=subprocess.run) -> bool:
    try:
        out = run(["pgrep", "-f", r"skillbot (run|supervise)"], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return bool(out.stdout.strip())


def claim(lock: Path, running=skillbot_running) -> None:
    """Make sure nothing else is driving the client, and say that superbond2 is."""
    if running():
        raise LoginError("skillbot is running. Stop it first (one client, one mouse): its panel's "
                         "Stop, or `systemctl --user stop skillbot`.")
    if lock.exists():
        pid = lock.read_text().strip()
        if pid.isdigit() and Path(f"/proc/{pid}").exists() and int(pid) != os.getpid():
            raise LoginError(f"superbond2 is already playing (process {pid})")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))


def release(lock: Path) -> None:
    if lock.exists() and lock.read_text().strip() == str(os.getpid()):
        lock.unlink()
