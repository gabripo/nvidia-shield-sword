<p align="center"><img src="docs/img/icon.png" width="160" alt="Shield helper icon"></p>

# nvidia-shield-sword

Turn an **NVIDIA Shield** (Android TV) into an always-on home assistant you steer from your
phone through **one Telegram bot**: instant built-in commands, your own commands (power plugs,
SSH to other machines, …), and **Claude Code** for everything else. Claude can even add new
bot commands when you ask. A small **macOS / Linux helper** (`shield` command + `Shield.app`)
gets you into the Shield over SSH with one click.

```
                                   ┌─ /status, /sh, /termux, /new …   built-ins: instant, no Claude
 Phone ── Telegram ──► shield-bot ─┼─ /tvinfo, /plug, /ar4k …   your scripts in ~/workspace/commands
           (one bot)   (Termux)    └─ anything else ─► claude -p in ~/workspace (your subscription)
                                                       └─ can create new commands on request

 Mac ── Shield.app / `shield` ── SSH ──► Termux ──► Debian (proot-distro)
        adb (network) wakes Termux after a reboot
```

- **No root needed**: Termux + a Debian container via `proot-distro`.
- **One bot, three layers**: built-ins and your commands cost no Claude usage; only free-form
  requests go to Claude ([docs/TELEGRAM.md](docs/TELEGRAM.md)).
- **Extensible by Claude**: *"create a command /ar4k that connects via SSH to the gaming PC"*.
- **Uses your Claude subscription** (Pro/Max): sign in once, same quota as the Claude apps.
- **Locked to you**: only allowlisted Telegram user IDs, private chats only.
- **Self-starting**: opening Termux (or `shield` from the Mac, via adb) starts sshd and the bot;
  the bot restarts by itself after a crash.

## Repository layout

| Path | What it is |
|---|---|
| `setup/install.sh` | Mac-side installer: Termux, SSH, Debian, Claude Code, bot, autostart |
| `setup/termux-setup.sh`, `setup/debian-setup.sh` | Run on the Shield (piped over SSH by the installer) |
| `setup/lib/typeline.py` | Types the one-time SSH bootstrap command into Termux via `adb shell input text` |
| `shield/termux/` | `shield-bot.py` (the Telegram bot), `start-shield.sh` (sshd + bot), `start-claude.sh` (interactive Claude on demand), the `~/.bashrc` autostart hook |
| `shield/debian/workspace/` | Claude's workspace template: `CLAUDE.md` (rules, how to create commands), pre-allowed tools, `commands/` |
| `examples/trips/` | Optional trip-planning rules to add to the workspace |
| `mac/` | `shield` command, `Shield.app` source (AppleScript + SVG icon), build and install scripts |
| `linux/` | Linux version of the helper: `shield`, a zenity/kdialog menu and a desktop launcher ([docs/LINUX.md](docs/LINUX.md)) |
| `config.example` | Settings (Shield IP, SSH key, time zone) |
| `docs/` | Guides |

## Quick start

1. Prepare the Shield and the Mac: **[docs/SETUP.md](docs/SETUP.md)** (ADB, SSH key, config).
2. `mac/install.sh` (installs the `shield` command, config and Shield.app). On Linux:
   `linux/install.sh`, see [docs/LINUX.md](docs/LINUX.md).
3. `setup/install.sh` (sets up everything on the Shield, about 15–30 minutes).
4. Sign in to Claude and set up the bot: **[docs/TELEGRAM.md](docs/TELEGRAM.md)**.
5. Day-to-day use: **[docs/USAGE.md](docs/USAGE.md)**. Problems: **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**.

## Status

Every step was run and verified by hand on an NVIDIA Shield TV (Android 11) with a Mac
(macOS 15). The scripts codify those steps and were syntax-checked; the full `setup/install.sh`
run on a factory-fresh Shield has **not** been tested end to end yet. Each stage can be resumed
with `setup/install.sh --from <stage>`.

## Safety notes

- Whoever is on the bot's allowlist gets a root shell in Debian (`/sh`) and a Claude agent with a
  shell. Keep the allowlist to yourself, protect your Telegram account (two-step verification),
  and trim `~/workspace/.claude/settings.json` if you want Claude to have less power.
- The workspace rules tell Claude never to pay, book, or handle passwords/cards. Treat that as a
  guideline, not a security boundary.
- Termux's sshd accepts key logins from your home network. Don't forward port 8022 on your router.
- Not affiliated with or endorsed by NVIDIA. "NVIDIA" and "SHIELD" are trademarks of NVIDIA
  Corporation; the icon is an original drawing.

## License

MIT, see [LICENSE](LICENSE).
