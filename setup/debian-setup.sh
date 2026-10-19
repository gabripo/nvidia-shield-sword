#!/bin/bash
# Runs inside the Debian container as root (piped by setup/install.sh through
# `proot-distro login debian -- bash -s`). Installs Claude Code (native installer),
# tmux, Node.js and Chromium, keeping the footprint small for the Shield.
set -euo pipefail

# proot-distro appends Termux's bin to PATH; keep Debian's own tools first and only.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive
TZ_NAME="${SHIELD_TIMEZONE:-UTC}"

echo "==> Debian: apt packages (no docs/man pages/translations, see /etc/dpkg/dpkg.cfg.d/01-shield-nodoc)"
apt-get update -qq
apt-get install -y -qq ca-certificates curl git tmux tzdata nodejs >/dev/null
# Headless browser for tools/browse (web pages + screenshots), with fonts so text renders.
apt-get install -y -qq --no-install-recommends chromium fonts-dejavu-core fonts-noto-color-emoji >/dev/null
echo "    $(chromium --version), Node $(node --version)"

# Remove docs/man pages/translations that came with the base image (~200 MB).
find /usr/share/doc -mindepth 1 ! -name copyright ! -type d -delete 2>/dev/null || true
find /usr/share/doc -mindepth 1 -type d -empty -delete 2>/dev/null || true
rm -rf /usr/share/man/* /usr/share/info/* /usr/share/lintian/*
find /usr/share/locale -mindepth 1 -maxdepth 1 ! -name locale.alias -exec rm -rf {} + 2>/dev/null || true

echo "==> Time zone: $TZ_NAME"
if [ -f "/usr/share/zoneinfo/$TZ_NAME" ]; then
  ln -sf "/usr/share/zoneinfo/$TZ_NAME" /etc/localtime
  echo "$TZ_NAME" > /etc/timezone
else
  echo "   unknown time zone '$TZ_NAME', leaving UTC" >&2
fi

echo "==> Claude Code (native installer from claude.ai; updates itself)"
if [ ! -x "$HOME/.local/bin/claude" ]; then
  curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh
  bash /tmp/claude-install.sh >/dev/null
  rm -f /tmp/claude-install.sh
fi
grep -qs 'HOME/.local/bin' "$HOME/.profile" ||
  printf '\n# Native Claude Code installer puts claude here\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.profile"
echo "    $("$HOME/.local/bin/claude" --version)"

# Claude Code asks for focus events (it uses them to track whether its window is active).
grep -qs 'focus-events on' "$HOME/.tmux.conf" || echo 'set -g focus-events on' >> "$HOME/.tmux.conf"

apt-get clean
mkdir -p "$HOME/workspace"
echo "==> Debian setup done"
