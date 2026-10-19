# Examples

Ready-made setups for Claude's workspace on the Shield (`/root/workspace` in Debian).
Each one is a `CLAUDE.md` (rules Claude reads at every start) plus `.claude/settings.json`
(tools Claude may use without asking, important because prompts can't be answered from Telegram).

## trips

Plan trips from Telegram: Claude asks for what's missing, researches schedules and prices on
the web, proposes 2–3 numbered options with sources and booking links, and **never books, pays
or handles passwords/cards**. Pre-allows web search, fetching pages, and reading/editing files
inside the workspace.

Install it into the workspace from your Mac (repository folder):

```bash
source ~/.config/shield/config
COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -C examples/trips -cf - . | \
  ssh -p "$SHIELD_SSH_PORT" -i "$SHIELD_SSH_KEY" "$SHIELD_HOST" \
  'proot-distro login debian -- bash -c "mkdir -p /root/workspace && tar -C /root/workspace -xf -"'
```

Then restart Claude so it reads the new rules: `shield stop && shield start`.
Claude asks once (in the terminal, via `shield`) to trust the changed settings.
