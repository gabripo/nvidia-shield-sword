# Examples

Extra rules for Claude's workspace on the Shield (`/root/workspace` in Debian). The workspace
already has a `CLAUDE.md` (general assistant rules + how to create bot commands); an example adds
a section to it.

## trips

Plan trips from Telegram: Claude asks for what's missing, researches schedules and prices on
the web, proposes 2–3 numbered options with sources and booking links, and **never books, pays
or handles passwords/cards**. The workspace's default tool permissions (web search, web pages,
files, shell) already cover it.

Append it to the workspace rules from your Mac (repository folder):

```bash
source ~/.config/shield/config
ssh -p "$SHIELD_SSH_PORT" -i "$SHIELD_SSH_KEY" "$SHIELD_HOST" \
  'proot-distro login debian -- bash -c "printf \"\n\" >> /root/workspace/CLAUDE.md && cat >> /root/workspace/CLAUDE.md"' \
  < examples/trips/CLAUDE.md
```

Claude reads `CLAUDE.md` on every request, so it applies to the next Telegram message.
Send `/new` first if the current conversation should forget earlier context.
