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

Built and tested on the simulated game; screen positions and colors the real client decides
are marked unconfirmed, with a `look`/`hover` check added to *Waiting on the owner*.

- [ ] **3. Levels and XP.** Read levels (Skills tab) and XP drops; level-ups to Discord, XP per
  hour in the daily summary.
- [ ] **14. Equipment.** Wear/wield items, read the equipment tab, in the prompt.
- [ ] **13. `use X on Y`.** Item on item, item on object (cooking, firemaking), as an action
  and a routine step.
- [ ] **15. Shops.** Buy and sell in a shop window, with a price sanity check from the wiki.
- [ ] **18. Discord reactions.** 👎 on a goal post vetoes it; 👍 on a question answers yes.
- [ ] **23. Stuck detector.** The same screen for many turns: hand over to the thoughtful
  brain, then tell the owner.
- [ ] **22. Random events.** Recognise a random event NPC (its highlight or dialogue) and
  dismiss it.
- [ ] **21. Memory sleep.** Now and then the thoughtful brain boils old notes down into lessons
  so the notebook stays short.
- [ ] **11. Quest points and the quest log.** Read them, track them toward Dragon Slayer's 32.
- [ ] **10. Quest Helper.** Read its step text and follow its `quest_target` highlights.
- [ ] **16. The Grand Exchange.** Buy and sell with wiki prices and guard rails (no selling
  far under price, no buying far over).
- [ ] **17. Smarter combat.** Targets by level, loot rules, burying bones, attack styles.
- [ ] **Vampyre Slayer with real models.** `play --sim --world vampyre` with the two brains;
  write up how far they get and what trips them, and fix what's ours to fix.
- [ ] **25. A BPE tokenizer** for the tiny GPT, compared with letters (learn/).

## Waiting on the owner

- Results of the quick bake-off (`--think off`, granite4.1:3b, qwen3:4b, gemma4:12b) to pick
  the fast brain.
- Confirm gemma4:12b as the thoughtful brain.
- Discord bot set up (docs/discord.md) and `accounts.yaml`.
- Turn on a coordinates overlay (RuneLite's Developer Tools Location, in developer mode, or a
  Plugin Hub plugin showing tile coordinates) under the hover text, and run
  `python -m superbond2 where`; send what it read and `where-raw.png`. walk_to needs it.
- With an NPC talking, and again with a choice of options: `python -m superbond2 dialogue`;
  send what it read and `dialogue-raw.png` (crop out your name). Confirms dialogue colors and lines.

## Done

- **2. Where am I**: his tile read from a coordinates overlay (OCR of "3222, 3218, 0"), and a
  `Where:` line in his prompt with the nearest named place; `python -m superbond2 where` checks it.
- **12. Vampyre Slayer in the sim**: a world with places (things show near where they are),
  stairs that go somewhere, a cupboard to search, NPC scripts with needs, takes and quest points,
  and a Count who rises again without stake and hammer; played start to finish by a test. Found
  and fixed: diagonal walk clicks landed off the round minimap; untagged items are now named
  by hovering them once.
- **7. Doors, gates, stairs, ladders**: `interact <thing> <option>` through the right-click
  menu (highlights or survey names), an action and a routine step; the sim's doors block tiles
  till opened, ladders change floors, and its walking now routes around walls like the game.
- **6. `walk_to <place>`**: 17 named F2P places (places.yaml); compass north, then minimap
  clicks of up to 14 tiles, position read after each; stuck and other-floor cases reported.
  Works in the sim; on the real client it needs item 2 (the position readout).
- **9. Talking**: `talk_to` (Talk-to from the right-click menu; a highlight or the NPC's
  name, found by hovering), `continue_dialogue` (space), `choose` (number or words; number
  keys), as actions and routine steps; sim NPCs with scripts that give items and set flags.
- **1. Dialogue reading**: the eyes notice a dialogue by its dark-red title, then the reader
  gets speaker, text, options (with where to click) and the continue line; in the sim and the
  prompt. `python -m superbond2 dialogue` for the real-client check.
- **Learning track 3**: `learn/README.md`, how a GPT works in plain words, part by part,
  using the tiny one and its first run (written for a phone).
- **Learning track 2** (9509c1c): `learn/gpt.py`, a character-level GPT in numpy with the
  backward pass by hand; every gradient checked numerically. On 1,500 wiki pages (2.2 MB),
  122k numbers, 3,000 steps in 6 minutes on a 4-core cloud CPU: loss 4.9 (guessing) -> about
  1.7, writing "...players damage. It is the statack that and by anots..."
- **Learning track 1**: `python -m learn.fetch_wiki` gets articles 50 per request (polite:
  the wiki client's User-Agent, 1 request/s, a week's cache) as plain text, skipping stubs,
  lists and interface copies; tested on a fake API and on 20 real pages.
- **Code review**, four real bugs fixed: after waiting for background thinking, a turn used
  the screen from before the wait; that wait didn't beat the heartbeat (the watchdog could
  kill a healthy game); a reflex logout still asked a model what to do on the login screen;
  a helper restarted by `!update` forgot the game it was watching (now in data/watching.json).
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
