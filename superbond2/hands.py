"""superbond2's hands: the mouse and keyboard, on the real client or the simulated one.

A Body is the world as the hands see it: grab a picture, click, press a key, let time pass.
RealBody drives the VM's mouse with pyautogui; SimBody drives the simulated game. Everything
above them works the same with either.

The kill switch: move the mouse into any corner of the screen and superbond2 stops at the
next thing he does (Stopped is raised and nothing catches it).
"""
from __future__ import annotations

import time
from typing import Protocol

import numpy as np

KEYS = {"space", "esc", "enter", "1", "2", "3", "4", "5"}   # dialogs, menus, closing things


class Stopped(Exception):
    """The owner pulled the kill switch. Never caught inside superbond2."""


class Body(Protocol):
    def grab(self) -> np.ndarray: ...
    def click(self, pt: tuple[int, int], shift: bool = False) -> None: ...
    def key(self, k: str) -> None: ...
    def wait(self, seconds: float) -> None: ...


class SimBody:
    """The simulated game: clicks and keys go straight in, waiting lets its world run."""

    def __init__(self, game):
        self.game = game

    def read_hover(self, pt):
        return self.game.hover(pt)

    def open_menu(self, pt, shift: bool = False):
        return self.game.open_menu(pt, shift)

    def close_menu(self) -> None:
        self.game.menu_open = None

    def grab(self) -> np.ndarray:
        return self.game.grab()

    def click(self, pt, shift: bool = False) -> None:
        self.game.click(pt, shift=shift)

    def key(self, k: str) -> None:
        self.game.key(k)

    def wait(self, seconds: float) -> None:
        self.game.advance(seconds)

    def type_login(self, text: str) -> None:
        self.game.type_text(text)

    def press_login(self, key: str) -> None:
        self.game.key(key)


class RealBody:
    """The real client in the VM. Points are in canvas coordinates; `screen` (a Screen from
    screen.py) knows where the canvas is on the desktop."""

    def __init__(self, screen, gui=None, move_seconds: float = 0.15, corner: int = 4):
        if gui is None:
            import pyautogui as gui         # only needed on a real desktop
        self.screen, self.gui = screen, gui
        self.move_seconds = move_seconds
        self.corner = corner
        gui.FAILSAFE = True                 # pyautogui's own corner check, as a second net
        gui.PAUSE = 0.05
        from .text import Reader
        self.reader = Reader()

    def check_kill_switch(self) -> None:
        x, y = self.gui.position()
        w, h = self.gui.size()
        near_x = x <= self.corner or x >= w - 1 - self.corner
        near_y = y <= self.corner or y >= h - 1 - self.corner
        if near_x and near_y:
            raise Stopped("the mouse is in a screen corner")

    def grab(self) -> np.ndarray:
        self.check_kill_switch()
        return self.screen.grab()

    def click(self, pt, shift: bool = False) -> None:
        self.check_kill_switch()
        x, y = self.screen.to_screen(pt)
        try:
            self.gui.moveTo(x, y, duration=self.move_seconds)
            if shift:
                self.gui.keyDown("shift")
            try:
                self.gui.click()
            finally:
                if shift:
                    self.gui.keyUp("shift")
        except self.gui.FailSafeException as e:
            raise Stopped("the mouse is in a screen corner") from e

    def read_hover(self, pt):
        """Move the mouse to `pt` and read what the game says is there (a Hover, or None)."""
        self.check_kill_switch()
        x, y = self.screen.to_screen(pt)
        self.gui.moveTo(x, y)                    # straight there: a survey hovers ~270 points
        time.sleep(0.08)                         # the hover text follows a frame later
        return self.reader.hover(self.screen.grab())

    def open_menu(self, pt, shift: bool = False):
        """Right-click `pt` (with shift held for RuneLite's extra options) and read the menu:
        [(row text, where to click it)]."""
        self.check_kill_switch()
        x, y = self.screen.to_screen(pt)
        self.gui.moveTo(x, y, duration=self.move_seconds)
        if shift:
            self.gui.keyDown("shift")
        try:
            self.gui.click(button="right")
        finally:
            if shift:
                self.gui.keyUp("shift")
        time.sleep(0.3)
        return self.reader.menu(self.screen.grab(), pt)

    def close_menu(self) -> None:
        """Moving away from a menu closes it."""
        x, y = self.gui.position()
        self.gui.moveTo(x, max(0, y - 60), duration=self.move_seconds)

    def key(self, k: str) -> None:
        if k not in KEYS:
            raise ValueError(f"superbond2 doesn't press {k!r}")
        self.check_kill_switch()
        self.gui.press(k)

    def type_login(self, text: str) -> None:
        """Type into the login screen. Only characters.py calls this: it's not an action, so
        the brain can't type (no chat), and what's typed is never logged."""
        self.check_kill_switch()
        self.gui.write(text, interval=0.03)

    def press_login(self, key: str) -> None:
        """tab, enter or backspace on the login screen (characters.py only)."""
        if key not in ("tab", "enter", "backspace", "esc"):
            raise ValueError(f"not a login key: {key!r}")
        self.check_kill_switch()
        self.gui.press(key)

    def wait(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while True:                        # check the kill switch while waiting, too
            self.check_kill_switch()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(left, 0.25))
