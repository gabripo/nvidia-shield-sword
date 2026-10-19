#!/data/data/com.termux/files/usr/bin/python3
"""shield-bot - the one Telegram bot that manages the NVIDIA Shield.

Runs in Termux (Python standard library only). For every message from an
allowlisted user it either:

  1. answers a built-in command instantly (/status, /sh, /termux, /logs, /new, ...),
  2. runs one of YOUR commands: any executable in Debian's ~/workspace/commands/
     becomes /<name> (Claude can create new ones on request), or
  3. hands everything else to Claude Code (`claude -p` in ~/workspace, your
     subscription), continuing the same conversation until /new.

  shield-bot.py --setup            create ~/.config/shield-bot/config.json
  shield-bot.py --run              run the bot (start-shield.sh keeps it running)
  shield-bot.py --selftest "/cmd"  run one built-in or user command locally (no Claude)
"""
import faulthandler
import getpass
import html
import json
import os
import queue
import re
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HOME = os.path.expanduser("~")
PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
CONF_DIR = os.path.join(HOME, ".config", "shield-bot")
CONFIG_PATH = os.path.join(CONF_DIR, "config.json")
STATE_PATH = os.path.join(CONF_DIR, "state.json")
BOOT_DIR = os.path.join(HOME, ".termux", "boot")
LOG_PATH = os.path.join(BOOT_DIR, "shield-bot.log")
START_LOG = os.path.join(BOOT_DIR, "start-shield.log")
ROOTFS = os.path.join(PREFIX, "var/lib/proot-distro/containers/debian/rootfs")
WORKSPACE = "/root/workspace"                       # path inside Debian
COMMANDS_DIR = WORKSPACE + "/commands"              # path inside Debian
DEBIAN_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.bun/bin:/root/.local/bin"
MAX_MSG = 3800                                      # Telegram limit is 4096
NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")

# Use IPv4 only: while the TV sleeps, connections to Telegram's IPv6 address can hang
# until the timeout before Python falls back to IPv4, delaying replies by a minute.
_getaddrinfo = socket.getaddrinfo


def _ipv4_only(host, *args, **kwargs):
    res = _getaddrinfo(host, *args, **kwargs)
    return [r for r in res if r[0] == socket.AF_INET] or res


socket.getaddrinfo = _ipv4_only

BUILTINS = {
    "help": "List commands",
    "status": "Shield status: services, memory, disk, Claude",
    "sh": "Run a shell command in Debian",
    "termux": "Run a shell command in Termux",
    "commands": "List your custom commands",
    "logs": "Recent bot and start logs",
    "new": "Start a new Claude conversation",
    "cancel": "Stop the running Claude request",
}


def log(msg):
    os.makedirs(BOOT_DIR, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(time.strftime("%F %T ") + msg + "\n")


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    old = os.umask(0o077)
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
    finally:
        os.umask(old)
    os.replace(tmp, path)


def load_config():
    cfg = load_json(CONFIG_PATH, None)
    if not cfg:
        sys.exit(f"No config at {CONFIG_PATH} - run: python3 {sys.argv[0]} --setup")
    cfg.setdefault("allow_shell", True)
    cfg.setdefault("shell_timeout", 120)
    cfg.setdefault("command_timeout", 120)
    cfg.setdefault("claude_timeout", 900)
    cfg["allowed_user_ids"] = [int(x) for x in cfg.get("allowed_user_ids", [])]
    return cfg


# ------------------------------------------------------------------ running things

def run(argv, timeout=60, inp=None):
    """Run argv; return (exit code, combined stdout+stderr)."""
    try:
        p = subprocess.run(argv, input=inp, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        out = out.decode(errors="replace") if isinstance(out, bytes) else out
        return 124, out + f"\n[timed out after {timeout}s]"


def debian_argv(cmd):
    return ["proot-distro", "login", "debian", "--", "env", f"PATH={DEBIAN_PATH}", "HOME=/root",
            "TERM=xterm-256color", "bash", "-lc", cmd]


def debian(cmd, timeout=60, inp=None):
    return run(debian_argv(cmd), timeout, inp)


def termux(cmd, timeout=60):
    return run(["bash", "-c", cmd], timeout)


def pre(text, title=""):
    text = text.strip() or "(no output)"
    if len(text) > MAX_MSG - 200:
        text = "...(cut)\n" + text[-(MAX_MSG - 200):]
    head = f"<b>{html.escape(title)}</b>\n" if title else ""
    return f"{head}<pre>{html.escape(text)}</pre>"


# ------------------------------------------------------------------ user commands

def user_commands():
    """{name: description} for executables in Debian's ~/workspace/commands."""
    d = ROOTFS + COMMANDS_DIR
    cmds = {}
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return cmds
    for name in names:
        path = os.path.join(d, name)
        if not NAME_RE.match(name) or name in BUILTINS or not os.path.isfile(path) \
                or not os.access(path, os.X_OK):
            continue
        desc = "Custom command"
        try:
            with open(path, errors="replace") as f:
                for line in f.readlines()[:15]:
                    m = re.match(r"^\s*(#|//|--)\s*description:\s*(.+)$", line, re.I)
                    if m:
                        desc = m.group(2).strip()[:200]
                        break
        except OSError:
            pass
        cmds[name] = desc
    return cmds


def run_user_command(name, arg, cfg):
    try:
        args = shlex.split(arg)
    except ValueError:
        args = [arg] if arg else []
    cmd = f"cd {WORKSPACE} && ./commands/{name} " + " ".join(shlex.quote(a) for a in args)
    code, out = debian(cmd, timeout=cfg["command_timeout"])
    return pre(out, f"/{name}" + (f" {arg}" if arg else "") + f" - exit {code}")


# ------------------------------------------------------------------ built-ins

def b_help(_a, _c):
    lines = ["<b>Shield bot</b>: write normally to talk to Claude, or use a command.", "",
             "<b>Built-in</b>"]
    lines += [f"/{n} - {html.escape(d)}" for n, d in BUILTINS.items()]
    uc = user_commands()
    lines += ["", "<b>Your commands</b>" if uc else
              "<i>No custom commands yet - ask Claude, e.g. \"create a command /plug that ...\"</i>"]
    lines += [f"/{n} - {html.escape(d)}" for n, d in uc.items()]
    return "\n".join(lines)


def b_commands(_a, _c):
    uc = user_commands()
    if not uc:
        return "No custom commands yet. Ask Claude to create one, e.g. \"create a command /ar4k that ...\"."
    return "\n".join(f"/{n} - {html.escape(d)}" for n, d in uc.items())


def b_status(_a, _c):
    lines = ["sshd:    " + ("running" if termux("pgrep -x sshd")[0] == 0 else "not running")]
    sess = debian("tmux has-session -t claude 2>/dev/null")[0] == 0
    lines.append("Claude:  " + ("busy with a request" if CLAUDE.busy() else "idle")
                 + (" · interactive session open" if sess else ""))
    lines.append("Uptime:  " + termux("uptime -p 2>/dev/null || uptime")[1].strip())
    lines.append("Memory:  " + termux(
        "awk '/MemTotal/ {t=$2} /MemAvailable/ {a=$2} END {printf \"%d MB free of %d MB\", a/1024, t/1024}'"
        " /proc/meminfo")[1].strip())
    lines.append("Disk:    " + termux("df -h $HOME | awk 'NR==2 {print $4\" free of \"$2}'")[1].strip())
    lines.append("Commands: " + (", ".join("/" + n for n in user_commands()) or "none"))
    return "<pre>" + html.escape("\n".join(lines)) + "</pre>"


def b_shell(arg, cfg, where):
    if not cfg["allow_shell"]:
        return "Shell commands are disabled (allow_shell is false in the config)."
    if not arg:
        return f"Usage: /{where} &lt;command&gt;"
    fn = debian if where == "sh" else termux
    code, out = fn(arg, timeout=cfg["shell_timeout"])
    return pre(out, ("Debian" if where == "sh" else "Termux") + f" $ {arg[:60]} - exit {code}")


def b_logs(_a, _c):
    return pre(termux(f"tail -n 12 {LOG_PATH} 2>/dev/null; echo; tail -n 6 {START_LOG} 2>/dev/null; true")[1],
               "logs")


def b_new(_a, _c):
    st = load_json(STATE_PATH, {})
    st.pop("claude_session_id", None)
    save_json(STATE_PATH, st)
    return "Started a new conversation: Claude won't remember earlier messages."


def b_cancel(_a, _c):
    return "Stopped the running Claude request." if CLAUDE.cancel() else "No Claude request is running."


HANDLERS = {
    "help": b_help, "start": b_help, "commands": b_commands, "status": b_status,
    "sh": lambda a, c: b_shell(a, c, "sh"), "termux": lambda a, c: b_shell(a, c, "termux"),
    "logs": b_logs, "new": b_new, "cancel": b_cancel,
}


def handle_command(text, cfg):
    """Return reply HTML for a /command, or None if it isn't one we know."""
    name, _, arg = text[1:].partition(" ")
    name = name.split("@", 1)[0].lower()
    arg = arg.strip()
    if name in HANDLERS:
        return HANDLERS[name](arg, cfg)
    if name in user_commands():
        return run_user_command(name, arg, cfg)
    return None


# ------------------------------------------------------------------ Claude

class ClaudeWorker:
    """Runs one Claude request at a time in a background thread."""

    def __init__(self):
        self.q = queue.Queue()
        self.proc = None
        self.lock = threading.Lock()

    def busy(self):
        return self.proc is not None

    def submit(self, bot, chat_id, prompt, cfg):
        ahead = self.q.qsize() + (1 if self.busy() else 0)
        self.q.put((bot, chat_id, prompt, cfg))
        return ahead

    def cancel(self):
        with self.lock:
            p = self.proc
        if not p:
            return False
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except OSError:
            p.terminate()
        return True

    def loop(self):
        while True:
            bot, chat_id, prompt, cfg = self.q.get()
            try:
                self.ask(bot, chat_id, prompt, cfg)
            except Exception as e:
                log(f"claude error: {e!r}")
                bot.send(chat_id, f"Claude failed: {html.escape(repr(e))}")

    def ask(self, bot, chat_id, prompt, cfg, retry=True):
        st = load_json(STATE_PATH, {})
        sid = st.get("claude_session_id")
        cmd = f"mkdir -p {WORKSPACE} && cd {WORKSPACE} && claude -p --output-format json --permission-mode dontAsk"
        if sid:
            cmd += f" --resume {shlex.quote(sid)}"
        with self.lock:
            self.proc = subprocess.Popen(debian_argv(cmd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, start_new_session=True)
        proc = self.proc
        result = {}
        done = threading.Event()

        def communicate():
            try:
                result["out"], result["err"] = proc.communicate(prompt, timeout=cfg["claude_timeout"])
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                result["out"], result["err"] = proc.communicate()
                result["timeout"] = True
            done.set()

        threading.Thread(target=communicate, daemon=True).start()
        while not done.wait(5):
            bot.action(chat_id)
        with self.lock:
            self.proc = None

        if result.get("timeout"):
            bot.send(chat_id, f"Claude took longer than {cfg['claude_timeout']} s and was stopped.")
            return
        if proc.returncode in (-signal.SIGTERM, 143) and not result.get("out"):
            return  # cancelled; /cancel already replied
        try:
            data = json.loads(result["out"])
        except (json.JSONDecodeError, TypeError):
            err = (result.get("err") or result.get("out") or "").strip()
            if sid and retry and ("session" in err.lower() or "resume" in err.lower()):
                st.pop("claude_session_id", None)
                save_json(STATE_PATH, st)
                return self.ask(bot, chat_id, prompt, cfg, retry=False)
            bot.send(chat_id, pre(err[-1500:] or f"exit {proc.returncode}", "Claude failed"))
            return
        if data.get("session_id"):
            st["claude_session_id"] = data["session_id"]
            save_json(STATE_PATH, st)
        text = (data.get("result") or "").strip() or "(Claude returned no text)"
        files = re.findall(r"^SEND_FILE:\s*(\S+)\s*$", text, re.M)
        text = re.sub(r"^SEND_FILE:\s*\S+\s*$\n?", "", text, flags=re.M).strip()
        if data.get("is_error"):
            text = "⚠️ " + text
        bot.send_plain(chat_id, text or "(file attached)")
        for path in files:
            bot.send_file(chat_id, path)


CLAUDE = ClaudeWorker()


# ------------------------------------------------------------------ Telegram

class Bot:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, http_timeout=70, **params):
        data = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (list, dict)) else v
                                       for k, v in params.items()}).encode()
        # http_timeout is the network timeout; a `timeout` in params is Telegram's long-poll time.
        with urllib.request.urlopen(urllib.request.Request(self.base + method, data=data),
                                    timeout=http_timeout) as r:
            res = json.load(r)
        if not res.get("ok"):
            raise RuntimeError(f"{method}: {res.get('description')}")
        return res["result"]

    def call_retry(self, method, **params):
        """For replies: short network timeout and one retry, so a stalled connection
        never delays an answer for long."""
        try:
            return self.call(method, http_timeout=20, **params)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if isinstance(e, urllib.error.HTTPError):
                raise
            log(f"{method} failed ({e!r}), retrying once")
            return self.call(method, http_timeout=20, **params)

    def action(self, chat_id):
        try:
            self.call("sendChatAction", chat_id=chat_id, action="typing", http_timeout=10)
        except Exception:
            pass

    def send(self, chat_id, text_html):
        try:
            self.call_retry("sendMessage", chat_id=chat_id, text=text_html, parse_mode="HTML",
                            disable_web_page_preview="true")
        except Exception as e:
            log(f"sendMessage(HTML) failed: {e!r}")
            self.send_plain(chat_id, re.sub(r"<[^>]+>", "", html.unescape(text_html)))

    def send_plain(self, chat_id, text):
        for i in range(0, max(len(text), 1), MAX_MSG):
            self.call_retry("sendMessage", chat_id=chat_id, text=text[i:i + MAX_MSG],
                            disable_web_page_preview="true")

    def send_file(self, chat_id, debian_path):
        if not debian_path.startswith("/"):
            debian_path = WORKSPACE + "/" + debian_path
        local = ROOTFS + debian_path
        if not os.path.isfile(local):
            self.send_plain(chat_id, f"(file not found: {debian_path})")
            return
        if os.path.getsize(local) > 45 * 1024 * 1024:
            self.send_plain(chat_id, f"(file too large for Telegram: {debian_path})")
            return
        boundary = uuid.uuid4().hex
        with open(local, "rb") as f:
            content = f.read()
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
                f"filename=\"{os.path.basename(local)}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + "sendDocument", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            json.load(r)

    def set_commands(self, cmds):
        menu = [{"command": n, "description": d[:250]} for n, d in BUILTINS.items()]
        menu += [{"command": n, "description": d[:250]} for n, d in cmds.items()]
        self.call("setMyCommands", commands=menu[:100])


def run_bot():
    cfg = load_config()
    # `kill -USR1 <pid>` writes every thread's stack to shield-bot.err (for debugging hangs).
    faulthandler.register(signal.SIGUSR1, file=open(os.path.join(BOOT_DIR, "shield-bot.err"), "a"),
                          all_threads=True)
    bot = Bot(cfg["token"])
    me = bot.call("getMe")
    log(f"started as @{me['username']}, allowed users {cfg['allowed_user_ids']}")
    threading.Thread(target=CLAUDE.loop, daemon=True).start()
    menu = user_commands()
    bot.set_commands(menu)
    # Drop messages sent while the bot was offline: never replay old commands.
    pending = bot.call("getUpdates", offset=-1, timeout=0)
    offset = pending[-1]["update_id"] + 1 if pending else 0
    backoff = 5
    while True:
        try:
            updates = bot.call("getUpdates", offset=offset, timeout=50, allowed_updates=["message"])
            backoff = 5
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Another program is reading this bot's messages (e.g. a leftover Claude
                # Telegram channel plugin). Retry quickly so we don't fall behind.
                log("getUpdates conflict (409): another program is polling this bot; retrying in 2s")
                time.sleep(2)
                continue
            log(f"getUpdates failed: {e!r}; retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as e:
            log(f"getUpdates failed: {e!r}; retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        current = user_commands()
        if current != menu:                      # Claude (or you) added/removed a command
            menu = current
            try:
                bot.set_commands(menu)
            except Exception as e:
                log(f"setMyCommands failed: {e!r}")
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            user = (msg.get("from") or {}).get("id")
            chat = msg.get("chat") or {}
            if user not in cfg["allowed_user_ids"] or chat.get("type") != "private":
                log(f"ignored message from user {user} (chat {chat.get('type')})")
                continue
            text = (msg.get("text") or msg.get("caption") or "").strip()
            if not text:
                bot.send_plain(chat["id"], "Only text messages are supported for now.")
                continue
            threading.Thread(target=dispatch, args=(bot, chat["id"], text, cfg), daemon=True).start()


def dispatch(bot, chat_id, text, cfg):
    try:
        if text.startswith("/"):
            log(f"command {text.split(' ', 1)[0][:40]}")
            bot.action(chat_id)
            reply = handle_command(text, cfg)
            if reply is not None:
                bot.send(chat_id, reply)
                log("replied")
                return
            # Unknown /command: let Claude handle it (e.g. "/ar4k" before it exists).
        log("to Claude")
        ahead = CLAUDE.submit(bot, chat_id, text, cfg)
        if ahead:
            bot.send_plain(chat_id, f"Queued for Claude ({ahead} request(s) ahead). /cancel stops the current one.")
    except Exception as e:
        log(f"dispatch error: {e!r}")
        bot.send_plain(chat_id, f"Error: {e!r}")


# ------------------------------------------------------------------ setup

def setup():
    print("shield-bot setup")
    # Reuse the Claude channel plugin's bot if there is one: one bot for everything.
    old_env = ROOTFS + "/root/.claude/channels/telegram/.env"
    token = ""
    if os.path.isfile(old_env):
        with open(old_env) as f:
            m = re.search(r"^TELEGRAM_BOT_TOKEN=(\S+)", f.read(), re.M)
        if m and input("Use the existing Claude Telegram bot's token? [Y/n]: ").strip().lower() not in ("n", "no"):
            token = m.group(1)
    if not token:
        token = getpass.getpass("Bot token from @BotFather (input hidden): ").strip()
    try:
        me = Bot(token).call("getMe", http_timeout=15)
    except Exception as e:
        sys.exit(f"Token rejected by Telegram: {e}")
    print(f"Bot: @{me['username']}")
    ids = []
    access = load_json(ROOTFS + "/root/.claude/channels/telegram/access.json", {})
    default_ids = [int(x) for x in access.get("allowFrom", []) if str(x).isdigit()]
    hint = f" [{','.join(map(str, default_ids))}]" if default_ids else ""
    ans = input(f"Allowed Telegram user IDs, comma-separated{hint}: ").strip()
    ids = [int(x) for x in ans.split(",") if x.strip()] if ans else default_ids
    if not ids:
        sys.exit("At least one user ID is needed (message @userinfobot in Telegram to get yours).")
    shell = input("Allow /sh and /termux shell commands? [Y/n]: ").strip().lower() not in ("n", "no")
    save_json(CONFIG_PATH, {"token": token, "allowed_user_ids": ids, "allow_shell": shell,
                            "shell_timeout": 120, "command_timeout": 120, "claude_timeout": 900})
    os.chmod(CONFIG_PATH, 0o600)
    print(f"Saved {CONFIG_PATH} (mode 600).")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "--help"
    if arg == "--setup":
        setup()
    elif arg == "--run":
        run_bot()
    elif arg == "--selftest":
        cfg = load_json(CONFIG_PATH, None) and load_config() or \
            {"allow_shell": True, "shell_timeout": 60, "command_timeout": 60, "allowed_user_ids": []}
        text = " ".join(sys.argv[2:])
        reply = handle_command(text, cfg) if text.startswith("/") else None
        print(html.unescape(re.sub(r"<[^>]+>", "", reply)) if reply is not None else "(would go to Claude)")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
