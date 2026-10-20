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
    "memory": "Claude memory: on (follow-ups continue the conversation) or off",
}
MENU_BUILTINS = ("help",)    # the other built-ins work when typed or tapped, but stay out of the menu


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
    cfg.setdefault("claude_idle", 900)          # close the warm Claude process after 15 idle minutes
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


_MENU_CACHE = {}   # command name -> (mtime key, [shortcuts]) for "# menu: dynamic" commands
_HIDDEN_SHORTCUTS = []   # shortcuts kept out of the menu, as of the last menu_shortcuts()


def _header(path, lines=25):
    try:
        with open(path, errors="replace") as f:
            return f.readlines()[:lines]
    except OSError:
        return []


def menu_shortcuts():
    """Menu shortcuts declared by user commands: [(shortcut, command, args, description)].

    In a command's first lines:
      # menu: <shortcut> <args...> | <description>    a static shortcut (repeatable)
      # shortcut: <shortcut> <args...> | <description>  the same, but not listed in the menu
                                                      (e.g. reached through buttons)
      # menu: dynamic                                 run `<command> --menu` for the list
      # menu-depends: <path>                          re-run --menu when that file changes
    `--menu` prints one shortcut per line: shortcut<TAB>args<TAB>description[<TAB>hidden]
    ("hidden" = like "# shortcut:", kept out of the menu).
    """
    base = ROOTFS + COMMANDS_DIR
    taken = set(BUILTINS) | set(user_commands())
    out, hidden = [], set()
    for name in user_commands():
        path = os.path.join(base, name)
        head = _header(path)
        entries, dynamic, depends = [], False, []
        for line in head:
            m = re.match(r"^\s*(?:#|//|--)\s*(menu|shortcut):\s*(.+)$", line, re.I)
            if m:
                spec = m.group(2).strip()
                if spec.lower() == "dynamic":
                    dynamic = True
                else:
                    left, _, desc = spec.partition("|")
                    parts = left.split()
                    if parts:
                        entries.append((parts[0], " ".join(parts[1:]), desc.strip(),
                                        m.group(1).lower() == "shortcut"))
            m = re.match(r"^\s*(?:#|//|--)\s*menu-depends:\s*(\S+)", line, re.I)
            if m:
                depends.append(m.group(1))
        if dynamic:
            key = []
            for f in [path] + [ROOTFS + (d if d.startswith("/") else f"{WORKSPACE}/{d}") for d in depends]:
                try:
                    key.append(os.path.getmtime(f))
                except OSError:
                    key.append(0)
            cached = _MENU_CACHE.get(name)
            if not cached or cached[0] != key:
                code, text = debian(f"cd {WORKSPACE} && ./commands/{name} --menu", timeout=30)
                found = []
                for row in text.splitlines() if code == 0 else []:
                    cols = row.split("\t")
                    if len(cols) >= 2:
                        found.append((cols[0].strip(), cols[1].strip(), cols[2].strip() if len(cols) > 2 else "",
                                      len(cols) > 3 and cols[3].strip().lower() == "hidden"))
                _MENU_CACHE[name] = cached = (key, found)
            entries += cached[1]
        for short, args, desc, hide in entries:
            short = short.lower()
            if NAME_RE.match(short) and short not in taken:
                taken.add(short)
                out.append((short, name, args, desc or f"/{name} {args}"))
                if hide:
                    hidden.add(short)
    _HIDDEN_SHORTCUTS[:] = sorted(hidden)
    return out


def _flagged(flag):
    """User commands with "# <flag>: yes" in their first lines."""
    found = set()
    for name in user_commands():
        for line in _header(os.path.join(ROOTFS + COMMANDS_DIR, name)):
            if re.match(r"^\s*(?:#|//|--)\s*" + flag + r":\s*(yes|true|1)\b", line, re.I):
                found.add(name)
    return found


def shortcuts_only():
    """Commands with "# shortcuts-only: yes": usable only through their menu shortcuts (no typed
    arguments with spaces, not even the bare command); not listed themselves."""
    return _flagged("shortcuts-only")


def hidden_shortcuts():
    """Shortcuts declared with "# shortcut:" or generated as "hidden" (usable, not listed in
    Telegram's menu)."""
    menu_shortcuts()
    return set(_HIDDEN_SHORTCUTS)


def menu_hidden():
    """Commands and shortcuts not listed in Telegram's menu: "# menu-hide: yes" (still usable
    when typed), all shortcuts-only commands, and "# shortcut:" entries."""
    return _flagged("menu-hide") | shortcuts_only() | hidden_shortcuts()


class Reply(str):
    """Reply HTML that may carry inline buttons: [(label, callback_data)]."""
    buttons = ()


BUTTON_RE = re.compile(r"^BUTTON:\s*(/[a-z0-9_]{1,32})\s*\|\s*([^|\n]+?)\s*(\|\s*confirm\s*)?$", re.M | re.I)


def run_user_command(name, arg, cfg, label=None):
    try:
        args = shlex.split(arg)
    except ValueError:
        args = [arg] if arg else []
    cmd = f"cd {WORKSPACE} && ./commands/{name} " + " ".join(shlex.quote(a) for a in args)
    code, out = debian(cmd, timeout=cfg["command_timeout"])
    # "BUTTON: /command | Label [| confirm]" lines become buttons under the reply; "confirm"
    # asks "are you sure?" before running (for shutdowns and the like).
    buttons = [(m.group(2), ("?" if m.group(3) else "") + m.group(1).lower())
               for m in BUTTON_RE.finditer(out)]
    reply = Reply(pre(BUTTON_RE.sub("", out).strip(),
                      (label or f"/{name}" + (f" {arg}" if arg else "")) + f" - exit {code}"))
    reply.buttons = buttons
    return reply


# ------------------------------------------------------------------ built-ins

def b_help(_a, _c):
    lines = ["<b>Shield bot</b>: write normally to talk to Claude, or use a command.", "",
             "<b>Built-in</b>"]
    lines += [f"/{n} - {html.escape(d)}" for n, d in BUILTINS.items()]
    uc = user_commands()
    lines += ["", "<b>Your commands</b>" if uc else
              "<i>No custom commands yet - ask Claude, e.g. \"create a command /plug that ...\"</i>"]
    lines += _command_lines(uc)
    return "\n".join(lines)


def b_commands(_a, _c):
    uc = user_commands()
    if not uc:
        return "No custom commands yet. Ask Claude to create one, e.g. \"create a command /ar4k that ...\"."
    return "\n".join(_command_lines(uc))


def _command_lines(uc):
    """Each user command, followed by its menu shortcuts (indented)."""
    shortcuts, only = menu_shortcuts(), shortcuts_only()
    lines = []
    for n, d in uc.items():
        if n in only:                     # list just the shortcuts
            lines += [f"/{sc} - {html.escape(desc)}" for sc, base, _a, desc in shortcuts if base == n]
            continue
        lines.append(f"/{n} - {html.escape(d)}")
        lines += [f"   /{sc} - {html.escape(desc)}" for sc, base, _a, desc in shortcuts if base == n]
    return lines


def b_status(_a, _c):
    lines = ["sshd:    " + ("running" if termux("pgrep -x sshd")[0] == 0 else "not running")]
    sess = debian("tmux has-session -t claude 2>/dev/null")[0] == 0
    lines.append("Claude:  " + ("busy with a request" if CLAUDE.busy() else
                                ("idle, warm (fast replies)" if CLAUDE.warm() else "idle, not loaded"))
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


def memory_on():
    return load_json(STATE_PATH, {}).get("claude_memory", True)


def conversation_buttons():
    """Buttons for a Claude conversation. They run commands, so they keep working on old
    messages: /cancel stops whatever request is running, /new ends the conversation."""
    return [("⏹ Cancel request", "/cancel"), ("🆕 End conversation", "/new"),
            ("🧠 Memory: on - turn off", "/memory off") if memory_on()
            else ("🧠 Memory: off - turn on", "/memory on")]


def b_new(_a, _c):
    if not CLAUDE.cancel():                  # a running request is stopped first
        CLAUDE.stop("new conversation")
    st = load_json(STATE_PATH, {})
    st.pop("claude_session_id", None)
    save_json(STATE_PATH, st)
    return "Conversation ended: your next message starts a new one."


def b_memory(arg, _c):
    arg = arg.lower()
    if arg in ("on", "off"):
        st = load_json(STATE_PATH, {})
        st["claude_memory"] = arg == "on"
        save_json(STATE_PATH, st)
    reply = Reply("Claude memory: <b>on</b> - follow-up messages continue the conversation."
                  if memory_on() else
                  "Claude memory: <b>off</b> - every message starts a new conversation.")
    reply.buttons = [conversation_buttons()[2]]
    return reply


def b_cancel(_a, _c):
    return "Stopped the running Claude request." if CLAUDE.cancel() else "No Claude request is running."


HANDLERS = {
    "help": b_help, "start": b_help, "commands": b_commands, "status": b_status,
    "sh": lambda a, c: b_shell(a, c, "sh"), "termux": lambda a, c: b_shell(a, c, "termux"),
    "logs": b_logs, "new": b_new, "cancel": b_cancel, "memory": b_memory,
}


def handle_command(text, cfg):
    """Return reply HTML for a /command, or None if it isn't one we know."""
    name, _, arg = text[1:].partition(" ")
    name = name.split("@", 1)[0].lower()
    arg = arg.strip()
    if name in HANDLERS:
        return HANDLERS[name](arg, cfg)
    only = shortcuts_only()
    if name in user_commands() and name not in only:
        return run_user_command(name, arg, cfg)
    for short, base, args, _desc in menu_shortcuts():      # e.g. /plug_pc_cycle -> plug pc cycle
        if short == name:
            # Shortcuts of shortcuts-only commands take no extra words.
            if base in only:
                return run_user_command(base, args, cfg, label=f"/{short}")
            return run_user_command(base, (args + " " + arg).strip(), cfg, label=f"/{short}" + (f" {arg}" if arg else ""))
    if name in only:
        return "Use the menu entries for this command: " + " ".join(
            f"/{sc}" for sc, base, _a, _d in menu_shortcuts() if base == name)
    return None


# ------------------------------------------------------------------ Claude

class ClaudeWorker:
    """Keeps ONE Claude Code process running between messages ("warm Claude").

    Claude runs in streaming mode (stream-json in/out): the first message pays the
    ~15 s startup, later ones answer in seconds and continue the same conversation.
    The process is closed after `claude_idle` seconds without requests (default 900)
    to give the RAM back, and restarted on demand with --resume. One request at a time.
    """

    def __init__(self):
        self.q = queue.Queue()
        self.proc = None
        self.events = None          # queue of parsed stdout messages (None = process ended)
        self.lock = threading.Lock()
        self.working = False
        self.cancelled = False
        self.last_used = 0.0

    def busy(self):
        return self.working

    def warm(self):
        return self.proc is not None and self.proc.poll() is None

    def submit(self, bot, chat_id, prompt, cfg):
        ahead = self.q.qsize() + (1 if self.working else 0)
        self.q.put((bot, chat_id, prompt, cfg))
        return ahead

    # -- process management
    def _start(self, cfg):
        sid = load_json(STATE_PATH, {}).get("claude_session_id")
        cmd = (f"mkdir -p {WORKSPACE} && cd {WORKSPACE} && exec claude -p --input-format stream-json "
               "--output-format stream-json --verbose --permission-mode dontAsk")
        if sid:
            cmd += f" --resume {shlex.quote(sid)}"
        proc = subprocess.Popen(debian_argv(cmd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True)
        events = queue.Queue()
        stderr_tail = []

        def read_stdout():
            for line in proc.stdout:
                try:
                    events.put(json.loads(line))
                except json.JSONDecodeError:
                    pass
            events.put(None)

        def read_stderr():
            for line in proc.stderr:
                stderr_tail.append(line)
                del stderr_tail[:-20]

        threading.Thread(target=read_stdout, daemon=True).start()
        threading.Thread(target=read_stderr, daemon=True).start()
        proc.stderr_tail = stderr_tail
        proc.resumed = bool(sid)            # first answer of a resumed session gets a sanity check
        self.proc, self.events = proc, events
        log(f"Claude process started (pid {proc.pid}{', resuming' if sid else ''})")

    def stop(self, reason=""):
        with self.lock:
            p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                p.terminate()
            log(f"Claude process stopped{': ' + reason if reason else ''}")

    def forget(self):
        """Drop the conversation: the next request starts a new one."""
        self.stop("memory off")
        st = load_json(STATE_PATH, {})
        st.pop("claude_session_id", None)
        save_json(STATE_PATH, st)

    def cancel(self):
        if not self.working:
            return False
        self.cancelled = True
        self.stop("cancelled")
        return True

    def reap_idle(self, idle_seconds):
        """Background thread: close the warm process when it hasn't been used for a while."""
        while True:
            time.sleep(60)
            if self.warm() and not self.working and time.time() - self.last_used > idle_seconds:
                self.stop(f"idle for {idle_seconds // 60} min")

    def loop(self, cfg):
        threading.Thread(target=self.reap_idle, args=(cfg["claude_idle"],), daemon=True).start()
        while True:
            bot, chat_id, prompt, cfg = self.q.get()
            self.working, self.cancelled = True, False
            try:
                if not memory_on() and load_json(STATE_PATH, {}).get("claude_session_id"):
                    self.forget()                        # memory off: every message is a new conversation
                if not load_json(STATE_PATH, {}).get("claude_session_id"):
                    bot.send(chat_id, "💬 <b>New Claude conversation</b>" + (
                        "\nFollow-up messages continue it until you end it." if memory_on() else
                        "\nMemory is off: each message is answered on its own."),
                        conversation_buttons())
                self.ask(bot, chat_id, prompt, cfg)
            except Exception as e:
                log(f"claude error: {e!r}")
                bot.send(chat_id, f"Claude failed: {html.escape(repr(e))}")
            finally:
                self.working = False
                self.last_used = time.time()
            if not memory_on() and not self.cancelled:
                # Memory off: drop this conversation now and start a fresh process in the
                # background, so the next message is still answered quickly.
                self.forget()
                try:
                    self._start(cfg)
                except Exception as e:
                    log(f"Claude prestart failed: {e!r}")

    # -- one request
    def ask(self, bot, chat_id, prompt, cfg, retry=True, note=""):
        if not self.warm():
            self._start(cfg)
        proc, events = self.proc, self.events
        try:
            proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.stop("stdin closed")
            if retry:
                return self.ask(bot, chat_id, prompt, cfg, retry=False)
            raise
        deadline = time.time() + cfg["claude_timeout"]
        result = None
        while result is None:
            if time.time() > deadline:
                self.stop("timeout")
                bot.send(chat_id, f"Claude took longer than {cfg['claude_timeout']} s and was stopped.")
                return
            try:
                msg = events.get(timeout=5)
            except queue.Empty:
                bot.action(chat_id)
                continue
            if msg is None:                                    # process ended
                if self.cancelled:
                    return                                     # /cancel already replied
                err = "".join(getattr(proc, "stderr_tail", [])).strip()
                self.stop("exited")
                st = load_json(STATE_PATH, {})
                if retry and st.get("claude_session_id") and ("session" in err.lower() or "resume" in err.lower()):
                    st.pop("claude_session_id", None)          # stale session id: start fresh
                    save_json(STATE_PATH, st)
                    return self.ask(bot, chat_id, prompt, cfg, retry=False)
                bot.send(chat_id, pre(err[-1500:] or f"exit {proc.returncode}", "Claude stopped unexpectedly"))
                return
            if msg.get("type") == "result":
                result = msg
        if getattr(proc, "resumed", False):
            proc.resumed = False
            if retry and (result.get("is_error") or not (result.get("result") or "").strip()):
                # A conversation interrupted mid-task (e.g. by /cancel) can't always be resumed:
                # start a new one and ask again.
                log(f"resumed session gave an empty/error result ({result.get('subtype')}); starting fresh")
                self.stop("resume failed")
                st = load_json(STATE_PATH, {})
                st.pop("claude_session_id", None)
                save_json(STATE_PATH, st)
                return self.ask(bot, chat_id, "(The previous conversation was interrupted.) " + prompt, cfg,
                                retry=False, note="(Started a new conversation: the previous one was interrupted.)\n\n")
        if result.get("session_id"):
            st = load_json(STATE_PATH, {})
            st["claude_session_id"] = result["session_id"]
            save_json(STATE_PATH, st)
        text = (result.get("result") or "").strip() or "(Claude returned no text)"
        files = re.findall(r"^SEND_FILE:\s*(\S+)\s*$", text, re.M)
        text = re.sub(r"^SEND_FILE:\s*\S+\s*$\n?", "", text, flags=re.M).strip()
        if result.get("is_error"):
            text = "⚠️ " + text
        bot.send_plain(chat_id, note + (text or "(file attached)"))
        for path in files:
            bot.send_file(chat_id, path)
        log(f"Claude replied ({len(text)} chars, {len(files)} file(s), {result.get('num_turns', '?')} turns, "
            f"{result.get('subtype', '?')})")


CLAUDE = ClaudeWorker()


# ------------------------------------------------------------------ maintenance

CLEANUP_DEBIAN = ("apt-get clean; rm -rf /var/lib/apt/lists/*; "
                  "find /root/.claude/projects -name '*.jsonl' -mtime +30 -delete 2>/dev/null; "
                  f"find {WORKSPACE}/screenshots -type f -mtime +1 -delete 2>/dev/null; true")
CLEANUP_TERMUX = "apt-get clean 2>/dev/null; true"


def maintenance():
    """Daily cleanup (10 min after start, then every 24 h): apt caches and package lists,
    Claude transcripts older than 30 days, screenshots older than a day."""
    time.sleep(600)
    while True:
        if not CLAUDE.busy():
            before = termux("df -k $HOME | awk 'NR==2 {print $4}'")[1].strip()
            debian(CLEANUP_DEBIAN, timeout=300)
            termux(CLEANUP_TERMUX, timeout=120)
            after = termux("df -k $HOME | awk 'NR==2 {print $4}'")[1].strip()
            try:
                log(f"daily cleanup done, freed {(int(after) - int(before)) // 1024} MB")
            except ValueError:
                log("daily cleanup done")
        time.sleep(24 * 3600)


# ------------------------------------------------------------------ Telegram

def keyboard(buttons, per_row=2):
    """Telegram inline keyboard from [(label, callback_data)]."""
    rows = [[{"text": t[:60], "callback_data": d[:64]} for t, d in buttons[i:i + per_row]]
            for i in range(0, len(buttons), per_row)]
    return {"inline_keyboard": rows}


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

    def send(self, chat_id, text_html, buttons=()):
        extra = {"reply_markup": keyboard(buttons)} if buttons else {}
        try:
            self.call_retry("sendMessage", chat_id=chat_id, text=text_html, parse_mode="HTML",
                            disable_web_page_preview="true", **extra)
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
        with open(local, "rb") as f:
            content = f.read()
        name = os.path.basename(local)
        # Images go out as photos (shown inline); Telegram rejects photos over 10 MB or with
        # extreme proportions, so fall back to sending the file as a document.
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and len(content) < 10 * 1024 * 1024:
            try:
                return self._upload("sendPhoto", "photo", chat_id, name, content)
            except Exception as e:
                log(f"sendPhoto failed for {name} ({e!r}), sending as document")
        self._upload("sendDocument", "document", chat_id, name, content)

    def _upload(self, method, field, chat_id, name, content):
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
                f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + method, data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.load(r)
        if not res.get("ok"):
            raise RuntimeError(f"{method}: {res.get('description')}")

    def set_commands(self, cmds, shortcuts=(), hidden=()):
        """Telegram's command menu: /help, then each user command with its shortcuts.

        Set for the default scope AND for all private chats: Telegram prefers the more specific
        scope, so a list left there by another program (e.g. Claude Code's Telegram channel
        plugin sets /start /help /status) would otherwise hide ours.
        """
        menu = [{"command": n, "description": BUILTINS[n][:250]} for n in MENU_BUILTINS]
        for n, d in cmds.items():
            if n not in hidden:
                menu.append({"command": n, "description": d[:250]})
            menu += [{"command": sc, "description": desc[:250]}
                     for sc, base, _a, desc in shortcuts if base == n and sc not in hidden]
        if len(menu) > 100:
            log(f"command menu has {len(menu)} entries; Telegram shows the first 100")
        for scope in ({"type": "default"}, {"type": "all_private_chats"}):
            self.call("setMyCommands", commands=menu[:100], scope=scope)


def run_bot():
    cfg = load_config()
    # `kill -USR1 <pid>` writes every thread's stack to stderr, which start-shield.sh
    # appends to shield-bot.err (for debugging hangs).
    faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True)
    bot = Bot(cfg["token"])
    me = bot.call("getMe")
    log(f"started as @{me['username']}, allowed users {cfg['allowed_user_ids']}")
    threading.Thread(target=CLAUDE.loop, args=(cfg,), daemon=True).start()
    threading.Thread(target=maintenance, daemon=True).start()
    menu = (user_commands(), menu_shortcuts(), menu_hidden())
    bot.set_commands(*menu)
    # Drop messages sent while the bot was offline: never replay old commands.
    pending = bot.call("getUpdates", offset=-1, timeout=0)
    offset = pending[-1]["update_id"] + 1 if pending else 0
    backoff = 5
    while True:
        try:
            updates = bot.call("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
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
        current = (user_commands(), menu_shortcuts(), menu_hidden())
        if current != menu:                      # Claude (or you) changed commands or their shortcuts
            menu = current
            try:
                bot.set_commands(*menu)
            except Exception as e:
                log(f"setMyCommands failed: {e!r}")
        for u in updates:
            offset = u["update_id"] + 1
            if "callback_query" in u:                # a tap on one of our buttons
                cq = u["callback_query"]
                chat = (cq.get("message") or {}).get("chat") or {}
                if (cq.get("from") or {}).get("id") not in cfg["allowed_user_ids"] \
                        or chat.get("type") != "private":
                    log(f"ignored button from user {(cq.get('from') or {}).get('id')}")
                    continue
                threading.Thread(target=on_button, args=(bot, cq, cfg), daemon=True).start()
                continue
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
                bot.send(chat_id, reply, getattr(reply, "buttons", ()))
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


def on_button(bot, cq, cfg):
    """Button taps. Data is a command ("/pc_on"); "?/cmd" asks for confirmation first, "!/cmd"
    is the confirmed command, "x" cancels. Buttons only ever run commands, never Claude."""
    data, msg = cq.get("data") or "", cq.get("message") or {}
    chat_id, msg_id = msg["chat"]["id"], msg.get("message_id")
    label = next((b["text"] for row in (msg.get("reply_markup") or {}).get("inline_keyboard", [])
                  for b in row if b.get("callback_data") == data), data)
    try:
        bot.call("answerCallbackQuery", callback_query_id=cq["id"], http_timeout=10,
                 **({"text": "Cancelled"} if data == "x" else {}))
        if data.startswith(("!", "x")):          # answered: remove the Yes/Cancel buttons
            bot.call("editMessageReplyMarkup", chat_id=chat_id, message_id=msg_id, http_timeout=10,
                     reply_markup={"inline_keyboard": []})
    except Exception as e:
        log(f"button ack failed: {e!r}")
    if data == "x":
        return
    if data.startswith("?"):
        bot.send(chat_id, f"<b>{html.escape(label)}</b>: are you sure?",
                 [("Yes, " + label[0].lower() + label[1:], "!" + data[1:]), ("Cancel", "x")])
        return
    text = data.lstrip("!")
    if not text.startswith("/"):
        return
    log(f"button {text[:40]}")
    bot.action(chat_id)
    try:
        reply = handle_command(text, cfg)
        bot.send(chat_id, reply if reply is not None else f"Unknown command {html.escape(text)}",
                 getattr(reply, "buttons", ()))
        log("replied")
    except Exception as e:
        log(f"button error: {e!r}")
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
