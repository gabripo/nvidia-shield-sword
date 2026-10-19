#!/bin/bash
# Runs inside the Debian container as root (piped by setup/install.sh through
# `proot-distro login debian -- bash -s`). Installs Claude Code and tmux.
set -euo pipefail

# proot-distro appends Termux's bin to PATH; keep Debian's own tools first and only.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive
TZ_NAME="${SHIELD_TIMEZONE:-UTC}"

echo "==> Debian: apt packages"
apt-get update -qq
apt-get install -y -qq ca-certificates curl git tmux unzip tzdata nodejs npm >/dev/null

echo "==> Time zone: $TZ_NAME"
if [ -f "/usr/share/zoneinfo/$TZ_NAME" ]; then
  ln -sf "/usr/share/zoneinfo/$TZ_NAME" /etc/localtime
  echo "$TZ_NAME" > /etc/timezone
else
  echo "   unknown time zone '$TZ_NAME', leaving UTC" >&2
fi

echo "==> Node $(node --version), npm $(npm --version)"

echo "==> Claude Code"
npm install -g --no-fund --no-audit @anthropic-ai/claude-code >/dev/null
echo "    $(claude --version)"

# Claude Code asks for focus events (it uses them to track whether its window is active).
grep -qs 'focus-events on' "$HOME/.tmux.conf" || echo 'set -g focus-events on' >> "$HOME/.tmux.conf"

mkdir -p "$HOME/workspace"
echo "==> Debian setup done"
