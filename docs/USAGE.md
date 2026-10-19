# Daily use

## Shield.app

Open it with Spotlight (Cmd+Space, "Shield") or from the Dock. Pick an action and click **Open**:
it runs in a new Terminal window.

| Choice | What it does |
|---|---|
| **Claude Code session** | Interactive Claude in `~/workspace` (opened if needed). Leave it running with **Ctrl+b**, **d** |
| **Debian shell** | Root shell in Debian |
| **Termux shell** | Shell in Termux |
| **Status** | sshd, Telegram bot, interactive Claude session, last start |
| **Start services (sshd + Telegram bot)** | Starts sshd and the bot (wakes Termux through adb if needed) |
| **Close Claude session** | Closes the interactive Claude session, after a confirmation (the bot keeps running) |

The first launch asks to let Shield control Terminal: click **OK** (System Settings → Privacy &
Security → Automation if you denied it).

## The `shield` command

```bash
shield              # = shield claude: interactive Claude in ~/workspace (opened if needed)
shield debian       # Debian shell
shield termux       # Termux shell
shield status       # sshd, bot, Claude session
shield start        # start sshd + the Telegram bot
shield stop         # close the interactive Claude session (bot keeps running)
shield bot-setup    # configure the Telegram bot (docs/TELEGRAM.md)
SHIELD_HOST=10.0.0.5 shield status   # override the configured IP for one call
```

If SSH doesn't answer, `shield` wakes the TV and opens Termux through adb, waits up to two
minutes for SSH, then continues.

## The interactive Claude session

The Telegram bot doesn't need it: it's for working with Claude at a terminal. It runs in the
same `~/workspace` (same rules and custom commands) but is a separate conversation.

| Action | Effect |
|---|---|
| **Ctrl+b**, then **d** | Detach: your window closes, the session keeps running |
| `/exit` | Closes the session |

## After a reboot of the Shield

Nothing starts until Termux runs. Either open **Termux** with the TV remote, or just use
`shield` / Shield.app from the Mac, which opens Termux through adb. Opening Termux runs
`~/.termux/boot/start-shield.sh`: wake lock, `sshd` and the Telegram bot.

## Checking what runs

```bash
shield status
adb shell ps -A -o PID,ETIME,ARGS | grep -E "shield-bot|sshd"    # works without SSH
```

On the Shield, `~/.termux/boot/start-shield.log` records every start, `shield-bot.log` every
message and `shield-bot.err` the bot's errors.

## Files on the Shield

| Where | What |
|---|---|
| Termux `~/.termux/boot/shield-bot.py` | The Telegram bot |
| Termux `~/.termux/boot/start-shield.sh` | Starts sshd and keeps the bot running |
| Termux `~/.termux/boot/start-claude.sh` | Opens the interactive Claude session (`shield claude`) |
| Termux `~/.config/shield-bot/config.json` | Bot token, allowed user IDs, options (mode 600) |
| Termux `~/.bashrc` | Autostart hook (between `nvidia-shield-sword autostart` markers) |
| Debian `/root/workspace/` | Claude's workspace: `CLAUDE.md`, `.claude/settings.json`, `commands/` (your bot commands), `tools/browse` (headless browser), `screenshots/` (kept one day) |
| Debian `/root/.claude/` | Claude sign-in and conversations |

## RAM and storage

The Shield has ~3 GB of RAM (Android and your apps use about 1.8 GB) and limited storage, so the
setup is tuned to use resources only while something happens:

| Component | Idle | While working | Tuning |
|---|---|---|---|
| shield-bot (Termux) | ~30 MB | same | - |
| Claude (warm process) | 0 (closed after 15 min) | ~250 MB | `claude_idle` in `~/.config/shield-bot/config.json` |
| Chromium (warm browser) | 0 (closed after 10 min) | ~300–500 MB | `IDLE_SECONDS` in `tools/browse.js`; `tools/browse stop` |

Storage savings built in: no docs, man pages or translations in Debian
(`/etc/dpkg/dpkg.cfg.d/01-shield-nodoc`), Claude Code as a native binary (no npm), npm only
installed temporarily during setup, and a **daily cleanup** by the bot (apt caches and package
lists, Claude transcripts older than 30 days, screenshots older than a day; logged as "daily
cleanup done, freed N MB").

Biggest remaining items: Chromium with its graphics libraries (~560 MB), Claude Code (~270 MB),
and Termux's compiler toolchain (~300 MB, required by `proot-distro`). Other Android apps running
in the background (VPNs, media servers) compete for the same RAM.

## Updating

```bash
shield debian
claude update                                 # Claude Code (also updates itself)
apt update && apt upgrade                     # Debian
```

To reinstall the browse tool's dependencies (e.g. after deleting `node_modules`):
`apt update && apt install -y npm && cd ~/workspace/tools && npm ci; apt purge -y npm && apt autoremove -y`.

In Termux (`shield termux`): `pkg upgrade`. If that upgrades `openssh`, the running `sshd`
starts refusing new connections: restart it from the Termux app on the TV with
`pkill sshd; sshd`.
