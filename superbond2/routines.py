"""Routines: short action lists superbond2 writes, saves and replays without thinking about
every click.

A routine is YAML, kept simple enough for a small model to write:

    name: chop oaks and bank
    about: Chop oaks until the inventory is full, then bank. Twice.
    steps:
      - repeat: 2
        do:
          - repeat:
            until: inventory full
            do:
              - if: idle and see oak_tree
                then:
                  - click_nearest: oak_tree
              - wait: 2
          - click_nearest: bank

A step is one of:
- an action, written `action: argument`: click_nearest, click_item, click_slot, drop_all,
  press, wait, wait_until_idle (see actions.py)
- `repeat: N` (a number of times) or `repeat:` with `until: <condition>`, and `do:` steps
- `if: <condition>`, `then:` steps, and optionally `else:` steps
- `stop: <why>`, which ends the routine

Conditions are short phrases, joined with `and`, each optionally starting with `not`:
inventory full, inventory empty, free slots below N, idle, busy, hp below N%, hp above N%,
see <highlight>, have <item>, in game.

A routine stops when it runs out of steps, at a `stop`, when an action fails (it says which
step and why), or when it hits its limits on actions and time, so a loop that never ends
can't run forever.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from .actions import ACTIONS, Actions, Result, changes
from .eyes import View
from .layout import SLOTS

ACTION_NAMES = [a["function"]["name"] for a in ACTIONS]
INT_ACTIONS = {"click_slot", "wait", "wait_until_idle"}
ARG = {"click_nearest": "name", "click_item": "item", "click_slot": "slot", "drop_all": "item",
       "press": "key", "wait": "seconds", "wait_until_idle": "timeout"}
MAX_STEPS = 40          # in the whole routine, counting nested ones
MAX_DEPTH = 4
MAX_REPEAT = 100        # passes of one repeat


class RoutineError(ValueError):
    """The routine can't be run as written. The message says what to fix."""


# --- conditions ---------------------------------------------------------------------------
CONDITIONS: list[tuple[str, Callable]] = [
    (r"inventory full", lambda v: v.free_slots == 0),
    (r"inventory empty", lambda v: v.free_slots == SLOTS),
    (r"free slots below (\d+)", lambda v, n: v.free_slots < int(n)),
    (r"idle", lambda v: v.busy is False),
    (r"busy", lambda v: v.busy is True),
    (r"hp below (\d+)%", lambda v, n: v.hp is not None and v.hp * 100 < int(n)),
    (r"hp above (\d+)%", lambda v, n: v.hp is not None and v.hp * 100 > int(n)),
    (r"see ([a-z0-9_]+)", lambda v, name: v.count(name) > 0),
    (r"have ([a-z0-9_]+)", lambda v, item: bool(v.slots_with(item))),
    (r"in game", lambda v: v.in_game),
]
CONDITION_HELP = ("inventory full, inventory empty, free slots below N, idle, busy, "
                  "hp below N%, hp above N%, see <highlight>, have <item>, in game")


def condition(text: str) -> Callable[[View], bool]:
    """'idle and not see oak_tree' -> a test on a View."""
    tests = []
    for part in str(text).strip().lower().split(" and "):
        part = part.strip()
        negate = part.startswith("not ")
        if negate:
            part = part[4:].strip()
        for pattern, fn in CONDITIONS:
            m = re.fullmatch(pattern, part)
            if m:
                tests.append((negate, fn, m.groups()))
                break
        else:
            raise RoutineError(f"I don't understand the condition {part!r}. "
                               f"Conditions are: {CONDITION_HELP}")
    return lambda v: all(fn(v, *args) != negate for negate, fn, args in tests)


# --- steps --------------------------------------------------------------------------------
@dataclass
class Step:
    kind: str                       # action / repeat / if / stop
    text: str                       # how it reads, for reports
    action: str = ""
    arg: object = None
    times: int | None = None        # repeat N
    until: Callable | None = None   # repeat until
    test: Callable | None = None    # if
    then: list["Step"] = field(default_factory=list)
    other: list["Step"] = field(default_factory=list)


def parse_steps(raw, depth: int = 1, where: str = "steps") -> list[Step]:
    if not isinstance(raw, list) or not raw:
        raise RoutineError(f"{where} must be a list with at least one step")
    if depth > MAX_DEPTH:
        raise RoutineError(f"too deeply nested at {where}: at most {MAX_DEPTH} levels")
    return [parse_step(s, depth, f"{where}[{i + 1}]") for i, s in enumerate(raw)]


def parse_step(raw, depth: int, where: str) -> Step:
    if not isinstance(raw, dict) or not raw:
        raise RoutineError(f"{where} should look like `click_nearest: oak_tree`, got {raw!r}")
    keys = set(raw)
    if "repeat" in keys:
        if keys - {"repeat", "until", "do"} or "do" not in keys:
            raise RoutineError(f"{where}: a repeat has `repeat:`, `do:` and optionally `until:`")
        times, until = raw["repeat"], raw.get("until")
        if until is None and not (isinstance(times, int) and 1 <= times <= MAX_REPEAT):
            raise RoutineError(f"{where}: `repeat:` needs a number 1-{MAX_REPEAT}, or `until:` "
                               "a condition")
        text = f"repeat until {until}" if until is not None else f"repeat {times}"
        return Step("repeat", text, times=times if isinstance(times, int) else None,
                    until=condition(until) if until is not None else None,
                    then=parse_steps(raw["do"], depth + 1, f"{where}.do"))
    if "if" in keys:
        if keys - {"if", "then", "else"} or "then" not in keys:
            raise RoutineError(f"{where}: an if has `if:`, `then:` and optionally `else:`")
        return Step("if", f"if {raw['if']}", test=condition(raw["if"]),
                    then=parse_steps(raw["then"], depth + 1, f"{where}.then"),
                    other=parse_steps(raw["else"], depth + 1, f"{where}.else") if "else" in raw else [])
    if keys == {"stop"}:
        return Step("stop", f"stop: {raw['stop']}", arg=str(raw["stop"]))
    if len(keys) != 1:
        raise RoutineError(f"{where}: one action per step, got {', '.join(sorted(keys))}")
    (name, arg), = raw.items()
    if name not in ARG:
        raise RoutineError(f"{where}: there's no action or step called {name!r}. Actions: "
                           f"{', '.join(ACTION_NAMES)}; steps: repeat, if, stop")
    if name in INT_ACTIONS:
        if not isinstance(arg, (int, float)) or isinstance(arg, bool):
            raise RoutineError(f"{where}: {name} needs a number, got {arg!r}")
    elif not isinstance(arg, (str, int)) or arg in ("", None):
        raise RoutineError(f"{where}: {name} needs a name, got {arg!r}")
    return Step("action", f"{name}: {arg}", action=name, arg=arg)


def count_steps(steps: list[Step]) -> int:
    return sum(1 + count_steps(s.then) + count_steps(s.other) for s in steps)


@dataclass
class Routine:
    name: str
    about: str
    steps: list[Step]
    source: dict                    # as written, for saving
    max_actions: int = 300
    max_minutes: float = 30

    @classmethod
    def from_dict(cls, raw) -> "Routine":
        if not isinstance(raw, dict):
            raise RoutineError("a routine is a mapping with name, about and steps")
        unknown = set(raw) - {"name", "about", "steps", "max_actions", "max_minutes", "stats"}
        if unknown:
            raise RoutineError(f"unknown keys: {', '.join(sorted(unknown))}. A routine has "
                               "name, about, steps, and optionally max_actions, max_minutes")
        name = str(raw.get("name", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9 _'-]{1,59}", name):
            raise RoutineError("the name should be 2-60 lower-case letters, digits, spaces, "
                               f"_ - or ', got {name!r}")
        if not str(raw.get("about", "")).strip():
            raise RoutineError("`about:` should say in a sentence what the routine does")
        steps = parse_steps(raw.get("steps"))
        if count_steps(steps) > MAX_STEPS:
            raise RoutineError(f"too many steps: {count_steps(steps)}, at most {MAX_STEPS}. "
                               "Split it into smaller routines.")
        r = cls(name, str(raw["about"]).strip(), steps,
                {k: v for k, v in raw.items() if k != "stats"})
        r.max_actions = min(int(raw.get("max_actions", 300)), 2000)
        r.max_minutes = min(float(raw.get("max_minutes", 30)), 240)
        return r

    @classmethod
    def from_yaml(cls, text: str) -> "Routine":
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise RoutineError(f"that isn't valid YAML: {e}") from None
        return cls.from_dict(raw)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.source, sort_keys=False, allow_unicode=True)


# --- running ------------------------------------------------------------------------------
class Finished(Exception):
    def __init__(self, ok: bool, why: str):
        super().__init__(why)
        self.ok, self.why = ok, why


@dataclass
class RunResult:
    ok: bool
    said: str
    actions: int
    log: list[str]

    def __str__(self) -> str:
        return self.said


class Runner:
    """Runs routines with Actions. `guard`, if given, is called with the newest View after
    every action and can return a reason to stop (the survival reflexes hook in here)."""

    def __init__(self, actions: Actions, guard: Callable[[View], str | None] | None = None,
                 clock: Callable[[], float] | None = None):
        self.actions = actions
        self.guard = guard
        self.clock = clock or time.monotonic

    def run(self, routine: Routine) -> RunResult:
        self.routine, self.count, self.log = routine, 0, []
        self.deadline = self.clock() + routine.max_minutes * 60
        act = self.actions
        start = act.look()
        try:
            self._steps(routine.steps)
            ok, why = True, "done"
        except Finished as f:
            ok, why = f.ok, f.why
        said = (f"{routine.name}: {why} after {self.count} actions. "
                f"Overall: {changes(start, act.view)}")
        return RunResult(ok, said, self.count, self.log)

    def _steps(self, steps: list[Step]) -> None:
        for step in steps:
            self._step(step)

    def _step(self, step: Step) -> None:
        view = self.actions.view
        if step.kind == "stop":
            raise Finished(True, f"stopped ({step.arg})")
        if step.kind == "if":
            self._steps(step.then if step.test(view) else step.other)
        elif step.kind == "repeat":
            passes = 0
            while True:
                if step.until is not None and step.until(self.actions.view):
                    return
                if step.times is not None and passes >= step.times:
                    return
                if passes >= MAX_REPEAT:
                    raise Finished(False, f"`{step.text}` went round {MAX_REPEAT} times without "
                                          "its condition coming true")
                passes += 1
                done = self.count
                self._steps(step.then)
                if self.count == done:
                    raise Finished(False, f"`{step.text}` did a pass without any action, so it "
                                          "would never change anything (add a wait?)")
        else:
            self._act(step)

    def _act(self, step: Step) -> None:
        if self.count >= self.routine.max_actions:
            raise Finished(False, f"hit its limit of {self.routine.max_actions} actions")
        if self.clock() > self.deadline:
            raise Finished(False, f"hit its limit of {self.routine.max_minutes:g} minutes")
        self.count += 1
        result: Result = getattr(self.actions, step.action)(step.arg)
        self.log.append(f"{step.text} -> {result.said}")
        if not result.ok:
            raise Finished(False, f"`{step.text}` failed: {result.said}")
        if self.guard is not None:
            why = self.guard(self.actions.view)
            if why:
                raise Finished(False, f"stopped by a reflex: {why}")


# --- the library --------------------------------------------------------------------------
class Library:
    """superbond2's saved routines: one YAML file each, with how they've gone so far."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.folder / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".yaml")

    def save(self, text: str) -> Routine:
        """Check a routine he wrote and keep it; raises RoutineError with what to fix.
        Saving over an existing routine keeps its stats."""
        routine = Routine.from_yaml(text)
        old = self.stats(routine.name)
        self._write(routine, old)
        return routine

    def load(self, name: str) -> Routine:
        p = self.path(name)
        if not p.exists():
            known = ", ".join(self.names()) or "none yet"
            raise RoutineError(f"there's no routine called {name!r} (saved: {known})")
        return Routine.from_yaml(p.read_text())

    def names(self) -> list[str]:
        return sorted(yaml.safe_load(p.read_text())["name"] for p in self.folder.glob("*.yaml"))

    def stats(self, name: str) -> dict:
        p = self.path(name)
        if not p.exists():
            return {"runs": 0, "worked": 0, "failed": 0, "last": ""}
        return yaml.safe_load(p.read_text()).get("stats") or {}

    def record(self, routine: Routine, result: RunResult) -> None:
        s = self.stats(routine.name)
        s["runs"] = s.get("runs", 0) + 1
        key = "worked" if result.ok else "failed"
        s[key] = s.get(key, 0) + 1
        s["last"] = result.said[:300]
        self._write(routine, s)

    def _write(self, routine: Routine, stats: dict) -> None:
        self.path(routine.name).write_text(
            yaml.safe_dump({**routine.source, "stats": stats}, sort_keys=False, allow_unicode=True))

    def summary(self) -> str:
        """One line per routine, for the brain's prompt."""
        lines = []
        for name in self.names():
            r, s = self.load(name), self.stats(name)
            lines.append(f"- {name}: {r.about} (ran {s.get('runs', 0)}x, worked "
                         f"{s.get('worked', 0)}, failed {s.get('failed', 0)})")
        return "\n".join(lines) or "(no routines saved yet)"
