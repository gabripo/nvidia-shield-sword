# Telegram bot

Claude Code's **channels** feature (research preview) pushes your Telegram messages into the
running Claude session on the Shield and sends Claude's replies back to the chat. It uses the
official plugin `telegram@claude-plugins-official` and needs [Bun](https://bun.sh), which the
installer sets up.

Docs: <https://code.claude.com/docs/en/channels> ·
plugin source: <https://github.com/anthropics/claude-plugins-official/tree/main/external_plugins/telegram>

## 1. Create the bot

In Telegram, open **@BotFather**, send `/newbot`, choose a display name and a username ending in
`bot`. BotFather replies with a **token** like `123456789:AA...`. Keep it secret: anyone with it
controls the bot. (`/revoke` in BotFather issues a new one.)

## 2. Save the token on the Shield

```bash
shield            # attaches to the Claude session (starts it if needed)
```

In Claude Code:

```
/telegram:configure <your-bot-token>
/exit
```

The token is stored in Debian at `~/.claude/channels/telegram/.env`. After `/exit` the
session's loop restarts Claude in about 15 s, now with the Telegram channel connected.
The startup screen shows "Channels (experimental) messages from plugin:telegram@… inject
directly in this session".

## 3. Pair your account

1. On your phone, send any message (e.g. "hi") to your bot. It replies with a **pairing code**.
2. In the Claude terminal:

   ```
   /telegram:access pair <code>
   /telegram:access policy allowlist
   ```

With the `allowlist` policy, messages from anyone else are silently dropped.

## 4. First message (stay at the terminal)

Send something from Telegram, e.g. *"What's the date and how much disk space is free?"*.
The first time Claude replies through Telegram, the terminal asks permission for the plugin's
reply tool: choose **"Yes, and don't ask again"** so later replies don't wait for you.

Then leave the session running: **Ctrl+b**, then **d** (tmux detach).

## How steering works

You write plain language; Claude works in `~/workspace` inside Debian and answers in the chat.
The examples below assume the trip-planning rules from [`examples/trips`](../examples/trips).
It can send files back (e.g. `options.md`) as Telegram documents.

| You send | Claude |
|---|---|
| "Plan 3 days in Florence from Zurich, 7–9 Nov, 2 people, train preferred" | researches, proposes 2–3 options with sources, saves them in the workspace |
| "Option 2 — send me the summary file" | sends booking links + checklist and the file |
| "Check prices again for option 2" | re-checks and says when |

### Limits

- **Permission prompts can't be answered from Telegram.** Anything not pre-allowed in
  `~/workspace/.claude/settings.json` (empty by default; the trips example allows WebSearch,
  WebFetch, Read/Edit inside the workspace)
  pauses the session until someone answers in the terminal. If the bot goes quiet, run `shield`
  and look.
- **Slash commands** (`/clear`, `/model`, …) only work in the terminal.
- **Usage counts against your Claude plan**, shared with your other Claude apps.
- **Messages only arrive while the session runs.** It restarts by itself after `/exit` or a
  crash, and after a reboot when Termux is opened (see [USAGE.md](USAGE.md)).

### Giving Claude more power (optional)

To let Claude run shell commands unattended, add rules to `~/workspace/.claude/settings.json`, e.g.
read-only checks:

```json
{
  "permissions": {
    "allow": [
      "WebSearch", "WebFetch", "Read(./**)", "Edit(./**)",
      "Bash(df:*)", "Bash(free:*)", "Bash(uptime)", "Bash(date)", "Bash(ls:*)"
    ]
  }
}
```

Claude runs as **root inside Debian**, and Debian can reach Termux's files. Every rule you add is
something anyone on the allowlist can trigger from Telegram.

## Revoking access

- Telegram: `/revoke` (new token) or `/deletebot` in @BotFather.
- Claude sign-in: `/logout` in Claude Code on the Shield, or remove the device in your Claude
  account settings.
