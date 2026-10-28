# superbond2 on Discord

He posts to one channel on your own private server:
- 👋 when he starts
- new goals and why
- ❓ his questions
- 🎉 firsts
- 📓 journal entries
- switching accounts
- 💀 deaths, and what he lost
- 🎉 level-ups
- 🏆 quests finished
- ⚠️ problems
- why he stopped
- 📅 a daily summary

You reply there from your phone:

| You say | He does |
|---|---|
| `stop` | stops playing |
| `pause` / `resume` | waits / carries on |
| `veto`, or `veto too risky`, or tap 👎 under his goal post | drops his current goal (with your reason) and picks another |
| `help` | lists these |
| tap 👍 or 👎 under his question | answers it yes or no |
| anything else | reaches him next turn as advice from you, or as the answer if he asked something |

Messages starting with `!` go to the helper instead, which runs jobs on the VM like
`!status` and `!bakeoff` ([remote.md](remote.md)).

He only listens to your own Discord account. Other people in the channel are ignored, even
if they claim to be you.

## Setting it up (about 10 minutes, most of it on your phone)

**1. A private server and channel** (Discord app)
- Tap **+** → *Create My Own* → *For me and my friends*. Call it anything.
- Add a text channel called `superbond2`.

**2. The bot** ([discord.com/developers/applications](https://discord.com/developers/applications), works in a phone browser)
- *New Application* → name it `superbond2`.
- **Bot** tab:
  - Turn **Message Content Intent** on, so he can read your replies.
  - Turn *Public Bot* off.
  - *Reset Token* → copy the token. It's a password for the bot. Keep it in a password
    manager or a note only you can see until you're at the VM. **Never paste it in a
    chat**, including with Claude.
- **OAuth2** tab → *URL Generator*:
  - Scope: `bot`.
  - Permissions: *View Channels*, *Send Messages*, *Read Message History*, *Add Reactions*.
  - Open the URL it makes and add the bot to your server.

**3. The two IDs** (Discord app)
- *Settings* → *Advanced* → **Developer Mode** on.
- Long-press the `superbond2` channel → *Copy Channel ID*.
- Long-press your own name → *Copy User ID*.

These IDs aren't secret.

**4. On the VM**, in a terminal:

```sh
mkdir -p ~/.config/superbond2 && chmod 700 ~/.config/superbond2
nano ~/.config/superbond2/discord.env
```

Type these three lines, then save and exit (Ctrl+O, Enter, Ctrl+X):

```
DISCORD_TOKEN=the bot's token
DISCORD_CHANNEL_ID=the channel's ID
DISCORD_OWNER_ID=your user ID
```

Then:

```sh
chmod 600 ~/.config/superbond2/discord.env
cd ~/superbond2 && . .venv/bin/activate && pip install -r requirements.txt
python -m superbond2 discord-test
```

The test posts a message. Reply to it within a minute. "Heard you" means it works both
ways. After that, `play` uses Discord on its own (`--no-discord` turns it off).

## If something's wrong

- **"the token is wrong"**: reset the token in the Developer Portal and put the new one in
  `discord.env`.
- **"can't see or post in that channel"**: the bot isn't in the server, or lacks the three
  permissions. Redo the URL Generator step. (The 👍 / 👎 under his posts need *Add Reactions*.)
- **The test posts but never hears you**: Message Content Intent is off, or
  `DISCORD_OWNER_ID` isn't your user ID.
- **"can be read by other users"**: run `chmod 600 ~/.config/superbond2/discord.env`.

If Discord is down while he plays, he carries on and posts again when it's back.

💀 Deaths and 🎉 level-ups are posted, and both are in the daily summary.
