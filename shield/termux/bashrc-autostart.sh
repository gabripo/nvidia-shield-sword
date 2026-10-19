# >>> nvidia-shield-sword autostart >>>
# Appended to Termux's ~/.bashrc by setup/install.sh.
# Starts sshd and the Telegram bot whenever the Termux app is opened on the TV
# (Termux:Boot does not fire reliably on the Shield). Skipped in SSH sessions;
# start-shield.sh itself won't start anything twice, and the lock stops parallel runs.
if [ -z "$SSH_CONNECTION" ] && [ -x "$HOME/.termux/boot/start-shield.sh" ]; then
  if mkdir "$PREFIX/tmp/start-shield.lock" 2>/dev/null; then
    ( nohup sh "$HOME/.termux/boot/start-shield.sh" >/dev/null 2>&1 < /dev/null
      rmdir "$PREFIX/tmp/start-shield.lock" ) &
    echo "Starting sshd and the Shield Telegram bot in the background..."
  fi
fi
# <<< nvidia-shield-sword autostart <<<
