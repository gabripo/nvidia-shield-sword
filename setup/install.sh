#!/bin/zsh
# nvidia-shield-sword installer - run on the Mac.
#
# Sets up Termux, a Debian container, Claude Code, Bun and the Telegram channel
# plugin on an NVIDIA Shield (Android TV, arm64) connected over network ADB.
#
# Usage: setup/install.sh [--from STAGE]
#   Stages, in order: termux-app, termux-bootstrap, termux, debian, files
#   --from lets you resume after fixing a failed stage.
#
# Reads ~/.config/shield/config (see config.example).
set -euo pipefail

REPO="${0:A:h:h}"
CONFIG="${SHIELD_CONFIG:-$HOME/.config/shield/config}"
[[ -f "$CONFIG" ]] || { echo "Missing $CONFIG - copy config.example there and edit it (or run mac/install.sh)." >&2; exit 1; }
source "$CONFIG"

ADB="${ADB:-$(command -v adb || true)}"
DEV="$SHIELD_HOST:$SHIELD_ADB_PORT"
SSH_OPTS=(-p "$SHIELD_SSH_PORT" -i "$SHIELD_SSH_KEY" -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new)
[[ "$(uname)" == Darwin ]] && SSH_OPTS+=(-o UseKeychain=yes)

STAGES=(termux-app termux-bootstrap termux debian files)
FROM="${STAGES[1]}"
[[ "${1:-}" == "--from" ]] && FROM="${2:?--from needs a stage name}"
(( ${STAGES[(Ie)$FROM]} )) || { echo "Unknown stage '$FROM'. Stages: ${STAGES[*]}" >&2; exit 1; }

step() { print -P "\n%F{green}==>%f %B$*%b"; }
die()  { print -P "%F{red}!!%f $*" >&2; exit 1; }
want() { (( ${STAGES[(Ie)$1]} >= ${STAGES[(Ie)$FROM]} )); }
adbs() { "$ADB" -s "$DEV" "$@"; }
ssh_up() { nc -z -G 2 "$SHIELD_HOST" "$SHIELD_SSH_PORT" >/dev/null 2>&1; }
remote() { ssh "${SSH_OPTS[@]}" "$SHIELD_HOST" "$@"; }

[[ -x "$ADB" ]] || die "adb not found (brew install android-platform-tools)"
[[ -f "$SHIELD_SSH_KEY.pub" ]] || die "No public key at $SHIELD_SSH_KEY.pub (ssh-keygen -t ed25519)"

step "Connecting to the Shield over ADB ($DEV)"
"$ADB" connect "$DEV" >/dev/null || true
[[ "$(adbs get-state 2>/dev/null)" == device ]] || die "adb can't reach $DEV. Enable Network debugging on the Shield and accept the prompt on the TV."
abi=$(adbs shell getprop ro.product.cpu.abi | tr -d '\r')
[[ "$abi" == arm64-v8a ]] || die "Unexpected ABI '$abi' (need arm64-v8a)"
echo "    $(adbs shell getprop ro.product.model | tr -d '\r'), Android $(adbs shell getprop ro.build.version.release | tr -d '\r')"

if want termux-app; then
  step "Termux app"
  if adbs shell pm list packages com.termux | grep -q 'package:com.termux$'; then
    echo "    already installed ($(adbs shell dumpsys package com.termux | grep -m1 versionName | tr -d ' \r'))"
  else
    tmp=$(mktemp -d)
    url=$(curl -fsSL https://api.github.com/repos/termux/termux-app/releases/latest |
          python3 -I -c 'import json,sys; print(next(a["browser_download_url"] for a in json.load(sys.stdin)["assets"] if a["name"].endswith("arm64-v8a.apk")))')
    echo "    downloading $url"
    curl -fL -o "$tmp/termux.apk" "$url"
    adbs install -r "$tmp/termux.apk"
    rm -rf "$tmp"
  fi
fi

if want termux-bootstrap; then
  step "Termux first start + SSH bootstrap"
  if ssh_up && remote true 2>/dev/null; then
    echo "    SSH already works - skipping"
  else
    adbs shell input keyevent 224                     # wake the screen
    adbs shell am start -n com.termux/com.termux.app.TermuxActivity >/dev/null
    echo "    waiting for Termux to finish its first-run setup..."
    for i in {1..36}; do
      adbs shell run-as com.termux ls files/usr/bin/bash >/dev/null 2>&1 && break
      sleep 5
    done
    sleep 10
    [[ "$(adbs shell dumpsys window | grep -m1 mCurrentFocus)" == *com.termux* ]] || die "Termux is not in the foreground on the TV."
    pub=$(<"$SHIELD_SSH_KEY.pub")
    [[ "$pub" != *"'"* ]] || die "Public key contains a single quote"
    line="termux-wake-lock; ln -sf \$PREFIX/etc/termux/mirrors/default \$PREFIX/etc/termux/chosen_mirrors; yes | pkg upgrade -y -o Dpkg::Options::=--force-confnew && pkg install -y openssh && mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pub' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && sshd"
    tmpf=$(mktemp); print -r -- "$line" > "$tmpf"
    echo "    typing the bootstrap command into Termux (watch the TV)"
    python3 -I "$REPO/setup/lib/typeline.py" --file "$tmpf" --chunk 200 --enter
    rm -f "$tmpf"
    echo "    waiting for sshd (pkg upgrade can take several minutes)..."
    for i in {1..60}; do ssh_up && remote true 2>/dev/null && break; sleep 15; done
    remote true || die "SSH did not come up. Check the Termux screen on the TV."
  fi
fi

if want termux; then
  step "Termux: proot-distro + Debian"
  remote 'bash -s' < "$REPO/setup/termux-setup.sh"
fi

if want debian; then
  step "Debian: Claude Code, Bun, tmux"
  remote "proot-distro login debian -- env SHIELD_TIMEZONE='$SHIELD_TIMEZONE' bash -s" < "$REPO/setup/debian-setup.sh"
fi

if want files; then
  step "Installing autostart and trips workspace"
  remote 'mkdir -p ~/.termux/boot && cat > ~/.termux/boot/start-claude.sh && chmod 700 ~/.termux/boot/start-claude.sh' \
    < "$REPO/shield/termux/start-claude.sh"
  remote 'f=~/.bashrc; touch $f; sed -i "/>>> nvidia-shield-sword autostart >>>/,/<<< nvidia-shield-sword autostart <<</d" $f; cat >> $f; chmod 600 $f' \
    < "$REPO/shield/termux/bashrc-autostart.sh"
  # Copy ~/trips (CLAUDE.md + .claude/settings.json) into Debian without overwriting your own edits.
  COPYFILE_DISABLE=1 tar -C "$REPO/shield/debian" -cf - trips | remote 'proot-distro login debian -- tar -C /root --skip-old-files -xf -'
fi

step "Done"
cat <<EOF
Next steps (see docs/SETUP.md and docs/TELEGRAM.md):
  1. Install the Mac helper:      mac/install.sh
  2. Sign in to Claude:           shield debian   then   claude   (choose your Claude subscription)
  3. Install the Telegram plugin: claude plugin install telegram@claude-plugins-official --scope user
  4. Create the bot, configure the token and pair your account (docs/TELEGRAM.md)
EOF
