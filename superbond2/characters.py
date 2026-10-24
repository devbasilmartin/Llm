"""superbond2's characters: logging in and out, and staying out of skillbot's way.

The logins are skillbot's: one file per character in ~/.config/skillbot/profiles/<name>.env
with SKILLBOT_USERNAME and SKILLBOT_PASSWORD. They're read here when logging in and go
nowhere else: not into his prompt, his memory, the decision log or any message. He only
ever knows a character by its profile name ("main", "alt").

There's one client and one mouse, so superbond2 and skillbot can't both play: `claim`
refuses while a skillbot run is going, and leaves a lock file while superbond2 plays.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .eyes import Eyes
from .layout import Layout

PROFILES = Path.home() / ".config" / "skillbot" / "profiles"


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


class Characters:
    def __init__(self, folder: Path = PROFILES):
        self.folder = Path(folder)

    def names(self) -> list[str]:
        if not self.folder.is_dir():
            return []
        return sorted(p.stem for p in self.folder.glob("*.env")
                      if {"SKILLBOT_USERNAME", "SKILLBOT_PASSWORD"} <= read_env(p).keys())

    def _login(self, name: str) -> tuple[str, str]:
        path = self.folder / f"{name}.env"
        env = read_env(path) if path.exists() else {}
        if not env.get("SKILLBOT_USERNAME") or not env.get("SKILLBOT_PASSWORD"):
            known = ", ".join(self.names()) or "none"
            raise LoginError(f"no login for a character called {name!r} (characters: {known}). "
                             f"Add {self.folder}/{name}.env with SKILLBOT_USERNAME and "
                             "SKILLBOT_PASSWORD, as skillbot uses.")
        return env["SKILLBOT_USERNAME"], env["SKILLBOT_PASSWORD"]


class Session:
    """Logs characters in and out through the game's own login screen."""

    def __init__(self, body, eyes: Eyes, characters: Characters, layout: Layout = Layout()):
        self.body, self.eyes, self.characters, self.layout = body, eyes, characters, layout
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
