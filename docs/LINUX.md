# Linux helper

The Linux version of the Mac helper: the same `shield` command plus a desktop launcher
("Shield" in your applications menu) instead of `Shield.app`.

| File | What it is |
|---|---|
| `linux/shield` | The `shield` command (bash), same subcommands as on macOS |
| `linux/shield-menu` | Graphical menu: zenity (GNOME, Xfce, Cinnamon, …), kdialog (KDE), or whiptail/dialog in a terminal |
| `linux/shield-sword.desktop` | Launcher with right-click actions (Claude session, Status, Start services, Close Claude session) |
| `linux/install.sh` | Installs everything into your home folder, no sudo |

## Install

Dependencies (Debian/Ubuntu names; use your distro's equivalents):

```bash
sudo apt install openssh-client adb zenity      # KDE: kdialog instead of zenity
```

Then, from the repository:

```bash
linux/install.sh
```

It installs:

- `~/.local/bin/shield` and `~/.local/bin/shield-menu`
- `~/.local/share/applications/shield-sword.desktop` (with absolute paths, so it works even if
  `~/.local/bin` isn't on your desktop session's PATH)
- the icon as `~/.local/share/icons/hicolor/scalable/apps/shield-sword.svg`
- `~/.config/shield/config` from `config.example` (if it doesn't exist yet). **Edit it**: set
  `SHIELD_HOST` and `SHIELD_SSH_KEY`.

If `~/.local/bin` isn't on your shell's PATH, the installer tells you the line to add.

## SSH key with a passphrase

macOS reads the passphrase from the keychain; on Linux use your desktop's SSH agent (GNOME Keyring
and KDE Wallet usually provide one) or load the key once per session:

```bash
ssh-add ~/.ssh/id_ed25519
```

Extra ssh options can go in the config, e.g. `SHIELD_SSH_EXTRA="-o AddKeysToAgent=yes"`.

## Use

- **Menu:** open "Shield" from your applications menu, pick an action, **Open**. It runs in a new
  terminal window (`$TERMINAL` if set, otherwise the first of `x-terminal-emulator`,
  `gnome-terminal`, `konsole`, `xfce4-terminal`, `kitty`, `alacritty`, `wezterm`, `foot`, `tilix`,
  `xterm`). Status, Start services and Close Claude session keep the window open until you press Enter.
- **Right-click** the launcher (dock or app grid) for the quick actions.
- **Terminal:** `shield`, `shield debian`, `shield termux`, `shield status`, `shield start`,
  `shield stop`, `shield bot-setup`, exactly as described in [USAGE.md](USAGE.md).

## Setting up the Shield from Linux

`setup/install.sh` is written for macOS (zsh, macOS `nc`). On Linux, the simplest path is to run
the setup once from a Mac, or follow its stages by hand: they are short and documented in
[SETUP.md](SETUP.md). The `shield` helper itself is fully supported on Linux.

## Uninstall

```bash
rm ~/.local/bin/shield ~/.local/bin/shield-menu \
   ~/.local/share/applications/shield-sword.desktop \
   ~/.local/share/icons/hicolor/scalable/apps/shield-sword.svg
rm -r ~/.config/shield        # your settings
```
