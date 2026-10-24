# RuneLite for superbond2

superbond2 sees the game through what RuneLite draws, so the plugins decide what he can
notice. He plays in skillbot's **bot** profile (same colors, `superbond2/colors.yaml`), plus a
few settings of his own.

## Needed

| Plugin | Setting | Why |
|---|---|---|
| **Object Markers** | **Marker color: `#80F8D0`** (registry name `marked`) | Everything he marks himself shows in this color. The owner's marks keep their named colors after skillbot's recolor. |
| Inventory Tags | from skillbot's generated profile | He reads his inventory by tag color; untagged items read as "untagged". |
| NPC Indicators | from skillbot's generated profile | Monsters, cows, fishing spots, random events. |
| Ground Items | from skillbot's generated profile (highlight tiles on) | Loot shows as `loot`. |
| Player Indicators | others in `other_player` | Crowding. |
| Status Bars | on, HP left of the inventory | His HP, and the eat reflex. |
| Key Remapping | on | Space for dialogs without typing into chat. |

Also: fixed mode, camera zoomed all the way out, **shift-click drop** on.

`marked` also has to go into skillbot's `colors.yaml`, so skillbot never hands that color
to something else: add the line from the bottom of `superbond2/colors.yaml`.

## Worth adding

| Plugin | What it gives him |
|---|---|
| **Quest Helper** (Plugin Hub) | Outlines the next NPC, object or item of a quest in `quest_target`, which he can already see. The way into Vampyre Slayer and the rest. Set its colors to skillbot's `quest_target` / `quest_dialog` / `quest_item`. |
| **Shortest Path** (Plugin Hub) | Draws a route to a destination (skillbot's `path` color). For travelling once he can set targets. |
| Menu Entry Swapper | Makes the useful option the left-click one (bank booths to "Bank", etc.), so fewer menus. Turn on only swaps you understand: they change what his clicks do. |

## Careful with

- **Plugins that draw their own colors** (the Fishing, Woodcutting, Mining and Agility
  plugins' overlays, Tile Indicators, Interact Highlight): a color close to a registry color
  makes him see things that aren't there. skillbot's profile already turns the Agility boxes
  off. If you add one, check with `python -m superbond2 look` that nothing new shows up.
- **NPC Indicators with `*`** (every NPC): it would let him see every NPC, but in the bot
  profile its color is `enemy`, which skillbot attacks. Only in a separate profile with its
  own color.
- **Mouse Tooltips**: draws the hover text by the cursor too; when the mouse is near the top
  left it can cover the text he reads.

## Text he reads

`survey`, `inspect` and `mark` read the game's hover text and right-click menus with
Tesseract: `sudo apt install tesseract-ocr` in the VM (pytesseract comes with
`pip install -r requirements.txt`). To check it: hover over a tree and run
`python -m superbond2 hover`; it prints what it read and saves `hover-raw.png` and
`hover.png`. Send those if it reads wrong.
