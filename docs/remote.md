# Looking after superbond2 from your phone

Two tools, each covering the other's gaps:

- **The Discord helper (on the VM).** Fixed jobs you type in the superbond2 channel:
  `!status`, `!models`, `!pull`, `!bakeoff`, `!update`, `!tests`, `!play`, `!log`, `!kill`.
  It's quick and safe because it can only do what's on that list.
- **Claude Remote Control (on Windows).** A Claude session on your PC that you drive from the
  Claude app, for everything off that list: reading errors, fixing things, trying new code.
  It reaches the VM over SSH, so nothing extra is installed in the VM except an SSH server.

For seeing the screen (watching him play, clicking in Bolt or RuneLite), add **Chrome
Remote Desktop** on Windows and your phone.

## Before either: keep the PC awake

- Windows: Settings → System → Power → when plugged in, **Sleep: Never**.
- Leave the VM running, logged in to its desktop. superbond2 needs a screen to see.
- Ollama on Windows: set the user environment variable `OLLAMA_HOST=0.0.0.0` (Start → "Edit
  environment variables for your account"), then quit Ollama from the tray and start it again.

## The Discord helper (about 5 minutes, after [discord.md](discord.md))

In the VM terminal:

```sh
cd ~/superbond2 && . .venv/bin/activate
git pull && pip install -r requirements.txt
python -m superbond2 helper --autostart     # start it with the desktop from now on
python -m superbond2 helper                 # and start it now
```

Then type `!help` in the channel. If you close that terminal, the helper stops until the VM
restarts or you start it again.

| Type | It does |
|---|---|
| `!status` | is he playing, what's running, Ollama, which code, disk space |
| `!models` / `!pull gemma4:12b` | what Ollama has / download a model, with progress |
| `!bakeoff` or `!bakeoff gemma4:12b granite4.1:8b` | runs the bake-off, posts progress, and attaches the report at the end (send that to Claude) |
| `!update` | gets the newest code; restarts itself if its own code changed |
| `!tests` | runs the tests |
| `!play gemma4:12b main 90` | lets him play (model, character, minutes); `!play gemma4:12b+granite4.1:3b main 90` adds a fast model for everyday turns. The helper restarts him if he crashes, or hangs for 15 minutes (3 times an hour at most); a clean finish, `stop`, the kill switch and `!kill` aren't restarted |
| `!log` / `!log 40` | the last lines of his play log |
| `!kill` | stops what the helper started, right away (`stop` without the `!` is the gentle way) |

## Claude Remote Control on Windows (about 20 minutes)

**1. Install** (PowerShell):

```powershell
winget install Git.Git
irm https://claude.ai/install.ps1 | iex
```

Close PowerShell and open it again, so it finds the new commands.

**2. A folder for it: a copy of the repo**, so Claude has the project and its rules
([CLAUDE.md](../CLAUDE.md)):

```powershell
git clone -b bench-bakeoff https://github.com/devbasilmartin/Llm $HOME\superbond2
cd $HOME\superbond2
claude
```

Sign in when it asks, then type `/exit`.

**3. SSH into the VM**, so Claude on Windows can work there:

- In the VM: `sudo apt install openssh-server`.
- In VirtualBox: the VM's **Settings → Network → Adapter 1 → Advanced → Port Forwarding** → **+**:
  - Name `ssh`, Protocol `TCP`
  - Host IP `127.0.0.1`, Host Port `2222`
  - Guest Port `22`
- In PowerShell, make a key and give it to the VM. Swap in your VM username for `you`; it
  asks for your VM password once:

  ```powershell
  ssh-keygen -t ed25519            # press Enter at every question
  type $HOME\.ssh\id_ed25519.pub | ssh -p 2222 you@127.0.0.1 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
  ```

- Give it a short name. Open `notepad $HOME\.ssh\config` and add:

  ```
  Host vm
      HostName 127.0.0.1
      Port 2222
      User you
  ```

- Check it: `ssh vm hostname` prints the VM's name without asking for a password.

**4. Start Remote Control**, and leave the window open:

```powershell
cd $HOME\superbond2
claude remote-control
```

On your phone: Claude app → **Code** → your PC's session.

**Keep it careful.** It runs on your real Windows PC, so leave it asking before each
command, and approve from your phone. Don't switch on any "don't ask" mode.

## Who does what

| You want to | Use |
|---|---|
| check on things, download a model, run the bake-off, update, start or stop him | the helper |
| figure out an error, fix something, try something new | Claude Remote Control |
| see the screen, click in Bolt or RuneLite | Chrome Remote Desktop |
| talk to superbond2 himself | the channel, without `!` |
