import os

import pytest

from superbond2.actions import Actions
from superbond2.characters import Characters, LoginError, Session, claim, read_env, release
from superbond2.eyes import Eyes
from superbond2.hands import SimBody
from superbond2.memory import Memory
from superbond2.sim import lumbridge

EYES = Eyes()
USER, PASSWORD = "Superbond2", "hunter2-secret"


@pytest.fixture
def profiles(tmp_path):
    d = tmp_path / "profiles"
    d.mkdir()
    (d / "main.env").write_text(f'export SKILLBOT_USERNAME="{USER}"\nSKILLBOT_PASSWORD={PASSWORD}\n')
    (d / "alt.env").write_text("SKILLBOT_USERNAME=alt_name\nSKILLBOT_PASSWORD='alt pass'\n# a comment\n")
    (d / "half.env").write_text("SKILLBOT_USERNAME=nopassword\n")
    return Characters(d)


@pytest.fixture
def game():
    g = lumbridge()
    g.accounts = {USER: PASSWORD, "alt_name": "alt pass"}
    g.screen = "login"
    return g


def test_reads_skillbots_profile_files(profiles, tmp_path):
    assert profiles.names() == ["alt", "main"]          # half.env has no password
    assert read_env(tmp_path / "profiles" / "alt.env") == {"SKILLBOT_USERNAME": "alt_name",
                                                          "SKILLBOT_PASSWORD": "alt pass"}
    assert Characters(tmp_path / "nowhere").names() == []


def test_logs_in_and_out(profiles, game):
    s = Session(SimBody(game), EYES, profiles)
    assert not s.in_game()
    s.log_in("main")
    assert s.in_game() and s.current == "main" and game.player_name == USER
    s.log_out()
    assert not s.in_game() and s.current is None
    s.log_in("alt")
    assert game.player_name == "alt_name"


def test_a_remembered_username_is_cleared_first(profiles, game):
    game._fields = ["leftover", ""]                     # the client remembered something
    Session(SimBody(game), EYES, profiles).log_in("main")
    assert game.player_name == USER


def test_bad_logins_fail_without_saying_the_login(profiles, game):
    game.accounts = {USER: "a different password"}
    with pytest.raises(LoginError) as e:
        Session(SimBody(game), EYES, profiles).log_in("main")
    assert "couldn't log main in after 3 tries" in str(e.value)
    with pytest.raises(LoginError) as e:
        Session(SimBody(game), EYES, profiles).log_in("half")
    assert "no login for a character called 'half'" in str(e.value)
    for err in (str(e.value),):
        assert PASSWORD not in err and USER not in err


def test_logging_in_while_in_game_is_refused(profiles):
    with pytest.raises(LoginError, match="already logged in"):
        Session(SimBody(lumbridge()), EYES, profiles).log_in("main")


def test_he_is_logged_back_in_after_a_disconnect_and_never_sees_the_login(profiles, game, tmp_path):
    from test_brain import Scripted
    from superbond2.brain import Brain, Owner
    session = Session(SimBody(game), EYES, profiles)
    session.log_in("main")
    memory = Memory(tmp_path / "memory")
    model = Scripted(("wait", {"seconds": 1}), ("wait", {"seconds": 1}))
    b = Brain(model, Actions(SimBody(game), EYES), memory, Owner(log=lambda s: None),
              log=lambda s: None, session=session, character="main")
    b.turn()
    game.screen = "login"                               # disconnected
    b.turn()
    assert game.screen == "game"
    assert "2. you were logged out; logged back in" in model.prompts[1]
    everything = "".join(model.prompts) + memory.decisions_file.read_text() + \
        "".join(p.read_text() for p in memory.folder.rglob("*") if p.is_file())
    assert PASSWORD not in everything and USER not in everything


def test_one_client_one_mouse(tmp_path):
    lock = tmp_path / "playing.lock"
    with pytest.raises(LoginError, match="skillbot is running"):
        claim(lock, running=lambda: True)
    claim(lock, running=lambda: False)
    assert lock.read_text() == str(os.getpid())
    claim(lock, running=lambda: False)                  # our own lock is fine
    release(lock)
    assert not lock.exists()
    lock.write_text("1")                                # pid 1 is alive, and isn't us
    with pytest.raises(LoginError, match="already playing"):
        claim(lock, running=lambda: False)


# --- launcher (Bolt) characters --------------------------------------------------------------
SESSION_ID = "jx-session-secret"


def fake_process(proc, pid, cmd, env=None, started=100):
    d = proc / str(pid)
    d.mkdir(parents=True)
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in cmd) + b"\0")
    (d / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in (env or {}).items()))
    (d / "stat").write_text(f"{pid} (java) S " + " ".join(["0"] * 18) + f" {started} 0 0")
    (d / "cwd").symlink_to(proc)
    return d


RUNELITE = ["/opt/bolt/java/bin/java", "-jar", "/home/me/.local/share/bolt/RuneLite.jar"]
JX = {"JX_SESSION_ID": SESSION_ID, "JX_CHARACTER_ID": "12345", "JX_DISPLAY_NAME": "Iron Bond"}


def test_saves_the_launchers_session_privately(tmp_path):
    proc = tmp_path / "proc"
    fake_process(proc, 4321, RUNELITE, {"HOME": "/home/me", **JX})
    chars = Characters(tmp_path / "profiles", tmp_path / "sessions")
    keys = chars.save_session("iron", 4321, proc=proc)
    assert keys == ["JX_CHARACTER_ID", "JX_DISPLAY_NAME", "JX_SESSION_ID"]   # names, not values
    saved = tmp_path / "sessions" / "iron.json"
    assert oct(saved.stat().st_mode & 0o777) == "0o600"
    assert oct(saved.parent.stat().st_mode & 0o777) == "0o700"
    s = chars._session("iron")
    assert s["env"] == JX and s["cmd"] == RUNELITE                          # HOME isn't kept
    assert chars.names() == ["iron"] and chars.launched() == ["iron"]


def test_a_client_the_launcher_didnt_start_cant_be_saved(tmp_path):
    proc = tmp_path / "proc"
    fake_process(proc, 4321, RUNELITE, {"HOME": "/home/me"})
    chars = Characters(tmp_path / "profiles", tmp_path / "sessions")
    with pytest.raises(LoginError, match="start the character from Bolt"):
        chars.save_session("iron", 4321, proc=proc)
    with pytest.raises(LoginError, match="letters, digits"):
        chars.save_session("../oops", 4321, proc=proc)


def test_finds_the_newest_runelite_and_nothing_else(tmp_path):
    from superbond2.characters import Client
    proc = tmp_path / "proc"
    fake_process(proc, 10, RUNELITE, started=50)
    fake_process(proc, 11, ["/usr/bin/python3", "-m", "superbond2", "save-session", "runelite"])
    fake_process(proc, 12, ["/usr/bin/bolt-launcher"])
    fake_process(proc, 13, ["/home/me/RuneLite.AppImage"], started=90)
    fake_process(proc, 9, RUNELITE, started=70)
    client = Client(proc)
    assert sorted(client.running()) == [9, 10, 13]
    assert client.newest() == 13


class FakeClient:
    """Starting RuneLite with a session, on the simulated game."""

    def __init__(self, game):
        self.game, self.started = game, []

    def start(self, session):
        self.started.append(session)
        self.game.screen, self.game.player_name = "title", session["env"]["JX_DISPLAY_NAME"]

    def stop(self):
        self.game.screen = "closed"


@pytest.fixture
def both(tmp_path, profiles):
    proc = tmp_path / "proc"
    fake_process(proc, 4321, RUNELITE, JX)
    chars = Characters(profiles.folder, tmp_path / "sessions")
    chars.save_session("iron", 4321, proc=proc)
    return chars


def test_a_launcher_character_logs_in_by_starting_runelite(both, game):
    client = FakeClient(game)
    s = Session(SimBody(game), EYES, both, client=client)
    assert both.names() == ["alt", "iron", "main"]
    s.log_in("main")                                    # password characters still type
    s.log_out()
    s.log_in("iron")
    assert s.in_game() and s.current == "iron" and game.player_name == "Iron Bond"
    assert client.started[0]["env"]["JX_SESSION_ID"] == SESSION_ID


def test_a_run_out_session_says_how_to_renew_it(both, game):
    game.session_ok = False
    with pytest.raises(LoginError) as e:
        Session(SimBody(game), EYES, both, client=FakeClient(game)).log_in("iron")
    assert "save-session iron" in str(e.value) and SESSION_ID not in str(e.value)


# --- switching accounts himself ------------------------------------------------------------
def test_he_switches_accounts_when_he_feels_like_it(both, game, tmp_path):
    from test_brain import Scripted
    from superbond2.brain import SWITCH_COOLDOWN, Brain, Owner
    told = []
    session = Session(SimBody(game), EYES, both, client=FakeClient(game))
    session.log_in("main")
    memory = Memory(tmp_path / "memory")
    memory.accounts_file.write_text("main: my main, the highest level\niron: ironman\n")
    model = Scripted(("set_goal", {"goal": "60 woodcutting", "reason": "oaks"}),
                     ("switch_character", {"name": "iron", "reason": "bored"}),
                     ("switch_character", {"name": "iron", "reason": "bored"}),
                     ("switch_character", {"name": "nope", "reason": "?"}),
                     ("set_goal", {"goal": "Vampyre Slayer", "reason": "iron needs it"}))
    b = Brain(model, Actions(SimBody(game), EYES), memory, Owner(log=told.append),
              log=lambda s: None, session=session, character="main",
              accounts=["main", "iron", "alt"])
    b.turn()
    assert "You're playing main (my main, the highest level). Your other accounts: " \
           "iron (ironman), alt." in model.prompts[0]
    assert "a fair go" in b.turn().result                # too soon
    b.turns = SWITCH_COOLDOWN
    t = b.turn()
    assert t.ok and t.result == "logged out of main and into iron. iron has no goal yet: pick one with set_goal"
    assert game.player_name == "Iron Bond" and b.character == "iron"
    assert "[to owner] Switched from main to iron. Why: bored" in told
    assert "no account called 'nope'" in b.turn().result
    b.turn()
    assert memory.goal()["goal"] == "Vampyre Slayer"     # iron's goal...
    memory.play_as("main")
    assert memory.goal()["goal"] == "60 woodcutting"     # ...and main's is still there
    assert "You're playing iron (ironman)" in model.prompts[-1]
    everything = "".join(model.prompts) + "".join(
        p.read_text() for p in memory.folder.rglob("*") if p.is_file())
    for secret in (SESSION_ID, PASSWORD, USER):
        assert secret not in everything


def test_one_account_means_no_switching(game, tmp_path):
    from test_brain import Scripted
    from superbond2.brain import Brain, Owner
    model = Scripted(("switch_character", {"name": "alt", "reason": "x"}))
    b = Brain(model, Actions(SimBody(game), EYES), Memory(tmp_path / "m"), Owner(log=lambda s: None),
              log=lambda s: None)
    assert "only have this one account" in b.turn().result
    assert "Your other accounts" not in model.prompts[0]
