# superbond2

The agent itself. So far: his **eyes**, his **hands**, his **routines** and a **simulated
game** to build the rest against.
See [ROADMAP.md](../ROADMAP.md) for the plan.

## What the eyes see

From one screenshot of the fixed-mode client:

- **Highlights** in the 3D view, by name: everything RuneLite outlines in a registry color
  (Object Markers, NPC Indicators, Ground Items, Player Indicators), with how far each is
  from the player.
- **The inventory**, slot by slot: the tagged item, "untagged" for an item without an
  Inventory Tag (tools), or empty.
- **HP**, from the Status Bars health bar.
- **Busy or idle**: whether the character is animating (chopping, fighting, walking). Each
  look takes two pictures 0.3 s apart and compares them; comparing with an older look can
  land on the same frame of a repeating swing and call a busy character idle.
- **In game or not**: the stone frame around the 3D view is only there when you're logged in.

The colors come from `colors.yaml`, a copy of skillbot's registry, so both bots use the same
RuneLite "bot" profile. If you change a color in one, change it in the other too.

The eyes don't read yet: chat and NPC dialog, levels, the minimap, open interfaces (bank,
shops). Those come as superbond2 needs them.

## Try the eyes on the VM

1. Get the code on the VM (once):
   ```sh
   git clone https://github.com/devbasilmartin/Llm ~/superbond2
   cd ~/superbond2 && git checkout bench-bakeoff
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Open RuneLite with the **bot** profile, fixed mode, logged in, standing somewhere with a
   few highlights in view (the oaks at Draynor, the cows at Lumbridge).
3. Find the game on the screen:
   ```sh
   python -m superbond2 calibrate
   ```
   You should see *Found the game at (x, y)*. Run it again whenever the window moves.
4. Look:
   ```sh
   python -m superbond2 look
   ```
   It prints what superbond2 sees, like:
   ```
   HP: 100%
   You are: idle
   Inventory: 8/28: 4 oak logs, 3 trout, 1 untagged
   Highlighted nearby: 2 oak tree (close); 1 bank (far)
   ```
   and draws **look.png** with a green box and a name on every highlight it found.

This only reads the screen; it never touches the mouse, so it's safe while skillbot runs.

**Send me** the printed text and `look.png` (crop out the account name). Things to check:
does every highlight have a box with the right name? Is HP right? Does *busy* say yes while
you chop? (Run `look` while chopping, then while standing still.)

## His hands

`hands.py` is the mouse and keyboard: on the real client through pyautogui (inside the VM),
or on the simulated game. **The kill switch: move the mouse into any corner of the screen**
and he stops at the next thing he does.

He only presses space, esc, enter and 1-5, so he can't type in chat.

`actions.py` is what he can do with them, one game-level action at a time:

| action | does |
|---|---|
| `click_nearest name` | click the nearest highlight with that name: a tree, a cow, the bank, loot |
| `click_item item` | click the first inventory slot with that item (eat it, bury it...) |
| `click_slot slot` | click inventory slot 0-27 |
| `drop_all item` | shift-click every slot with that item |
| `press key` | space, esc, enter or 1-5 |
| `wait seconds` | do nothing for up to a minute |
| `wait_until_idle` | wait until the character stops |

Every action says what changed since he last looked, e.g. *clicked the nearest oak_tree:
you're busy now*, or *idle after 41s: +12 oak logs; 1 oak tree gone*. That report is how he
finds out whether something worked.

### Try the hands on the VM

After `calibrate` (above), with the character standing near some highlights:

```sh
python -m superbond2 do click_nearest name=oak_tree
python -m superbond2 do wait_until_idle timeout=120
python -m superbond2 do drop_all item=oak_logs
python -m superbond2 do click_nearest name=bank
```

Each prints *OK* or *NO* and what changed. **This moves the mouse**, so stop skillbot first,
and keep your hand near the mouse: a corner stops it.

Clicking the bank opens the bank screen, which the eyes can't read yet, so expect
*nothing changed* there (press esc to close it: `do press key=esc`).

## His routines

A routine is a short list of actions he writes in YAML, saves, and replays without thinking
about every click ([examples/](../examples/)):

```yaml
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
```

- **Steps:** any action (`click_nearest: oak_tree`), `repeat:` a number of times or `until:` a
  condition, `if:`/`then:`/`else:`, and `stop:`.
- **Conditions:** inventory full, inventory empty, free slots below N, idle, busy, hp below N%,
  hp above N%, see *highlight*, have *item*, in game; joined with `and`, each can start with
  `not`.
- **It stops** at the end, at a `stop:`, when an action fails (saying which step and why), when
  a reflex says so, or at its limits (300 actions and 30 minutes unless it says otherwise; a
  repeat that does nothing is caught at once).
- **Mistakes in what he writes** get a message that says what to fix, e.g. *there's no action
  or step called 'fly'. Actions: click_nearest, ...*. He reads it and tries again.
- **The library** keeps each routine with how it's gone: runs, worked, failed, and the last
  result.

### Try a routine

```sh
python -m superbond2 run examples/chop-and-drop-oaks.yaml --sim   # on the simulated game
python -m superbond2 run examples/chop-and-drop-oaks.yaml         # on the real client
```

On the real client: stand at some oaks marked with Object Markers in the `oak_tree` color,
with oak logs tagged (`oak_logs`) and shift-click drop on. It prints every step and what
changed. Mouse into a corner stops it.

Banking routines only work on the simulated game for now: on the real client, clicking the
bank opens the bank screen, which the eyes can't read yet.

## The simulated game

`sim.py` draws a small scene the way RuneLite draws the real one: oaks, a tree, a copper
rock, a cow that fights back and drops a cowhide, the bank, another player. Clicking works:
gather until full, shift-click to drop, click food to eat, click the bank to deposit, die and
lose everything. `python -m superbond2 sim` shows what the eyes make of it (sim.png).

## Tests

```sh
pip install pytest
python -m pytest tests
```
