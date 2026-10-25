"""superbond2 from the command line.

    python -m superbond2 calibrate     # find the RuneLite canvas on the screen (log in first)
    python -m superbond2 look          # what the eyes see right now; draws look.png
    python -m superbond2 sim           # the same for the simulated game; draws sim.png
    python -m superbond2 do click_nearest name=oak_tree    # one action, on the real client
    python -m superbond2 run my-routine.yaml               # a routine (add --sim to try it first)
    python -m superbond2 play --model gemma4:12b           # let him play (add --sim to try it first)
    python -m superbond2 hover                             # read the hover text under the mouse
    python -m superbond2 characters                        # the characters he can log into
    python -m superbond2 save-session iron                 # keep the session Bolt started
    python -m superbond2 play --model gemma4:12b --character main  # he can switch to the others
    python -m superbond2 discord-test                      # check the Discord bot's settings
    python -m superbond2 helper                            # do !jobs asked for on Discord

Mouse into any screen corner stops superbond2 (the kill switch).

Pictures can show the account name, so they're kept out of git (.gitignore).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

from .eyes import Eyes, View, describe

DATA = Path("data")
ORIGIN = DATA / "origin.json"


def draw(img, view: View, path: Path) -> None:
    """The picture with a box and a name on everything the eyes found."""
    out = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    for h in view.highlights:
        b = h.box
        cv2.rectangle(out, (b.x, b.y), (b.x + b.w, b.y + b.h), (0, 255, 0), 1)
        cv2.putText(out, h.name, (b.x, max(b.y - 3, 10)), cv2.FONT_HERSHEY_PLAIN, 0.8, (0, 255, 0))
    cv2.imwrite(str(path), out)


def calibrate(_args) -> int:
    from .screen import find_canvas, grab_desktop
    desktop, (left, top) = grab_desktop()
    at, share = find_canvas(desktop)
    if at is None:
        print(f"Couldn't find the game (best match {share:.0%}). Is RuneLite in fixed mode, "
              "logged in, and fully on screen?")
        return 1
    origin = (left + at[0], top + at[1])
    DATA.mkdir(exist_ok=True)
    ORIGIN.write_text(json.dumps({"origin": origin}))
    print(f"Found the game at {origin} ({share:.0%} of the frame matched). Saved {ORIGIN}.")
    return 0


def look(_args) -> int:
    from .screen import Screen
    eyes, screen = Eyes(), Screen.load(ORIGIN)
    eyes.look(screen.grab())                    # the first look can't tell busy from idle
    img = screen.grab()
    view = eyes.look(img)
    print(describe(view))
    draw(img, view, Path("look.png"))
    print("\nDrew look.png: a green box should be on every highlight.")
    return 0


def do_action(args) -> int:
    from .actions import ACTIONS, Actions, do
    from .hands import RealBody, Stopped
    from .screen import Screen
    if args.action not in {a["function"]["name"] for a in ACTIONS}:
        print("Actions: " + ", ".join(a["function"]["name"] for a in ACTIONS))
        return 1
    kw = {}
    for pair in args.args:
        key, _, value = pair.partition("=")
        kw[key] = int(value) if value.isdigit() else value
    screen = Screen.load(ORIGIN)
    try:
        result = do(Actions(RealBody(screen), Eyes()), args.action, kw)
    except Stopped as e:
        print(f"Stopped: {e}")
        return 1
    print(("OK  " if result.ok else "NO  ") + result.said)
    return 0 if result.ok else 1


def run_routine(args) -> int:
    from .actions import Actions
    from .hands import RealBody, SimBody, Stopped
    from .routines import Routine, RoutineError, Runner
    try:
        routine = Routine.from_yaml(Path(args.file).read_text())
    except (OSError, RoutineError) as e:
        print(f"Can't run it: {e}")
        return 1
    if args.sim:
        from .sim import lumbridge
        body = SimBody(lumbridge())
    else:
        from .screen import Screen
        body = RealBody(Screen.load(ORIGIN))
    try:
        result = Runner(Actions(body, Eyes())).run(routine)
    except Stopped as e:
        print(f"Stopped: {e}")
        return 1
    for line in result.log:
        print("  " + line)
    print(("OK  " if result.ok else "NO  ") + result.said)
    return 0 if result.ok else 1


def play(args) -> int:
    from .actions import Actions
    from .brain import Brain, DiscordOwner, Owner
    from .characters import Characters, LoginError, Session, claim, release
    from .discord import CONFIG, Discord, DiscordError
    from .hands import RealBody, SimBody, Stopped
    from .memory import Memory
    from .model import Ollama
    from .wiki import Wiki
    accounts = [n.strip() for n in (args.characters or "").split(",") if n.strip()]
    start = args.character or (accounts[0] if accounts else None)
    if start and not args.characters:
        accounts = Characters().names()          # he may play any of them
    if start and start not in accounts:
        accounts.insert(0, start)
    if args.sim:
        from .sim import lumbridge
        body, folder = SimBody(lumbridge()), DATA / "sim-memory"
        start, accounts = None, []
    else:
        from .screen import Screen
        body, folder = RealBody(Screen.load(ORIGIN)), DATA / "memory"
    folder = Path(args.memory) if args.memory else folder
    think = {"on": True, "off": False}.get(args.think, args.think) if args.think else None
    model = Ollama(args.model, args.host, think=think)
    fast = Ollama(args.fast_model, args.host, think=False) if args.fast_model else None
    wiki = None if args.no_wiki else Wiki(DATA / "wiki-cache")
    eyes = Eyes()
    session = Session(body, eyes, Characters()) if start else None
    owner = Owner()
    if not args.no_discord and CONFIG.exists():
        try:
            discord = Discord.from_config()
            discord.hello()
            discord.new_messages()                   # start from now
            owner = DiscordOwner(discord)
        except DiscordError as e:
            print(f"Discord is off: {e}")
    lock = DATA / "playing.lock"
    try:
        if not args.sim:
            claim(lock)
        if session is not None:
            if session.in_game():
                session.log_out()
            print(f"Logging in {start}...")
            session.log_in(start)
        brain = Brain(model, Actions(body, eyes), Memory(folder), owner, wiki=wiki,
                      session=session, character=start, accounts=accounts, fast=fast)
        owner.tell(f"👋 Playing{' ' + start if start else ''} now.")
        others = [a for a in accounts if a != start]
        print(f"superbond2 is playing{' ' + start if start else ''} with {args.model}"
              f"{' (and ' + args.fast_model + ' for quick turns)' if fast else ''}; memory in "
              f"{folder}." + (f" He can switch to: {', '.join(others)}." if others else "") +
              " Mouse into a corner stops him.")
        print(brain.play(turns=args.turns, minutes=args.minutes))
        if session is not None and args.log_out:
            session.log_out()
    except Stopped as e:
        print(f"Stopped: {e}")
        owner.tell(f"🛑 Stopped from the PC: {e}")
    except LoginError as e:
        print(f"Can't go on: {e}")
        owner.tell(f"⚠️ I've had to stop: {e}")
        return 1
    finally:
        if not args.sim:
            release(lock)
    return 0


def discord_test(_args) -> int:
    from .discord import CONFIG, HELP, Discord, DiscordError
    try:
        d = Discord.from_config()
        print("Gateway: " + ("connected once" if d.hello() else
                             "skipped (pip install websocket-client to connect once)"))
        d.post("👋 superbond2 here! This is a test. " + HELP)
        print("Posted a test message. Reply in the channel within 60 seconds...")
        d.new_messages()
        import time
        for _ in range(12):
            time.sleep(5)
            heard = d.new_messages()
            if heard:
                print(f"Heard you: {heard[0]!r}. Discord works both ways.")
                d.post("Got it, I can hear you. 🎉")
                return 0
        print("Heard nothing. If you replied: turn on Message Content Intent for the bot in "
              f"the Developer Portal, and check DISCORD_OWNER_ID in {CONFIG}.")
        return 1
    except DiscordError as e:
        print(f"Couldn't: {e}")
        return 1


def helper(args) -> int:
    from .discord import Discord, DiscordError
    from .helper import Helper, write_autostart
    if args.autostart:
        print(f"Wrote {write_autostart()}: the helper starts with the desktop from now on.")
        return 0
    try:
        Helper(Discord.from_config(), host=args.host).serve()
    except DiscordError as e:
        print(f"Couldn't: {e}")
        return 1
    return 0


def hover(_args) -> int:
    from .screen import Screen
    from .text import Reader
    reader = Reader()
    img = Screen.load(ORIGIN).grab()
    pic, kind = reader.prepare(reader.layout.hover_text.crop(img))
    cv2.imwrite("hover.png", pic)
    cv2.imwrite("hover-raw.png", cv2.cvtColor(reader.layout.hover_text.crop(img), cv2.COLOR_RGB2BGR))
    try:
        h = reader.hover(img)
    except RuntimeError as e:
        print(e)
        return 1
    print(f"Read: {h.text!r} -> name {h.name!r}, a {h.kind}" if h else "Read: nothing (Walk here)")
    print("Saved hover-raw.png (what was there) and hover.png (what was read).")
    return 0


def characters(_args) -> int:
    from .characters import PROFILES, SESSIONS, Characters
    c = Characters()
    names = c.names()
    if names:
        launched = set(c.launched())
        print("Characters superbond2 can log into: " + ", ".join(
            f"{n} ({'launcher' if n in launched else 'password'})" for n in names))
    else:
        print("No characters yet. Either:\n"
              "- launcher: start the character from Bolt, then `python -m superbond2 save-session NAME`\n"
              f"- password: a file {PROFILES}/<name>.env with SKILLBOT_USERNAME=... and "
              "SKILLBOT_PASSWORD=... (the same files skillbot uses)")
    print(f"(Launcher sessions are kept in {SESSIONS}.)")
    return 0


def save_session(args) -> int:
    from .characters import SESSIONS, Characters, Client, LoginError
    pid = Client().newest()
    if pid is None:
        print("RuneLite isn't running. Start the character from Bolt first.")
        return 1
    try:
        keys = Characters().save_session(args.name, pid)
    except (LoginError, OSError) as e:
        print(f"Couldn't: {e}")
        return 1
    print(f"Saved {args.name}'s session ({', '.join(keys)}) in {SESSIONS}/{args.name}.json, "
          "readable only by you.")
    return 0


def login(args) -> int:
    from .characters import Characters, LoginError, Session
    from .hands import RealBody, Stopped
    from .screen import Screen
    session = Session(RealBody(Screen.load(ORIGIN)), Eyes(), Characters())
    try:
        if args.name:
            session.log_in(args.name)
            print(f"Logged in {args.name}.")
        else:
            session.log_out()
            print("Logged out.")
    except (LoginError, Stopped) as e:
        print(f"Couldn't: {e}")
        return 1
    return 0


def sim(_args) -> int:
    from .sim import lumbridge
    game, eyes = lumbridge(), Eyes()
    eyes.look(game.grab())
    game.click(game.things[0].box.center)       # start chopping the first oak
    game.advance(30)
    img = game.grab()
    view = eyes.look(img)
    print(describe(view))
    draw(img, view, Path("sim.png"))
    print("\nDrew sim.png.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="superbond2", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn in (("calibrate", calibrate), ("look", look), ("sim", sim), ("hover", hover)):
        sub.add_parser(name).set_defaults(fn=fn)
    d = sub.add_parser("do", help="one action on the real client, e.g. do click_nearest name=bank")
    d.add_argument("action")
    d.add_argument("args", nargs="*", help="key=value, e.g. name=oak_tree or seconds=10")
    d.set_defaults(fn=do_action)
    r = sub.add_parser("run", help="run a routine from a YAML file")
    r.add_argument("file")
    r.add_argument("--sim", action="store_true", help="on the simulated game, not the client")
    r.set_defaults(fn=run_routine)
    pl = sub.add_parser("play", help="let superbond2 play")
    pl.add_argument("--model", required=True, help="an Ollama model, e.g. gemma4:12b")
    pl.add_argument("--fast-model", help="a small model for everyday turns, e.g. granite4.1:3b; "
                                         "--model then thinks things over")
    pl.add_argument("--host", default="http://10.0.2.2:11434",
                    help="where Ollama is (default: the Windows host, seen from the VM)")
    pl.add_argument("--sim", action="store_true", help="on the simulated game, not the client")
    pl.add_argument("--turns", type=int, default=50)
    pl.add_argument("--minutes", type=float, default=60)
    pl.add_argument("--think", help="on, off, or low/medium/high for gpt-oss")
    pl.add_argument("--memory", help="memory folder (default data/memory, or data/sim-memory)")
    pl.add_argument("--no-wiki", action="store_true", help="play without the OSRS Wiki")
    pl.add_argument("--character", help="start on this character; he can switch to the others")
    pl.add_argument("--characters", help="only these may be played, comma separated "
                                         "(default: all of them); he starts on the first")
    pl.add_argument("--log-out", action="store_true", help="log out at the end")
    pl.add_argument("--no-discord", action="store_true", help="don't post to Discord")
    hp = sub.add_parser("helper", help="do jobs asked for on Discord (!help lists them)")
    hp.add_argument("--host", default="http://10.0.2.2:11434", help="where Ollama is")
    hp.add_argument("--autostart", action="store_true", help="start it with the desktop from now on")
    hp.set_defaults(fn=helper)
    sub.add_parser("discord-test", help="post a test message and wait for a reply").set_defaults(
        fn=discord_test)
    sub.add_parser("characters", help="the characters he can log into").set_defaults(fn=characters)
    ss = sub.add_parser("save-session", help="keep the session of the RuneLite Bolt just started")
    ss.add_argument("name", help="what to call the character, e.g. main or iron")
    ss.set_defaults(fn=save_session)
    li = sub.add_parser("login", help="log a character in")
    li.add_argument("name")
    li.set_defaults(fn=login)
    sub.add_parser("logout", help="log out").set_defaults(fn=login, name=None)
    pl.set_defaults(fn=play)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
