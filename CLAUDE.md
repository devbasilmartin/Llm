# superbond2

A local LLM that plays Old School RuneScape on a private server that allows bots, from what
it sees on screen. See README.md, ROADMAP.md (decisions and build order) and docs/.

## Where things run
- **Windows host:** Ollama (CPU only), at http://localhost:11434 here and
  http://10.0.2.2:11434 from the VM.
- **Ubuntu VM** (VirtualBox): RuneLite, superbond2 and its Discord helper, in `~/superbond2`
  with a venv at `.venv`. From Windows: `ssh vm` (see docs/remote.md).
- Commands that need the screen (`play`, `look`, `calibrate`, `do`) need the VM's desktop:
  start them with the Discord helper (`!play`), or over SSH with `DISPLAY=:0`.

## Never
- Print, read out, copy or commit logins, sessions or tokens: `~/.config/skillbot/`,
  `~/.config/superbond2/` (sessions, discord.env). If something needs one, say which file
  the owner should edit, and let them do it.
- Put screenshots in git (they show account names; `*.png` is ignored).
- Push to any branch other than `bench-bakeoff` without the owner asking.

## Checks
- Tests: `python -m pytest -q`, in the VM (some tests need Linux): `ssh vm 'cd ~/superbond2 &&
  .venv/bin/python -m pytest -q'`, or `!tests` on Discord. Try new behavior on the simulated game first (`--sim`).
- Lint: `ruff check --select F,E9 .`
