# The Telegram bot

One Telegram bot manages the Shield. A small program, `shield-bot` (Python, standard library
only), runs in Termux, reads every message from you and decides what to do with it:

| You send | What happens | Claude usage |
|---|---|---|
| a **built-in command** (`/status`, `/sh …`) | answered directly by shield-bot | none |
| one of **your commands** (`/tvinfo`, `/plug on`, …) | runs the matching script in Debian's `~/workspace/commands/` | none |
| **anything else** (plain text, unknown `/commands`) | handed to Claude Code (`claude -p` in `~/workspace`), reply sent back | yes |

Claude can **extend the bot**: ask *"create a command /ar4k that connects via SSH to the gaming
PC"* and Claude writes `commands/ar4k`, tests it and tells you; from then on `/ar4k` runs
directly, without Claude.

## 1. Create the bot

In Telegram, open **@BotFather**, send `/newbot`, choose a display name and a username ending in
`bot`. BotFather replies with a **token** (`123456789:AA…`). Keep it secret: anyone with it
controls the bot (`/revoke` in BotFather issues a new one).

Get your numeric Telegram user ID from **@userinfobot**.

## 2. Configure shield-bot

On your Mac:

```bash
shield bot-setup
```

It asks for the token (hidden input; checked with Telegram), the allowed user ID(s), and whether
to allow `/sh` and `/termux`. The config is saved in Termux at
`~/.config/shield-bot/config.json` (mode 600), and the bot (re)starts.

From then on the bot starts whenever Termux starts (see [USAGE.md](USAGE.md)) and is restarted
10 s after any crash. Open your bot in Telegram and send `/help`.

## Built-in commands

| Command | What it does |
|---|---|
| `/help` | All commands, including yours |
| `/status` | sshd, Claude, uptime, memory, disk, your commands |
| `/sh <cmd>` | Run a command in Debian as root, e.g. `/sh apt update && apt list --upgradable` |
| `/termux <cmd>` | Run a command in Termux, e.g. `/termux pkg upgrade -y` |
| `/commands` | List your custom commands |
| `/logs` | Recent bot and start log lines |
| `/new` | Start a new Claude conversation (Claude forgets earlier messages; the warm process restarts) |
| `/cancel` | Stop the Claude request that is running (the next message resumes the conversation) |

Shell commands time out after 120 s; long output is cut to its last ~3,500 characters (pipe
through `tail` for long output).

## Talking to Claude

Plain messages go to Claude Code, running headless in Debian's `~/workspace` with your Claude
subscription. Telegram shows "typing…" while Claude works; one request runs at a time (others
are queued). The conversation continues across messages until you send `/new`.

**Warm Claude.** The bot keeps one Claude process running between messages (Claude Code's
streaming mode). The first message after a while takes ~15 s (Claude Code starting inside
Debian), the following ones answer in ~2 s plus thinking time. After 15 idle minutes the process
is closed to free its ~250 MB of RAM; the next message starts it again and resumes the
conversation. Change the idle time with `"claude_idle": <seconds>` in the bot config.

Claude's behaviour is defined by `~/workspace/CLAUDE.md` (installed from
[`shield/debian/workspace`](../shield/debian/workspace)): short phone-friendly answers, never
pay or handle passwords, ask before destructive actions, and **how to create bot commands**.

Claude can send files back: it puts `SEND_FILE: /path` in its answer and the bot attaches the
file.

### What Claude may do

Running headless, Claude can't ask for permission mid-task, so tools are pre-allowed in
`~/workspace/.claude/settings.json`: shell (`Bash`), reading/writing files, web search and
fetching pages. Anything else is refused (`--permission-mode dontAsk`). To restrict Claude,
remove entries from that file, e.g. drop `"Bash"` so Claude can write commands but not run
them.

## Browsing with screenshots

Debian has a headless Chromium and a small tool, `~/workspace/tools/browse`, that Claude uses
when you want to *see* web results:

```bash
tools/browse flights "Zurich to Rome on 2026-11-07 one way"     # Google Flights search
tools/browse shot https://example.com --pages 2                 # any page
```

It opens the page in a **warm Chromium** (started on first use, reused by later searches and
closed after 10 idle minutes; `tools/browse stop` closes it at once), declines cookie banners
(the privacy-preserving choice, remembered for later runs), waits for the content, takes
screenshots (viewport by viewport, saved in `~/workspace/screenshots`, deleted
after a day) and prints JSON with the final `url`, the `screenshots` and the visible `text`.
Claude reads prices and times from the text, answers with a summary and the link, and adds a
`SEND_FILE:` line per screenshot; the bot sends images as **photos**.

### Example: flights

Send the bot:

> Search flights from Zurich to Rome on 7 November, one way, and send me screenshots and the
> link to book

After about 30–90 seconds ("typing…" meanwhile; the first message after a pause adds ~15 s) you get:

1. a short summary of the best options (times, airline, stops, price, e.g. *"8:15 → 9:50
   easyJet, nonstop, €101"*), notes such as "prices are currently high",
2. the Google Flights link with your search, to continue and book yourself,
3. two photos of the result list.

Follow-ups continue the same conversation: *"what about returning on 10 November?"*,
*"only nonstop flights after 10 am"*, *"compare with the train"*. Send `/new` to start over.

Notes:

- Claude never logs in, enters passenger data, or presses Book/Pay.
- A search takes ~15 s of browsing (plus Claude's thinking); with little free RAM a second
  screenshot is occasionally skipped (the text and link are always returned).
- Heavier sites may be slower or fail; Claude then tells you and still gives you links.

## Your own commands

Every **executable file** in `/root/workspace/commands/` (inside Debian) is a command; the file
name is the command name. The bot rescans the folder on every message and updates Telegram's
command menu, so new commands work immediately. Write them yourself or ask Claude.

```bash
#!/bin/bash
# description: Shield uptime, free memory and disk
uptime -p
awk '/MemAvailable/ {printf "%d MB free\n", $2/1024}' /proc/meminfo
df -h / | awk 'NR==2 {print $4 " disk free"}'
```

- Names: lowercase letters, digits, `_`, max 32 characters; built-in names are reserved.
- The `# description:` line (within the first lines) is shown in Telegram's menu and `/help`.
- Arguments are passed through: `/plug on` runs `commands/plug on`.
- Commands run as root with cwd `/root/workspace` and are stopped after 120 s.
- Keep secrets in `/root/workspace/.secrets/` (mode 600), never in the command file.

A ready-made `/plug` for Shelly smart plugs is in [`examples/commands/plug`](../examples/commands/plug)
(see [examples/README.md](../examples/README.md)).

Examples you can ask Claude for: *"create /plug that switches my Shelly plug at 192.168.1.50 on
or off"*, *"create /ar4k that runs a command on my gaming PC over SSH"* (Claude creates a key
and tells you where to authorize it), *"create /backup that copies ~/workspace to my NAS"*.

## Security

- Only user IDs in `allowed_user_ids` get answers, and only in private chats; others are
  ignored and logged. Messages sent while the bot was offline are discarded, so old commands
  are never replayed.
- `/sh` and Claude both have **root in Debian** (and Debian can reach Termux's files). Whoever
  controls your Telegram account controls the Shield: enable Telegram's two-step verification.
- Claude treats web pages and command output as data, but prompt injection is a real risk for
  any agent with a shell. Restrict `settings.json` if that worries you.
- The token lives only in `~/.config/shield-bot/config.json` (Termux, mode 600).

## Troubleshooting

- **No answer:** `shield status` (is the bot running?), then on the Shield
  `tail ~/.termux/boot/shield-bot.log` and `~/.termux/boot/shield-bot.err`.
  "ignored message from user N" means N isn't in `allowed_user_ids`.
- **`409 Conflict` in the log:** another program reads the same bot (only one reader is
  possible). Typical cause: Claude Code's old Telegram channel plugin; remove it with
  `claude plugin uninstall telegram@claude-plugins-official` and delete
  `~/.claude/channels/telegram` in Debian.
- **A reply hangs:** `kill -USR1 $(pgrep -f "shield-bot.py --run")` in Termux writes every
  thread's stack to `shield-bot.err`.
- **Change settings:** edit the config (or run `shield bot-setup` again), then
  `/termux pkill -f "shield-bot.py --run"`; the bot restarts with the new config in 10 s.
