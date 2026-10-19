#!/bin/bash
# Runs inside the Debian container as root (piped by setup/install.sh through
# `proot-distro login debian -- bash -s`). Installs Claude Code, Bun and tmux.
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

echo "==> Bun (needed by the Telegram channel plugin)"
if [ ! -x "$HOME/.bun/bin/bun" ]; then
  curl -fsSL https://bun.sh/install -o /tmp/bun-install.sh
  bash /tmp/bun-install.sh >/dev/null
  rm -f /tmp/bun-install.sh
fi
echo "    bun $("$HOME/.bun/bin/bun" --version)"

mkdir -p "$HOME/trips/.claude"
echo "==> Debian setup done"
