# Examples

Ready-made bot commands and extra rules for Claude's workspace on the Shield
(`/root/workspace` in Debian).

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

## commands/plug: Shelly smart plug

`/plug [on|off|toggle|status]` switches a Shelly plug on your Wi-Fi and reports its state, power,
voltage, temperature and energy, e.g. `Plug is ON · 42.0 W · 235 V · 38 °C · 1.24 kWh total`.
Works with Shelly's Gen2/Gen3/Gen4 RPC API (tested with a Shelly Plug S Gen3); talks to the plug
directly on your LAN, no Shelly cloud.

1. Find the plug's IP (Shelly app → device → settings → device information, or your router) and
   give it a fixed IP in the router.
2. Install it (from your Mac, in the repository folder; replace the IP):

   ```bash
   source ~/.config/shield/config
   S() { ssh -p "$SHIELD_SSH_PORT" -i "$SHIELD_SSH_KEY" "$SHIELD_HOST" "$@"; }
   S 'proot-distro login debian -- bash -c "cat > /root/workspace/commands/plug && chmod 755 /root/workspace/commands/plug"' < examples/commands/plug
   S 'proot-distro login debian -- bash -c "mkdir -p -m 700 /root/workspace/.secrets && umask 077 && echo SHELLY_HOST=192.168.1.50 > /root/workspace/.secrets/plug.env"'
   ```

3. Send `/plug` to the bot. If you set a password on the plug, add `SHELLY_PASS=<password>` to
   `plug.env` (never in the command file).

Or just ask the bot: *"create a command /plug that switches my Shelly plug at 192.168.1.50"*;
Claude can write the same thing.
