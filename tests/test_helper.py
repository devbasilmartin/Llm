import io
import json
import subprocess

import pytest

from superbond2.helper import Helper, write_autostart


class StubDiscord:
    def __init__(self):
        self.posted, self.files, self.inbox = [], [], []

    def post(self, text):
        self.posted.append(text)

    def post_file(self, path, text=""):
        self.files.append((path.name, text))

    def new_messages(self):
        out, self.inbox = self.inbox, []
        return out


class FakeProc:
    def __init__(self, lines=(), code=0, on_start=None):
        self.stdout, self.code, self.signals, self.pid = iter(lines), code, [], 999999
        self.running = True
        if on_start:
            on_start()

    def wait(self, timeout=None):
        self.running = False
        return self.code

    def poll(self):
        return None if self.running else self.code

    def send_signal(self, sig):
        self.signals.append(sig)
        self.running = False

    def kill(self):
        self.running = False


class Popen:
    """Stands in for subprocess.Popen: hands out prepared processes, keeps the commands."""

    def __init__(self, *procs):
        self.procs, self.cmds = list(procs), []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        return self.procs.pop(0)


def ollama(routes):
    def opener(req, timeout=None):
        path = req.full_url.split("11434")[1]
        got = routes[path]
        if isinstance(got, Exception):
            raise got
        if isinstance(got, list):
            return io.BytesIO(b"".join(json.dumps(x).encode() + b"\n" for x in got))
        return io.BytesIO(json.dumps(got).encode())
    return opener


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "data").mkdir(parents=True)
    return r


def helper(repo, popen=None, routes=None):
    d = StubDiscord()
    h = Helper(d, repo=repo, popen=popen or Popen(), opener=ollama(routes or {}), log=lambda s: None)
    return h, d


def wait_for_job(h):
    if h.job:
        h.job[1].join(5)


def test_help_and_unknown_commands(repo):
    h, d = helper(repo)
    h.handle("!help")
    assert "!bakeoff" in d.posted[-1] and d.posted[-1].startswith("```")
    h.handle("!rm -rf /")
    assert d.posted[-1] == "I don't know `!rm`. `!help` lists what I can do."
    h.handle("!models a b c")
    assert "doesn't take those" in d.posted[-1]
    h.handle("!stop")
    assert "`stop` (no !)" in d.posted[-1]


def test_status(repo):
    h, d = helper(repo, routes={"/api/ps": {"models": [{"name": "gemma4:12b"}]}})
    h.handle("!status")
    text = d.posted[-1]
    assert "💤 superbond2 isn't playing." in text and "loaded: gemma4:12b" in text
    assert "Disk free" in text
    import urllib.error
    h.opener = ollama({"/api/ps": urllib.error.URLError("refused")})
    h.handle("!status")
    assert "Can't reach Ollama" in d.posted[-1] and "OLLAMA_HOST=0.0.0.0" in d.posted[-1]


def test_models_and_pull(repo):
    h, d = helper(repo, routes={"/api/tags": {"models": [{"name": "gemma4:12b", "size": 8.1e9}]},
                                "/api/pull": [{"status": "pulling manifest"}] + [
                                    {"status": "pulling", "total": 8e9, "completed": c * 1e9}
                                    for c in range(9)] + [{"status": "success"}]})
    h.handle("!models")
    assert d.posted[-1] == "Models: gemma4:12b (8.1 GB)"
    h.handle("!pull gemma4:12b")
    wait_for_job(h)
    assert d.posted[1] == "⬇️ Downloading gemma4:12b..."
    assert [p for p in d.posted if "%" in p] == ["gemma4:12b: 0% of 8.0 GB", "gemma4:12b: 25% of 8.0 GB",
                                                  "gemma4:12b: 50% of 8.0 GB", "gemma4:12b: 75% of 8.0 GB",
                                                  "gemma4:12b: 100% of 8.0 GB"]
    assert d.posted[-1] == "✅ gemma4:12b is ready."
    h.handle("!pull gemma4:12b;reboot")
    assert "doesn't look like a model name" in d.posted[-1]


def test_a_failed_download_says_how_to_resume(repo):
    h, d = helper(repo, routes={"/api/pull": [{"status": "pulling", "total": 8e9, "completed": 1e9}]})
    h.handle("!pull gemma4:12b")
    wait_for_job(h)
    assert "`!pull gemma4:12b` again resumes it" in d.posted[-1]


def test_the_bakeoff_reports_back_with_the_file(repo):
    out = repo / "bench" / "results"

    def write_report():
        out.mkdir(parents=True)
        (out / "bakeoff-20261025-1200.md").write_text("# results")
    lines = ["=== gemma4:12b\n", "  loaded in 40.0 s\n"] + \
            [f"  [{i:2}/21] d{i} something  ok  (9.0 s)\n" for i in range(1, 22)] + ["| model | score |\n"]
    popen = Popen(FakeProc(lines, on_start=write_report))
    h, d = helper(repo, popen)
    h.handle("!bakeoff gemma4:12b")
    wait_for_job(h)
    assert popen.cmds[0][1:] == ["bench/bakeoff.py", "--host", "http://10.0.2.2:11434",
                                 "--models", "gemma4:12b"]
    assert "=== gemma4:12b" in d.posted and sum(p.startswith("  [") for p in d.posted) == 3
    assert d.posted[-1].startswith("✅ Bake-off done:") and "| model | score |" in d.posted[-1]
    assert d.files == [("bakeoff-20261025-1200.md", "Here's the full report. Send it to Claude.")]


def test_one_long_job_at_a_time_and_kill(repo):
    import threading
    killed = threading.Event()

    def output():                                           # goes on until it's killed
        while not killed.is_set():
            killed.wait(0.01)
            yield "still going\n"
    proc = FakeProc(output())
    proc.send_signal = lambda sig: (proc.signals.append(sig), killed.set())
    h, d = helper(repo, Popen(proc))
    h.handle("!tests")
    import time
    while h.proc is None:
        time.sleep(0.01)
    h.handle("!bakeoff")
    assert d.posted[-1].startswith("Busy with the tests")
    h.handle("!kill")
    assert proc.signals and d.posted[-1] == "Stopped the tests."
    wait_for_job(h)
    assert not h._busy()


def test_play_log_and_kill(repo):
    proc = FakeProc()
    popen = Popen(proc)
    h, d = helper(repo, popen)
    h.handle("!play gemma4:12b iron 90")
    cmd = popen.cmds[0]
    assert cmd[cmd.index("--character") + 1] == "iron" and cmd[cmd.index("--minutes") + 1] == "90"
    assert d.posted[-1].startswith("🎮 Starting him on gemma4:12b as iron for 90 minutes")
    h.handle("!play gemma4:12b")
    assert d.posted[-1].startswith("He's already playing")
    (repo / "data" / "play.log").write_text("".join(f"[{i}] wait -> ok\n" for i in range(30)))
    h.handle("!log 3")
    assert d.posted[-1] == "```\n[27] wait -> ok\n[28] wait -> ok\n[29] wait -> ok\n```"
    h.handle("!play x iron ninety")
    proc.running = False
    h.handle("!play gemma4:12b bad/name")
    assert d.posted[-1] == "`bad/name` isn't a character name."


def test_kill_finds_a_game_it_didnt_start(repo, monkeypatch):
    import os
    child = subprocess.Popen(["sleep", "30"])
    (repo / "data" / "playing.lock").write_text(str(child.pid))
    h, d = helper(repo, routes={"/api/ps": {"models": []}})
    h.handle("!status")
    assert "🎮 superbond2 is playing." in d.posted[-1]
    h.handle("!kill")
    assert d.posted[-1] == "Stopped his play."
    assert child.wait(5) != 0
    os.remove(repo / "data" / "playing.lock")


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def test_update_pulls_and_restarts_when_its_code_changed(tmp_path):
    origin, mine, theirs = tmp_path / "origin.git", tmp_path / "mine", tmp_path / "theirs"
    run(["git", "init", "-q", "--bare", "-b", "bench-bakeoff", str(origin)], tmp_path)
    run(["git", "clone", "-q", str(origin), str(theirs)], tmp_path)
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        run(["git", *args], theirs)
    (theirs / "README.md").write_text("hi\n")
    run(["git", "add", "."], theirs)
    run(["git", "commit", "-qm", "first"], theirs)
    run(["git", "push", "-q", "origin", "HEAD:bench-bakeoff"], theirs)
    run(["git", "clone", "-q", "-b", "bench-bakeoff", str(origin), str(mine)], tmp_path)
    h, d = helper(mine)
    h.handle("!update")
    assert d.posted[-1] == "Already up to date."
    (theirs / "superbond2").mkdir()
    (theirs / "superbond2" / "helper.py").write_text("# new\n")
    run(["git", "add", "."], theirs)
    run(["git", "commit", "-qm", "a better helper"], theirs)
    run(["git", "push", "-q", "origin", "HEAD:bench-bakeoff"], theirs)
    h.handle("!update")
    assert d.posted[-1].endswith("a better helper.") and h.restart


def test_autostart_file(tmp_path):
    path = write_autostart(tmp_path / "autostart" / "superbond2-helper.desktop")
    text = path.read_text()
    assert "-m superbond2 helper" in text and "X-GNOME-Autostart-enabled=true" in text


def test_he_ignores_messages_for_the_helper(tmp_path):
    from superbond2.actions import Actions
    from superbond2.brain import Brain, Owner
    from superbond2.eyes import Eyes
    from superbond2.hands import SimBody
    from superbond2.memory import Memory
    from superbond2.sim import lumbridge
    owner = Owner(log=lambda s: None)
    b = Brain(None, Actions(SimBody(lumbridge()), Eyes()), Memory(tmp_path / "m"), owner,
              log=lambda s: None)
    owner.said += ["!status", "!kill"]
    b.listen()
    assert b.recent == [] and not b.stopped


def test_play_with_a_fast_model_too(repo):
    popen = Popen(FakeProc())
    h, d = helper(repo, popen)
    h.handle("!play gemma4:12b+granite4.1:3b main 30")
    cmd = popen.cmds[0]
    assert cmd[cmd.index("--model") + 1] == "gemma4:12b" and cmd[cmd.index("--fast-model") + 1] == "granite4.1:3b"
    assert d.posted[-1].startswith("🎮 Starting him on gemma4:12b + granite4.1:3b as main for 30 minutes")
    h.playing.running = False
    h.handle("!play gemma4:12b+bad;name")
    assert d.posted[-1] == "`bad;name` doesn't look like a model name."



# --- the watchdog ------------------------------------------------------------------------------
def started(repo, *procs):
    popen = Popen(*procs)
    h, d = helper(repo, popen)
    h.handle("!play gemma4:12b main 60")
    return h, d, popen


def test_a_crash_gets_a_restart_for_the_time_left(repo):
    import time
    first, second = FakeProc(), FakeProc()
    h, d, popen = started(repo, first, second)
    first.running, first.code = False, 1
    (repo / "data" / "play.log").write_text("[12] wait -> ok\nTraceback (most recent call last):\nKeyError: 'x'\n")
    h.watch(now=time.time() + 20 * 60)
    assert len(popen.cmds) == 2 and h.playing is second
    cmd = popen.cmds[1]
    assert cmd[cmd.index("--minutes") + 1] == "40"                  # what's left of the hour
    assert d.posted[-1].startswith("🔁 he crashed (exit code 1); restarting him (restart 1 of 3")
    assert "KeyError: 'x'" in d.posted[-1]
    h.watch()                                                       # running fine: nothing
    assert len(popen.cmds) == 2


def test_a_hang_is_ended_and_restarted(repo):
    import os
    import time
    first, second = FakeProc(), FakeProc()
    h, d, popen = started(repo, first, second)
    beat = repo / "data" / "heartbeat"
    h.watch(now=time.time() + 60)
    assert len(popen.cmds) == 1                                     # a slow turn isn't a hang
    old = time.time() - 16 * 60
    os.utime(beat, (old, old))
    h.watch()
    assert first.signals and h.playing is second
    assert d.posted[-1].startswith("🔁 he hung (nothing for 16 minutes)")


def test_a_clean_finish_is_left_alone(repo):
    proc = FakeProc()
    h, d, popen = started(repo, proc)
    proc.running, proc.code = False, 0
    h.watch()
    assert len(popen.cmds) == 1 and h.play is None


def test_it_gives_up_after_three_restarts_in_an_hour(repo):
    import time
    procs = [FakeProc() for _ in range(5)]
    h, d, popen = started(repo, *procs)
    now = time.time()
    for i in range(4):
        h.playing.running, h.playing.code = False, 1
        h.watch(now=now + i * 60)
    assert len(popen.cmds) == 4 and h.play is None
    assert "3 restarts this hour is enough" in d.posted[-1]


def test_kill_means_no_restart(repo, monkeypatch):
    import os
    proc = FakeProc()
    h, d, popen = started(repo, proc)
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(h, "_playing_pid", lambda: 4242)
    h.handle("!kill")
    proc.running, proc.code = False, 1
    h.watch()
    assert len(popen.cmds) == 1


def test_he_beats_while_he_looks(tmp_path):
    from superbond2 import heartbeat
    from superbond2.actions import Actions
    from superbond2.eyes import Eyes
    from superbond2.hands import SimBody
    from superbond2.sim import lumbridge
    heartbeat.FILE = tmp_path / "heartbeat"
    try:
        Actions(SimBody(lumbridge()), Eyes())
        assert heartbeat.age(heartbeat.FILE, __import__("time").time()) < 5
    finally:
        heartbeat.FILE = None



def test_bakeoff_options(repo):
    popen = Popen(FakeProc(["boom\n"], code=1))
    h, d = helper(repo, popen)
    h.handle("!bakeoff granite4.1:3b qwen3:4b --think off --only d1 D3 i2")
    wait_for_job(h)
    assert popen.cmds[0][1:] == ["bench/bakeoff.py", "--host", "http://10.0.2.2:11434",
                                 "--models", "granite4.1:3b", "qwen3:4b",
                                 "--think", "off", "--only", "d1", "d3", "i2"]
    for bad, says in (("!bakeoff --think maybe", "`--think` takes"),
                      ("!bakeoff --only", "`--only` takes scenario ids"),
                      ("!bakeoff --only d1 ;rm", "(not: ;rm)"),
                      ("!bakeoff --models x", "I don't know `--models`"),
                      ("!bakeoff gemma4:12b;ls", "Not a model name")):
        h.handle(bad)
        assert says in d.posted[-1], bad
    assert len(popen.cmds) == 1
