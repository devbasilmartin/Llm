# Roadmap

**superbond2** is a local LLM that plays Old School RuneScape on a private server that
allows bots: it learns the game as it goes, sets its own goals and makes its own mistakes.
Next to it runs a learning track: building small language models from scratch.

These are the decisions agreed so far (Oct 2026), each with why. The build order is at the
bottom.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | **Machine split.** RuneLite and superbond2's eyes and hands run in the existing Ubuntu VM (Xorg, 4 GB, 2 cores). The brain runs on the Windows host in Ollama, reached from the VM at `10.0.2.2:11434`. CPU only, about 14 GB of the PC's 24 GB left for the model. | The bot's mouse stays inside the VM, so the PC stays usable. A CPU model needs every core and all the memory it can get. |
| 2 | **Code lives in this repo.** superbond2 has his own perception and actions; skillbot ([devbasilmartin/RuneScape](https://github.com/devbasilmartin/RuneScape)) is a reference, not a dependency. | skillbot isn't proven on the real client yet, and the point is for the LLM to do things itself. |
| 3 | **Brain model: chosen by the bake-off** ([bench/](bench/)). Candidates: `gemma4:12b`, `granite4.1:8b`, `gpt-oss:20b` (if it fits), `qwen3:8b` as a comparison. Not considered: abliterated/"uncensored" builds, DeepSeek models (weak against agent hijacking in NIST's evaluation), unvetted uploads, base models, tiny or outdated models. | Measured on his own decisions and on this CPU, not taken from benchmarks. |
| 4 | **Hard limits in code are few.** The kill switch (mouse in a screen corner); credentials never enter his prompt; survival reflexes (eat, flee) run in code instantly, with thresholds he chooses; and the server's own rules for bots (it allows bots everywhere, PvP, the Wilderness and the GE included). **Everything else is his choice**: the Wilderness, PvP, the GE, dropping things, spending. | He should experience the game, mistakes included. The reflexes are about speed, not permission: a 20-second decision is too slow to eat in time. |
| 4b | **Public chat is off** for now. When it opens: a filter on slurs and harassment in what he says, and he doesn't claim to be human when someone sincerely asks. | Prompt injection from players, with trading and the GE open, is the main way he could be steered by someone else. Reopen after the bake-off's injection results. |
| 4c | **Other people's text** (the wiki, later chat) always goes into his prompt labeled as untrusted information, never instructions. | The bake-off's *inject* scenarios test exactly this. |
| 5 | **Control: game-level actions plus his own routines.** Actions like "click the nearest highlighted oak", "click inventory slot", "open bank", "press space". Routines are short action lists he writes and saves ("chop until full, then bank"), with conditions read from the screen (inventory full, highlight visible, HP below, idle). He doesn't write code. | He learns by building his own skill library, and routines run without a slow decision per click. Code written by a small model that drives a real mouse is where things go badly wrong. |
| 5b | **He learns through notes, not training.** A notebook (facts and lessons: "lost my rune armour at the Skeleton Mine"), his routine library, a goal list, and a journal you can read. | The model's weights don't change while he plays; what's written down and fed back in is what he has learned. |
| 6 | **Goals: he sets his own**, posts each one to Discord with his reason, and keeps going unless you veto. Milestones you've offered, in his notebook once: Vampire Slayer, Stronghold of Security, Obor, **Dragon Slayer, which earns him membership**, and long term the fire cape. | Told once and then his to pursue, so the offer doesn't push him into cutting corners. |
| 6b | **Accounts:** he shares about 3 accounts with skillbot. Only one of the two plays at a time (a shared lock). He plays one account at a time and switches between them himself, like a real player: one memory, a goal per account. | His losses are those accounts' losses; that's accepted. |
| 7 | **First milestone (v0):** on the real client, he picks a skill goal, posts it, works toward it for an hour with his own actions, saves at least one routine he made, and keeps a journal. Built and tested against a simulated game first. | The smallest thing that shows the whole loop working. |
| 8 | **Learning track in parallel, in small doses.** A character-level GPT written from scratch, trained on the **OSRS wiki** instead of Shakespeare (CC BY-NC-SA, fetched politely through its API). Reddit is out because of its terms on training models. Later maybe BPE, a bigger model, a C version. | It never blocks superbond2. A model that writes fake wiki entries is more fun to judge than fake Shakespeare. |
| 9 | **What success means, in order:** (1) a companion you check on from your phone, (2) beating Dragon Slayer, (3) learning how LLMs work. | Dragon Slayer takes hundreds of hours of play, which only happens if he runs unattended and reports in. Dragon Slayer then decides which abilities come next. Learning comes from small doses of the GPT track and from explanations of each part as it's built. |
| 10 | **About 1-2 hours a week at the PC, CPU only, no hardware spending.** | He has to need you rarely: things that need the PC are batched into one short checklist, and everything is tested on the simulated game first. Speed comes from routines (the model decides only at real choice points), not hardware. |
| 11 | **Discord, two-way, through a bot.** He posts highlights (goals, questions, firsts, level-ups, deaths, journal entries, problems he can't fix) and a daily summary. You can answer, veto a goal, pause or stop him, and message him anytime: your messages reach him as advice, and his goals stay his choice. | It's how you look after him away from the PC. Only your own Discord account in a private channel is listened to, so other people can't steer him. The bot token lives in a private file on the VM, like the logins. |

## Owner to-dos

- [ ] Set up Discord: a private server and channel, the bot, and `discord.env` on the VM ([docs/discord.md](docs/discord.md)); the token never goes in a chat.
- [ ] Start the Discord helper with the VM's desktop (`python -m superbond2 helper --autostart`), and Claude Remote Control on Windows ([docs/remote.md](docs/remote.md)).
- [ ] Send the quick bake-off results (`--think off`, granite4.1:3b, qwen3:4b, gemma4:12b) to pick the fast brain.
- [ ] Confirm gemma4:12b as the thoughtful brain.
- [ ] Save each Bolt character's session (`python -m superbond2 save-session NAME`) and write a line about each in `data/memory/accounts.yaml`.
- [ ] Try the eyes and hands on the VM ([superbond2/README.md](superbond2/README.md)) and send the output and look.png.
- [x] Check the server's rules on bots: allowed everywhere, PvP and the GE included.
- [x] Install Ollama on Windows and pull the bake-off models.
- [x] Run the bake-off at home: gemma4:12b 13/21 (best, and safest on injections, but about 2.5 minutes an answer), gpt-oss:20b 9/21, granite4.1:8b 3/21 (both did what injected messages told them).

## Build order

### Phase 0: pick the brain
- [x] Bake-off: 21 scenarios (decide, judgment, plan, inject), graded and timed through Ollama
- [x] Run it on the PC: gemma4:12b leads (see the owner to-dos)
- [ ] The quick bake-off for the fast brain, and the pair chosen

### Phase 1: superbond2 v0
- [x] Eyes: find the canvas on the desktop, highlights by name, inventory tags, HP, busy/idle, in game or not ([superbond2/](superbond2/))
- [ ] Eyes, checked on the real client (`python -m superbond2 look`): boxes, HP, busy while chopping
- [x] Hands: mouse and keyboard in the VM (pyautogui) or the simulated game; kill switch (mouse in a corner); keys limited to space, esc, enter, 1-5
- [x] Actions: click the nearest highlight, click an item or slot, drop all, press, wait, wait until idle; each reports what changed
- [ ] Hands, checked on the real client (`python -m superbond2 do ...`)
- [x] Routines: YAML with repeat/if/stop and screen conditions, checked with messages that say what to fix, run with limits, saved in a library that keeps score
- [ ] Banking on the real client: the eyes read the bank screen, actions deposit and withdraw
- [x] Brain loop: state → model → one tool call, with the notebook, goals, journal, decision log and his routines; limits on goal churn, repeated questions and repeating what does nothing
- [x] Survival reflexes: eat below his threshold, in code, before every turn and after every routine action
- [x] Flee reflex: with no food and HP below his flee threshold, run from the fight; still dropping, log out and rest 2 minutes
- [x] Two brains: a small fast model for everyday turns, the big one when it needs thought (no goal, stuck, asked, the owner spoke, every 15 turns) and in the background while routines play; first real run in [superbond2/README.md](superbond2/README.md)
- [ ] More reflexes once the eyes can see them: the Wilderness level, a skulled player nearby
- [x] First runs with real models on the simulated game (granite4.1 3b and 8b): see [superbond2/README.md](superbond2/README.md#first-runs-simulated-game-a-4-core-cloud-cpu)
- [x] Routines he can write: a simple form (one-line steps, until, after, rounds) instead of nested YAML, and a ready `save_routine` handed to him when he does the same thing by hand three times
- [x] Routines he writes on his own: granite4.1:8b wrote one unprompted on turn 6 and ran it 7 times without a failure
- [x] His personality: who he is, firsts celebrated, journal reminders
- [x] Characters: log into skillbot's profiles by name (credentials typed by code, never seen by him), logged back in after a disconnect; won't start while skillbot runs
- [x] Launcher characters: `save-session` keeps the session Bolt gives RuneLite (private file outside the repo); logging in restarts RuneLite with it and clicks Play
- [x] One player, several accounts: he switches himself (`switch_character`, 20 turns minimum per account); shared notebook, routines and journal, a goal per account, the owner's line about each account in accounts.yaml
- [ ] The login screen positions, confirmed on the real client
- [x] Exploring: survey (hover text over the whole view), mark (Object Markers, in `marked`), inspect (what a highlight really is); RuneLite guide in docs/runelite.md
- [ ] Hover text and menu reading, tuned on the real client (`python -m superbond2 hover`)
- [ ] New routines only run unattended once proven (experimental while you watch)
- [x] A simulated game, drawn like RuneLite draws the real one: gathering, combat and loot, bank, food, dropping, dying
- [ ] More eyes as needed: chat and NPC dialog, levels, minimap, open interfaces
- [ ] On the real client: one hour of a skill he picked (the v0 milestone)

### Phase 1.5: a companion you check on
- [x] Discord bot ([docs/discord.md](docs/discord.md)): highlights and a daily summary out; answers, vetoes, pause/resume/stop and advice in, from your account only; `discord-test` checks the setup
- [x] Daily summary: turns, accounts, turn time, routine success, firsts, new goals, a journal line
- [x] The Discord helper: `!status`, `!models`, `!pull`, `!bakeoff` (report attached), `!update`, `!tests`, `!play`, `!log`, `!kill`; owner only, fixed jobs, starts with the VM's desktop ([docs/remote.md](docs/remote.md))
- [x] Watchdog: the helper restarts a `!play` after a crash or 15 minutes without a heartbeat (3 times an hour at most), and says so on Discord
- [x] Deaths: noticed from two looks (low HP, then full HP and most items gone), told to him, posted on Discord, counted in the daily summary
- [ ] Level-ups on Discord, and XP in the daily summary (needs eyes for them)
- [ ] Claude Remote Control on Windows, reaching the VM over SSH ([docs/remote.md](docs/remote.md))
- [ ] A full evening unattended, followed only through Discord

### Phase 2 and later
- [x] The OSRS Wiki as tools: search, and read a page or section as plain text (polite: User-Agent, 1 request/s, a week's cache); the page stays in view for 6 turns, labeled as other people's writing
- [ ] Travel, NPC dialogs and quests (Vampire Slayer first)
- [ ] The Grand Exchange
- [ ] Chat, after the injection results
- [ ] Combat and the Wilderness on his own terms; Obor; Dragon Slayer

### Learning track (whenever)
- [ ] Fetch the OSRS wiki politely and clean it into plain text
- [ ] A readable character-level GPT: tokenizer, attention, MLP, training loop, sampling
- [ ] Train it on the CPU; read its fake wiki pages

The unattended work queue is [WORKQUEUE.md](WORKQUEUE.md).
