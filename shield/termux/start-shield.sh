#!/data/data/com.termux/files/usr/bin/sh
# Installed on the Shield as ~/.termux/boot/start-shield.sh. Run when the Termux app is
# opened (via ~/.bashrc), by Termux:Boot if it works, or by `shield start`.
#
# Keeps Termux awake, starts sshd and keeps the Telegram bot (shield-bot.py) running:
# the bot is restarted 10 s after it exits. Safe to run any number of times.
BOOT="$HOME/.termux/boot"
LOG="$BOOT/start-shield.log"

if [ "${1:-}" = "--bot-loop" ]; then
  while true; do
    python3 "$BOOT/shield-bot.py" --run 2>> "$BOOT/shield-bot.err"
    echo "$(date '+%F %T') shield-bot exited ($?), restarting in 10 s (errors: shield-bot.err)" >> "$LOG"
    sleep 10
  done
fi

echo "$(date '+%F %T') start" >> "$LOG"
termux-wake-lock
pgrep -x sshd >/dev/null || sshd

if [ ! -f "$HOME/.config/shield-bot/config.json" ]; then
  echo "shield-bot not configured (run: shield bot-setup)" >> "$LOG"
  exit 0
fi
if pgrep -f "[s]tart-shield.sh --bot-loop" >/dev/null; then
  echo "shield-bot already running" >> "$LOG"
  exit 0
fi
# Give Wi-Fi time to come up after boot.
for i in $(seq 1 12); do
  curl -s --max-time 3 -o /dev/null https://api.telegram.org && break
  sleep 5
done
nohup sh "$0" --bot-loop >/dev/null 2>&1 < /dev/null &
echo "shield-bot started" >> "$LOG"
