# Setup

What you need:

- NVIDIA Shield TV (any arm64 model, Android 11 tested), on the same network as your Mac
- A Mac with [Homebrew](https://brew.sh)
- A Claude Pro or Max subscription (or an Anthropic API key)
- Telegram on your phone

About 2.5 GB of free storage on the Shield is needed (Termux, Debian, Node.js, Claude Code, Bun).

## 1. Enable network ADB on the Shield

1. **Settings → Device Preferences → About**, click **Build** 7 times to unlock developer options.
2. **Settings → Device Preferences → Developer options**: enable **Network debugging**
   (and **USB debugging**). Note the IP address shown.
3. Give the Shield a fixed IP in your router (DHCP reservation), so the address never changes.

## 2. Prepare the Mac

```bash
brew install android-platform-tools
adb connect <SHIELD_IP>:5555        # accept the "Allow network debugging?" prompt on the TV
adb devices                         # should list <SHIELD_IP>:5555  device
```

An SSH key for logging in to the Shield (skip if you already have one you want to use):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

If the key has a passphrase, store it in the macOS keychain once:

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

## 3. Install the Mac helper and configure

```bash
git clone https://github.com/gabripo/nvidia-shield-sword.git
cd nvidia-shield-sword
mac/install.sh
```

This installs the `shield` command (`~/.local/bin`), `Shield.app` (`~/Applications`) and creates
`~/.config/shield/config`. **Edit that file**: set `SHIELD_HOST`, `SHIELD_SSH_KEY` and
`SHIELD_TIMEZONE` (find the Shield's zone with `adb shell getprop persist.sys.timezone`).

## 4. Set up the Shield

```bash
setup/install.sh
```

Stages (each prints what it does):

| Stage | What happens |
|---|---|
| `termux-app` | Downloads the latest Termux release from GitHub (arm64) and installs it with adb. Skipped if Termux is installed. |
| `termux-bootstrap` | Opens Termux on the TV and **types one command into it** (watch the TV, don't touch the remote): pins the official package mirror, upgrades all packages, installs OpenSSH, adds your public key and starts `sshd`. Then waits for SSH. |
| `termux` | Installs `proot-distro` and the Debian trixie container `debian`. |
| `debian` | Installs tmux, Node.js, Claude Code, Bun; sets the time zone. |
| `files` | Installs `~/.termux/boot/start-claude.sh`, the `~/.bashrc` autostart hook and `~/trips`. |

If a stage fails, fix the cause and resume, e.g. `setup/install.sh --from debian`.

> The `termux-app` stage installs the **GitHub** build of Termux. Don't mix it with Termux add-ons
> from F-Droid or Google Play: they are signed with different keys.

## 5. Sign in to Claude

```bash
shield debian          # opens a Debian shell on the Shield
cd ~/trips && claude
```

1. Pick a theme, then **"Claude account with subscription"**.
2. Claude Code shows a sign-in link: Cmd-click it, approve in the browser, paste the code back.
3. Accept **"Yes, I trust this folder"** for `~/trips`.
4. `/status` shows your account. Then `/exit`.

Install the Telegram channel plugin (user scope, available in every folder):

```bash
claude plugin install telegram@claude-plugins-official --scope user
```

Continue with **[TELEGRAM.md](TELEGRAM.md)**.

## Optional: Termux:Boot

[Termux:Boot](https://github.com/termux/termux-boot) runs `~/.termux/boot/*` at Android boot. On
the Shield it receives the boot event but often fails to start Termux
([termux-boot#62](https://github.com/termux/termux-boot/issues/62)), which is why this project
starts everything when the Termux app is opened instead. Installing it does no harm: install the
GitHub build, open it once, and the same `start-claude.sh` will run at boot if it works.
