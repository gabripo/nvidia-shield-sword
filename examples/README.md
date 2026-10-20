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

## commands/plug: Shelly smart plugs

![/plug pc cycle: phone → Telegram → Shield → Wi-Fi → Shelly plug → PC](../docs/img/plug.svg)

Controls one or more Shelly plugs on your Wi-Fi directly over their local API (Gen2/Gen3/Gen4,
tested with a Shelly Plug S Gen3; no Shelly cloud):

| Command | What it does |
|---|---|
| `/plug` | Status of all plugs, e.g. `1 pc: ON · 48.2 W · 38 °C · 1.24 kWh` |
| `/plug list` | Configured plugs with IP and cycle time |
| `/plug pc on` · `/plug 1 off` · `/plug pc toggle` | Switch a plug, by **name or number** |
| `/plug pc cycle` | **Power cycle**: off for N seconds, then on again |
| `/plug pc cycle 30` | Same, with a 30 s off time this once |

With a single plug configured, the name can be left out (`/plug cycle`).

### Turning a PC on with `cycle`

A PC whose BIOS is set to power on when mains power returns can be started remotely by cutting
its power briefly. `cycle` uses the plug's **own timer** (`Switch.Set` with `toggle_after`): the
plug switches off and back on by itself after N seconds, so the off time is exact even if Wi-Fi
or the Shield is slow. A quick `off`/`on` or `toggle` from the phone is often too short for the
power supply to register a power loss. After the cycle, the reply shows the power draw: tens of
watts means the PC is booting.

BIOS setting (names vary by vendor): ASRock *Advanced → Chipset Configuration → Restore On
AC/Power Loss = Power On*. If the PC doesn't start:

1. With the plug ON, press the PC's power button: `/plug pc` should then show tens of watts.
   If not, the plug doesn't feed the PC (check the PSU's rear switch and the cable).
2. Check the BIOS setting is **Power On** (not *Last State*) and saved.
3. Disable deep power-saving modes (*Deep Sleep*, *ErP Ready*) that can block it on some boards.
4. Try a longer off time: `/plug pc cycle 30`, then set it as the plug's default in `plugs.conf`.
5. Alternative without cutting power: Wake-on-LAN (ask the bot: *"create a command /wake that
   sends a Wake-on-LAN packet to my PC, MAC aa:bb:cc:dd:ee:ff"*).

### Install

1. Find each plug's IP (Shelly app → device → settings → device information, or your router)
   and give it a fixed IP in the router.
2. Install the command (from your Mac, in the repository folder):

   ```bash
   source ~/.config/shield/config
   S() { ssh -p "$SHIELD_SSH_PORT" -i "$SHIELD_SSH_KEY" "$SHIELD_HOST" "$@"; }
   S 'proot-distro login debian -- bash -c "cat > /root/workspace/commands/plug && chmod 755 /root/workspace/commands/plug"' < examples/commands/plug
   ```

3. Configure the plugs in `/root/workspace/.secrets/plugs.conf` (inside Debian, `chmod 600`),
   one per line: number, name, IP, optional cycle seconds (default 10), optional password (only if
   you enabled one in the Shelly app):

   ```
   # number  name   ip              [cycle_seconds]  [password]
   1         pc     192.168.1.50    10
   2         lamp   192.168.1.51
   ```

4. Send `/plug` to the bot. New plugs: add a line, no restart needed.

Or ask the bot: *"add my Shelly plug at 192.168.1.52 as plug 3 named heater"*; Claude edits
`plugs.conf` for you.
