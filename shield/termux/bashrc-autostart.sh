# >>> nvidia-shield-sword autostart >>>
# Appended to Termux's ~/.bashrc by setup/install.sh.
# Starts sshd, Debian and Claude Code whenever the Termux app is opened on the TV
# (Termux:Boot does not fire reliably on the Shield). Skipped in SSH sessions;
# start-claude.sh itself won't start anything twice, and the lock stops parallel runs.
if [ -z "$SSH_CONNECTION" ] && [ -x "$HOME/.termux/boot/start-claude.sh" ]; then
  if mkdir "$PREFIX/tmp/start-claude.lock" 2>/dev/null; then
    ( nohup sh "$HOME/.termux/boot/start-claude.sh" >/dev/null 2>&1 < /dev/null
      rmdir "$PREFIX/tmp/start-claude.lock" ) &
    echo "Starting Claude Code in the background (tmux session 'claude' in Debian)..."
  fi
fi
# <<< nvidia-shield-sword autostart <<<
