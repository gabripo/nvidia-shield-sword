# Troubleshooting

Lessons learned while building this setup.

### `proot-distro install debian` fails with HTTP 403 / old proot-distro

Termux picked a stale mirror (it chooses one at random and keeps it for 6 hours). An old
mirror ships proot-distro 4.x, whose download host may refuse requests. Pin the official mirror:

```bash
ln -sf $PREFIX/etc/termux/mirrors/default $PREFIX/etc/termux/chosen_mirrors
pkg --check-mirror update && pkg upgrade
```

`setup/install.sh` does this before anything else.

### SSH: "Connection closed" right after `pkg upgrade`

Upgrading `openssh` replaces the binaries under the running `sshd`, which then drops new
connections. In the Termux app on the TV: `pkill sshd; sshd`.

### SSH: "Permission denied (publickey)" although the key is installed

Your private key has a passphrase and isn't loaded. `ssh-add --apple-use-keychain <key>` once;
the tools pass `-o UseKeychain=yes`.

### The `claude` tmux session disappears right after starting

`proot-distro login` kills every process inside Debian when the login command exits. That's why
`start-claude.sh` keeps a background login alive (`while tmux has-session …; sleep 30`).

### `shield` not found

`~/.local/bin` isn't on your PATH: `mac/install.sh` adds it to `~/.zshrc`; open a new Terminal
window or `source ~/.zshrc`.

### Telegram bot doesn't answer, or answers late

1. `shield status`: is the bot running? If not, `shield start`.
2. On the Shield: `tail ~/.termux/boot/shield-bot.log ~/.termux/boot/shield-bot.err`.
3. **`409 Conflict`**: another program reads the same bot. Only one reader is possible; remove
   Claude Code's old Telegram channel plugin if it's installed (see [TELEGRAM.md](TELEGRAM.md)).
4. **Replies late after the TV slept**: connections to Telegram's IPv6 address can hang while
   the TV is in standby. shield-bot uses IPv4 only for that reason; if you write your own tools,
   do the same (e.g. `curl -4`).
5. Claude answers but refuses an action: it isn't pre-allowed in
   `~/workspace/.claude/settings.json` (headless Claude can't ask).

### Termux:Boot doesn't start anything after a reboot

Known on the Shield ([termux-boot#62](https://github.com/termux/termux-boot/issues/62)). Open
Termux once (remote, or `shield` from the Mac).

### Times in Debian are off by hours

Debian defaults to UTC. Set `SHIELD_TIMEZONE` in your config and re-run
`setup/install.sh --from debian`, or inside Debian:
`ln -sf /usr/share/zoneinfo/Europe/Zurich /etc/localtime`.

### A reply hangs

`kill -USR1 $(pgrep -f "shield-bot.py --run")` in Termux writes every thread's stack to
`~/.termux/boot/shield-bot.err`.

### Things that did not work on the Shield (so you don't have to try)

- **Hermes Agent** (Nous Research): `install.sh` inside proot picks Termux's Android Python or
  fails to find its own managed Python; the Termux APT package lacks the `anthropic` package and
  can't build it on Android. Removed in favour of Claude Code.
- **Headless Chromium screenshots** of heavy booking sites: simple pages work, but large sites
  hang (≈600 MB free RAM), and SwiftShader rendering segfaults under proot.
- **agent-browser** on Android: the npm package ships an empty Android binary.
- **Claude Code's Telegram channel plugin** as the bot: works, but every message costs Claude
  usage, permission prompts can't be answered remotely, and it can't coexist with a second
  reader of the same bot. Replaced by `shield-bot`, which calls Claude only when needed.
