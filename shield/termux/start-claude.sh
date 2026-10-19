#!/data/data/com.termux/files/usr/bin/sh
# Installed on the Shield as ~/.termux/boot/start-claude.sh.
#
# Keeps Termux awake, starts sshd, then starts Claude Code with the Telegram
# channel in a tmux session named "claude" inside Debian. Claude is restarted
# 15 s after any exit (including /exit), so the Telegram bot stays online.
# Leave the session with Ctrl+b then d. Safe to run any number of times.
LOG="$HOME/.termux/boot/start-claude.log"
echo "$(date '+%F %T') start" >> "$LOG"
termux-wake-lock
pgrep -x sshd >/dev/null || sshd

# Give Wi-Fi time to come up after boot.
for i in $(seq 1 12); do
  curl -s --max-time 3 -o /dev/null https://api.telegram.org && break
  sleep 5
done

# proot-distro kills everything inside Debian when its login command exits, so this
# login stays in the background for as long as the tmux session lives.
nohup proot-distro login debian -- bash -lc '
  # new-session fails if "claude" already exists, so two parallel starts cannot both win.
  tmux new-session -d -s claude "cd ~/trips && while true; do claude --channels plugin:telegram@claude-plugins-official; sleep 15; done" 2>/dev/null \
    || { echo "claude session already running"; exit 0; }
  echo "claude session started"
  while tmux has-session -t claude 2>/dev/null; do sleep 60; done
  echo "claude session ended"
' >> "$LOG" 2>&1 < /dev/null &
