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
| `/plug pc cycle` | **Power cycle**: off for N seconds (default 60), then on again |
| `/plug pc cycle 90` | Same, with a 90 s off time this once |

With a single plug configured, the name can be left out (`/plug cycle`).

Every plug also gets **one-tap entries in Telegram's command menu**, generated from
`plugs.conf`: `/plug_pc` (status), `/plug_pc_on`, `/plug_pc_off`, `/plug_pc_toggle`,
`/plug_pc_cycle`. Add a plug and its entries appear within a minute. The bare `/plug` is not
listed in the menu (`# menu-hide: yes`) but still works when typed.

### Turning a PC on with `cycle`

A PC whose BIOS is set to power on when mains power returns can be started remotely by cutting
its power briefly. `cycle` uses the plug's **own timer** (`Switch.Set` with `toggle_after`): the
plug switches off and back on by itself after N seconds, so the off time is exact even if Wi-Fi
or the Shield is slow. A quick `off`/`on` or `toggle` from the phone is often too short for the
power supply to register a power loss. After the cycle, the reply shows the power draw: tens of
watts means the PC is booting.

The trick works with **most desktop PCs**: almost every motherboard can boot automatically when
mains power returns. Only the BIOS option names and the needed off time differ.

#### Adapting it to your PC

1. **Enable power-on after power loss.** Typical names (they vary by BIOS version; look in the
   power, ACPI, chipset or advanced menus):

   | Vendor | Typical option | Value |
   |---|---|---|
   | ASRock | Restore on AC/Power Loss | Power On |
   | ASUS | Restore AC Power Loss | Power On |
   | MSI | Restore after AC Power Loss | Power On |
   | Gigabyte | AC BACK | Always On |
   | Dell / HP / Lenovo (office PCs) | AC Recovery / After Power Loss / After Power Failure | Power On |

   Use *Power On* / *Always On*, not *Last State*: with *Last State*, a PC you shut down normally
   stays off.
2. **Disable deep power-saving modes** that can keep the board from noticing power returning:
   *Deep Sleep*, *ErP Ready*, *EuP*, *Deep S4/S5*.
3. **Optional:** disable USB power in the off state (*USB power in S5*, *USB standby power*) if you
   don't want USB devices powered while the PC is off; disable USB wake options then too.
4. **Find the off time.** Shut the PC down, then try `/plug pc cycle 30`, `60`, `90`… until it
   boots (the reply shows tens of watts when it does). Put the working value in `plugs.conf`
   (fourth column) so `/plug pc cycle` always uses it.
5. **Check it twice**, also after a normal shutdown from the operating system.

#### Tested configurations

| PC / motherboard | BIOS settings | Plug | Off time |
|---|---|---|---|
| ASRock **B850M Pro RS** (AMD AM5) | *Advanced → ACPI Configuration*: Restore on AC/Power Loss = **Power On**, Deep Sleep = **Disabled**; optional: USB Power delivery in Soft Off state (S5) = Disabled, USB Device Power on = Disabled | Shelly Plug S Gen3 (fw 1.7.3) | 10, 15 and 30 s: **no**; **60 s: boots** ✅ |

Notes from that test:

- Settings as documented in ASRock's *AMD 800 Series Software/BIOS Setup Guide*, section 3.4.5,
  which also recommends Deep Sleep = Disabled.
- *USB Power delivery in Soft Off state (S5) = Disabled* left some USB ports powered on this
  board; turning the plug off after shutdown removes all power if that matters to you.
- A shut-down PC reads **0.0 W** on the plug (standby draw is below its resolution), so the
  reading can't tell whether standby power is present.

Tested another PC? A pull request adding a row to this table is welcome.

#### If the PC doesn't start

1. With the plug ON, press the PC's power button: `/plug pc` should show tens of watts while it
   boots. If not, the plug doesn't feed the PC (check the PSU's rear switch and the cable).
   Note: a shut-down PC usually shows **0.0 W**; its standby draw is below what the plug measures.
2. Check *Restore on AC/Power Loss* is **Power On** (not *Last State*) and saved (F10).
3. Disable *Deep Sleep* / *ErP Ready*.
4. Lengthen the off time (`/plug pc cycle 90`).
5. Alternative without cutting power: Wake-on-LAN (BIOS *PCIE Devices Power On = Enabled*; ask
   the bot: *"create a command /wake that sends a Wake-on-LAN packet to my PC, MAC
   aa:bb:cc:dd:ee:ff"*).

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
   one per line: number, name, IP, optional cycle seconds (default 60), optional password (only if
   you enabled one in the Shelly app):

   ```
   # number  name   ip              [cycle_seconds]  [password]
   1         pc     192.168.1.50    60
   2         lamp   192.168.1.51
   ```

4. Send `/plug` to the bot. New plugs: add a line, no restart needed.

Or ask the bot: *"add my Shelly plug at 192.168.1.52 as plug 3 named heater"*; Claude edits
`plugs.conf` for you.
