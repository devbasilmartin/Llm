# Work queue

What Claude works on unattended, top to bottom: one item per round, built, tested on the
simulated game, committed and pushed to `bench-bakeoff`, then checked off here with a line
on what was done. The owner can reorder, add or strike items any time, here or in chat.

Rules for unattended rounds:
- Only this repo, only `bench-bakeoff`. No pull requests, no other branches.
- Never touch logins, sessions or tokens (see CLAUDE.md).
- Tests and lint pass before every push.
- Anything that needs the owner (a decision, the real PC, a real account) goes to *Waiting on
  the owner* below instead of being guessed at; then on to the next item.
- When nothing is left that can be done without the owner, stop the loop.

## Queue

- [ ] **Code review** of superbond2/ for bugs, and fix what's real.
- [ ] **Learning track 1: the wiki as text.** Fetch a few hundred OSRS Wiki pages politely
  (the existing Wiki client's rules), cleaned to plain text, into `learn/data/` (not in git).
  Done when: a script does it, tested on a few pages.
- [ ] **Learning track 2: a tiny GPT.** A character-level GPT from scratch in numpy, readable
  first: tokenizer, attention, MLP, training loop, sampling, with comments that teach. Done
  when: it trains a little on the CPU and samples fake wiki text.
- [ ] **Learning track 3: a guide.** `learn/README.md` explaining each part in plain words,
  for the owner to read on a phone.

## Waiting on the owner

- Results of the quick bake-off (`--think off`, granite4.1:3b, qwen3:4b, gemma4:12b) to pick
  the fast brain.
- Confirm gemma4:12b as the thoughtful brain.
- Discord bot set up (docs/discord.md) and `accounts.yaml`.

## Done

- **Bake-off grading**: a wiki search first now gets an answer and the next call is graded;
  walking away from the i6 scam passes. The other failures (d2, d3, j3, j4) were fair.
- **Deaths**: noticed between any two looks (also mid-routine, which they stop), told to him
  with what he lost, posted on Discord, logged, and counted in the daily summary.
- **Food stays out of the bank**: the sim's bank now works like the real one (a click opens
  it, a click on a slot banks all of that item, Esc closes it), and a `bank` action keeps his
  tools and reflex food. The bank's color is a guess until `look` is run with it open.
- **`!bakeoff` options**: `--think` (auto/on/off/low/medium/high) and `--only` with scenario
  ids, checked like models; anything else is refused with what it takes.
- **Background thinking** (see the commit after 58043a4): starts with routines that have taken
  90 s or more, 2 turns after a thoughtful one, and stands in for the every-15-turns step back;
  the next turn waits for it rather than run two models at once. A real-model sim run showed
  it firing, and showed the cost of overlap (quick turns 5 s -> 120 s). Docs: set
  `OLLAMA_MAX_LOADED_MODELS=2` on Windows.
- **Watchdog** (62bfa3d): the helper restarts a `!play` after a crash or 15 minutes without a
  heartbeat (not 10: a thoughtful turn can take 6+ minutes), 3 times an hour at most; clean
  exits are left alone. Also restored ROADMAP.md, whose to-dos and build order an earlier
  edit of mine had cut off.
