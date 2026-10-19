#!/usr/bin/env bash
# Install the Linux helper: `shield`, `shield-menu`, the desktop launcher, icon and config.
# Everything goes into your home folder (no sudo).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
BIN="$HOME/.local/bin"
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/shield"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"

echo "==> Installing shield and shield-menu to $BIN"
mkdir -p "$BIN"
install -m 755 "$HERE/shield" "$BIN/shield"
install -m 755 "$HERE/shield-menu" "$BIN/shield-menu"

if [[ ! -f "$CONF_DIR/config" ]]; then
  mkdir -p "$CONF_DIR"
  cp "$REPO/config.example" "$CONF_DIR/config"
  echo "==> Created $CONF_DIR/config - EDIT IT (Shield IP address, SSH key)"
else
  echo "==> Keeping existing $CONF_DIR/config"
fi

echo "==> Installing icon and desktop launcher"
install -D -m 644 "$REPO/mac/icon/shield-icon.svg" "$DATA/icons/hicolor/scalable/apps/shield-sword.svg"
mkdir -p "$DATA/applications"
# Use absolute paths: desktop sessions don't always have ~/.local/bin on PATH.
sed "s|^Exec=shield-menu|Exec=$BIN/shield-menu|" "$HERE/shield-sword.desktop" \
  > "$DATA/applications/shield-sword.desktop"
chmod 644 "$DATA/applications/shield-sword.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" || true

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "!! $BIN is not on your PATH. Add this to ~/.bashrc or ~/.zshrc:"
     echo "     export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

missing=()
command -v ssh >/dev/null || missing+=(openssh-client)
command -v adb >/dev/null || missing+=("adb (android-tools)")
command -v zenity >/dev/null || command -v kdialog >/dev/null || missing+=("zenity or kdialog (for the menu)")
if ((${#missing[@]})); then
  echo "!! Also install: ${missing[*]}"
fi
echo "==> Done. Find \"Shield\" in your applications menu, or run: shield status"
