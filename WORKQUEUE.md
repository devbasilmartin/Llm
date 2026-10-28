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

- [ ] **Background thinking that actually runs.** In the first two-brain run it never fired
  (slow turns kept landing too close to routine starts). Rethink when it starts, so a long
  routine gets the big model thinking. Done when: a sim run with real models shows it, and
  tests cover it.
- [ ] **`!bakeoff` options.** `!bakeoff --think off --only d1 d3 ...`, checked like the other
  arguments. Done when: tested.
- [ ] **Keep food out of the bank.** Banking deposits everything that isn't a tool, so he
  banks his trout and the eat reflex has nothing. Banking keeps his reflex food (or the
  routine can say what to keep). Done when: the sim and tests show food staying.
- [ ] **Deaths.** Notice a death (HP back to full, inventory gone, in the sim: `game.deaths`),
  tell him, post it on Discord, count it in the daily summary. Done when: tested.
- [ ] **Bake-off grading, second look.** Check each scenario's accepted answers against the
  failures in the owner's report (wiki-first answers, "drop method" wording). Change only
  what's clearly unfair, and note each change in bench/README.md.
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

- **Watchdog** (62bfa3d): the helper restarts a `!play` after a crash or 15 minutes without a
  heartbeat (not 10: a thoughtful turn can take 6+ minutes), 3 times an hour at most; clean
  exits are left alone. Also restored ROADMAP.md, whose to-dos and build order an earlier
  edit of mine had cut off.
