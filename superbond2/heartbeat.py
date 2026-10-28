"""A heartbeat: a file superbond2 touches whenever he looks at the screen (and while
paused), so the helper's watchdog can tell a slow turn from a hung one."""
from __future__ import annotations

import os
from pathlib import Path

FILE: Path | None = None            # set by `play`; nothing happens until it is


def beat() -> None:
    if FILE is None:
        return
    try:
        FILE.touch()
    except OSError:
        pass


def age(path: Path, now: float) -> float | None:
    """Seconds since the last beat, or None if there's never been one."""
    try:
        return now - os.stat(path).st_mtime
    except OSError:
        return None
