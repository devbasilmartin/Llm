# superbond2

The agent itself. So far: his **eyes** and a **simulated game** to build the rest against.
See [ROADMAP.md](../ROADMAP.md) for the plan.

## What the eyes see

From one screenshot of the fixed-mode client:

- **Highlights** in the 3D view, by name: everything RuneLite outlines in a registry color
  (Object Markers, NPC Indicators, Ground Items, Player Indicators), with how far each is
  from the player.
- **The inventory**, slot by slot: the tagged item, "untagged" for an item without an
  Inventory Tag (tools), or empty.
- **HP**, from the Status Bars health bar.
- **Busy or idle**: whether the character is animating (chopping, fighting, walking).
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
