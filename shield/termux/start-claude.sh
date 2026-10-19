#!/data/data/com.termux/files/usr/bin/sh
# Installed on the Shield as ~/.termux/boot/start-claude.sh. Used by `shield claude`.
#
# Opens an interactive Claude Code session in a tmux session named "claude" inside
# Debian (in ~/workspace). It is only for working at the terminal: the Telegram bot
# doesn't need it. /exit in Claude ends the session. Safe to run any number of times.
LOG="$HOME/.termux/boot/start-shield.log"

# proot-distro kills everything inside Debian when its login command exits, so this
# login stays in the background for as long as the tmux session lives.
nohup proot-distro login debian -- bash -lc '
  # new-session fails if "claude" already exists, so two parallel starts cannot both win.
  tmux new-session -d -s claude "mkdir -p ~/workspace && cd ~/workspace && claude" 2>/dev/null \
    || { echo "claude session already running"; exit 0; }
  echo "claude session started"
  while tmux has-session -t claude 2>/dev/null; do sleep 30; done
  echo "claude session ended"
' >> "$LOG" 2>&1 < /dev/null &
