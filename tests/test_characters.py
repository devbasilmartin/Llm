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
