"""Where things are on the fixed-mode client, in pixels from the top-left of the game canvas.

Fixed mode is always 765x503, so every part of the interface sits at a known offset. The
values marked "measured" were measured on the real client by skillbot
(devbasilmartin/RuneScape, skillbot/layout.py); the others are still best guesses.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CANVAS_W, CANVAS_H = 765, 503
SLOTS = 28


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def crop(self, img):
        return img[self.y:self.y + self.h, self.x:self.x + self.w]

    def grow(self, n: int) -> "Rect":
        return Rect(self.x - n, self.y - n, self.w + 2 * n, self.h + 2 * n)

    def contains(self, pt) -> bool:
        return self.x <= pt[0] < self.x + self.w and self.y <= pt[1] < self.y + self.h


@dataclass(frozen=True)
class Layout:
    viewport: Rect = Rect(4, 4, 512, 334)          # the 3D view; the camera follows the player
    minimap_center: tuple[int, int] = (643, 84)
    minimap_radius: int = 70
    minimap_tile: int = 4                           # pixels per tile at the default zoom (a guess)
    compass: tuple[int, int] = (561, 20)            # clicking it turns the camera north (a guess)
    chatbox: Rect = Rect(7, 345, 499, 130)
    # inventory: 4 columns x 7 rows (measured: empty slots are flat panel)
    inv_origin: tuple[int, int] = (563, 213)
    slot_step: tuple[int, int] = (42, 36)
    slot_size: tuple[int, int] = (32, 32)
    # RuneLite Status Bars: the health bar left of the inventory, filling from the bottom
    # (measured: the bar is 18 px wide at x 524-543, y 210-459; this is its middle)
    hp_bar: Rect = Rect(529, 210, 10, 250)
    tabs: dict = field(default_factory=lambda: {
        "combat": (538, 186), "skills": (571, 186), "quest": (604, 186), "inventory": (637, 186),
        "magic": (736, 186), "logout": (637, 484)})

    # the hover text at the top left of the 3D view ("Chop down Oak tree / 2 more options")
    # and right-click menus (a header, then one row per option): not measured yet
    hover_text: Rect = Rect(4, 4, 420, 18)
    menu_header: int = 19
    menu_row: int = 15

    # logging in and out (skillbot's values, not yet confirmed on the real client)
    logout_button: tuple[int, int] = (641, 432)         # "Click here to logout" in the logout tab
    login_existing_user: tuple[int, int] = (462, 291)   # "Existing User" on the login screen
    login_play: tuple[int, int] = (383, 324)            # "Click here to play" after logging in
    login_launcher_play: tuple[int, int] = (383, 291)   # "Play" when the launcher signed in (a guess)

    @property
    def player(self) -> tuple[int, int]:
        """The camera keeps the player in the middle of the 3D view."""
        return self.viewport.center

    def slot(self, i: int) -> Rect:
        col, row = i % 4, i // 4
        return Rect(self.inv_origin[0] + col * self.slot_step[0],
                    self.inv_origin[1] + row * self.slot_step[1], *self.slot_size)

    def slot_at(self, pt) -> int | None:
        for i in range(SLOTS):
            if self.slot(i).contains(pt):
                return i
        return None
