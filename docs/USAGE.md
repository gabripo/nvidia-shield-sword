# Daily use

## Shield.app

Open it with Spotlight (Cmd+Space, "Shield") or from the Dock. Pick an action and click **Open**:
it runs in a new Terminal window.

| Choice | What it does |
|---|---|
| **Claude Code session (Telegram bot)** | Attaches to Claude on the Shield (starts it if needed). Leave with **Ctrl+b**, **d** |
| **Debian shell** | Root shell in Debian |
| **Termux shell** | Shell in Termux |
| **Status** | Whether Termux/SSH, Debian and Claude are running |
| **Start Claude** | Starts the Claude session if it isn't running |
| **Stop Claude** | Stops it, after a confirmation (the bot goes offline) |

The first launch asks to let Shield control Terminal: click **OK** (System Settings → Privacy &
Security → Automation if you denied it).

## The `shield` command

```bash
shield              # = shield claude: attach to Claude (start it if needed)
shield debian       # Debian shell
shield termux       # Termux shell
shield status
shield start | stop
SHIELD_HOST=10.0.0.5 shield status   # override the configured IP for one call
```

If SSH doesn't answer, `shield` wakes the TV and opens Termux through adb, waits up to two
minutes for SSH, then continues.

## Inside the Claude session

| Action | Effect |
|---|---|
| **Ctrl+b**, then **d** | Detach: your window closes, Claude keeps running, bot online |
| `/exit` | Claude exits and is restarted after 15 s (bot stays online) |
| `shield stop` | Really stops it |

## After a reboot of the Shield

Nothing starts until Termux runs. Either open **Termux** with the TV remote, or just use
`shield` / Shield.app from the Mac, which opens Termux through adb. Opening Termux runs
`~/.termux/boot/start-claude.sh`: wake lock, `sshd`, Debian, and the `claude` tmux session.

## Checking what runs

```bash
shield status
adb shell ps -A -o PID,ETIME,NAME | grep -E "proot|tmux|claude"    # works without SSH
```

On the Shield, `~/.termux/boot/start-claude.log` records every start.

## Files on the Shield

| Where | What |
|---|---|
| Termux `~/.termux/boot/start-claude.sh` | Starts sshd, Debian and Claude |
| Termux `~/.bashrc` | Autostart hook (between `nvidia-shield-sword autostart` markers) |
| Debian `/root/trips/` | Claude's workspace: `CLAUDE.md`, `.claude/settings.json`, your trip plans |
| Debian `/root/.claude/` | Claude sign-in, plugins, Telegram token and allowlist |

## Updating

```bash
shield debian
npm install -g @anthropic-ai/claude-code      # Claude Code
claude plugin update telegram@claude-plugins-official
apt update && apt upgrade                     # Debian
```

In Termux (`shield termux`): `pkg upgrade`. If that upgrades `openssh`, the running `sshd`
starts refusing new connections: restart it from the Termux app on the TV with
`pkill sshd; sshd`.
