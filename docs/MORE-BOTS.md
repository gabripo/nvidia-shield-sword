# More bots on the Shield

shield-bot answers you. Sometimes you want a bot that **watches something on its own** and writes
to you when it changes: new job postings, new house ads, a price drop. Such a bot runs next to
shield-bot, on the same Shield, as a separate always-on program with its own Telegram bot.

| You want | Use |
|---|---|
| Something done when you ask (`/plugs`, `/pc_on`, a status check) | a command in `/root/workspace/commands/` ([TELEGRAM.md](TELEGRAM.md#your-own-commands)) |
| Something that checks every few minutes and alerts you, with its own buttons and memory | a bot of its own, as below |

Two bots are built this way: **jobbot** (job alerts from careers pages, job boards and alert emails,
scored by Claude) and **casabot** (house ads from alert emails and links, run through a buy-vs-ETF
simulator, added to a shared website with one tap). Both are private repositories; the pattern below
is what they have in common.

## The pattern

| Piece | Where | Why |
|---|---|---|
| Code, config, state | Debian `/root/<bot>/` | Next to Claude Code and Chromium; shield-bot and its workspace stay untouched |
| Secrets | `/root/<bot>/.env`, mode 600 | Written over SSH from the clipboard: `pbpaste \| deploy/deploy.sh secret NAME`, never on screen or in shell history |
| Its own Telegram bot | a new bot from @BotFather | Two programs can't poll one token (`409 Conflict`): never reuse shield-bot's |
| Launcher | Termux `~/.termux/boot/start-<bot>.sh` | Keeps one `proot-distro login` in the background (Debian processes die when their login exits) and restarts the bot 30 s after any exit |
| Deploy | `deploy/deploy.sh` in the bot's repository, on the Mac | Reads `~/.config/shield/config` (`SHIELD_HOST`, `SHIELD_SSH_PORT`, `SHIELD_SSH_KEY`), copies the code with `tar` over SSH: `install`, `update`, `secret`, `start`/`stop`/`status`/`log`, `run <command>` |
| Dependencies | Python's standard library (Node for JavaScript) | Nothing installed with apt or pip: setups and upgrades stay simple |
| Telegram | long polling, answers only your chat id | No port opens at home |

### Start after a reboot

Termux:Boot doesn't run on the Shield ([TROUBLESHOOTING.md](TROUBLESHOOTING.md#termuxboot-doesnt-start-anything-after-a-reboot)),
so add each bot's launcher to Termux's `~/.bashrc`, next to the autostart block that starts
shield-bot. It then starts whenever Termux opens (with the remote, or `shield` from the Mac):

```sh
sh ~/.termux/boot/start-jobbot.sh start >/dev/null 2>&1
sh ~/.termux/boot/start-casabot.sh start >/dev/null 2>&1
```

The launchers are safe to run any number of times.

### Checking what runs

```bash
shield termux
sh ~/.termux/boot/start-<bot>.sh status      # running or stopped, and the last log lines
sh ~/.termux/boot/start-<bot>.sh log 60
```

## One bot mailbox for all bots: shield-mailbox

Bots that read alert emails (LinkedIn job alerts, immobiliare.it saved searches…) never log into
your personal inbox. **[shield-mailbox](https://github.com/gabripo/shield-mailbox)** gives them one
shared **bot Gmail**:

```
your Gmail ──(filters: forward alerts only)──► bot Gmail ──(one label per bot)──► each bot reads its label (IMAP)
```

- One app password per bot, revocable on its own.
- Mail for a bot skips the Inbox and goes under its label (`Casa` for casabot); jobbot reads the Inbox.
- Standard library only; add it to a bot as a git submodule (`lib/shield-mailbox`).
- Setup: [shield-mailbox's Gmail guide](https://github.com/gabripo/shield-mailbox/blob/main/docs/GMAIL.md).

## Reading web pages from a bot

- **`tools/browse`** (headless Chromium, [TELEGRAM.md](TELEGRAM.md#browsing-with-screenshots)) also
  works from a bot: `tools/browse shot <url> --pages 1` prints JSON with the page's text.
- Some sites refuse programs. On 2026-11-14 immobiliare.it answered a plain request with HTTP 403
  and gave headless Chromium an empty page. Respect that: use what the alert email
  says, an API you pay for (casabot can use Firecrawl), or let yourself paste the text into the chat.
- Identify the bot honestly in its User-Agent and keep the request rate low.

## Claude from a bot

A bot can ask Claude through the CLI that shield-bot uses, with your subscription:

```bash
claude -p --output-format json --disallowedTools "Bash,Edit,Write,WebFetch,WebSearch,Read,Glob,Grep" < prompt.txt
```

Every call counts toward the same usage limits as your Claude apps, so call it only when the cheap
checks (rules, patterns) aren't enough.

## Memory

The Shield TV has about 3 GB of RAM, shared with Android and shield-bot's Claude and Chromium.
jobbot uses about 30 MB; a bot that starts Node or Chromium for a few seconds adds that while it
runs. Check with `free -m` in Termux before adding many bots.
