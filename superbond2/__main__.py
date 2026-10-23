"""superbond2 from the command line.

    python -m superbond2 calibrate     # find the RuneLite canvas on the screen (log in first)
    python -m superbond2 look          # what the eyes see right now; draws look.png
    python -m superbond2 sim           # the same for the simulated game; draws sim.png
    python -m superbond2 do click_nearest name=oak_tree    # one action, on the real client
    python -m superbond2 run my-routine.yaml               # a routine (add --sim to try it first)

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
    for name, fn in (("calibrate", calibrate), ("look", look), ("sim", sim)):
        sub.add_parser(name).set_defaults(fn=fn)
    d = sub.add_parser("do", help="one action on the real client, e.g. do click_nearest name=bank")
    d.add_argument("action")
    d.add_argument("args", nargs="*", help="key=value, e.g. name=oak_tree or seconds=10")
    d.set_defaults(fn=do_action)
    r = sub.add_parser("run", help="run a routine from a YAML file")
    r.add_argument("file")
    r.add_argument("--sim", action="store_true", help="on the simulated game, not the client")
    r.set_defaults(fn=run_routine)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
