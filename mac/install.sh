#!/bin/zsh
# Install the Mac helper: the `shield` command, its config file and Shield.app.
set -euo pipefail
HERE="${0:A:h}"
REPO="${HERE:h}"
BIN="$HOME/.local/bin"
CONF_DIR="$HOME/.config/shield"

echo "==> Installing the shield command to $BIN"
mkdir -p "$BIN"
install -m 755 "$HERE/shield" "$BIN/shield"

if [[ ! -f "$CONF_DIR/config" ]]; then
  mkdir -p "$CONF_DIR"
  cp "$REPO/config.example" "$CONF_DIR/config"
  echo "==> Created $CONF_DIR/config - EDIT IT (Shield IP address, SSH key)"
else
  echo "==> Keeping existing $CONF_DIR/config"
fi

# Make sure ~/.local/bin is on the zsh PATH.
if ! grep -q '\.local/bin' "$HOME/.zshrc" 2>/dev/null; then
  printf '\n# Personal command-line tools (e.g. `shield` for the NVIDIA Shield)\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.zshrc"
  echo "==> Added ~/.local/bin to PATH in ~/.zshrc (open a new Terminal window)"
fi

"$HERE/build-app.sh"
mkdir -p "$HOME/Applications"
rm -rf "$HOME/Applications/Shield.app"
cp -R "$HERE/build/Shield.app" "$HOME/Applications/"
echo "==> Installed $HOME/Applications/Shield.app (find it with Spotlight: \"Shield\")"
