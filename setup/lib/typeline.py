"""Type one line into the foreground Android app via `adb shell input text`.

Usage: typeline.py --file PATH [--chunk N] [--enter]
Reads the line from PATH (so secrets/keys never appear on the command line or in output).
"""
import argparse, subprocess, sys

SPECIAL = set(";&|<>()'\"$\\`*?~#!{}[]")


def escape(s):
    out = []
    for c in s:
        if c == " ":
            out.append("%s")
        elif c in SPECIAL:
            out.append("\\" + c)
        else:
            out.append(c)
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--enter", action="store_true")
    a = ap.parse_args()
    line = open(a.file).read().rstrip("\n")
    if "\n" in line:
        sys.exit("line must not contain newlines")
    pieces = [line] if not a.chunk else [line[i:i + a.chunk] for i in range(0, len(line), a.chunk)]
    for p in pieces:
        r = subprocess.run(["adb", "shell", "input", "text", escape(p)], capture_output=True, text=True)
        if r.returncode != 0 or r.stderr.strip() or r.stdout.strip():
            sys.exit(f"input text failed (rc={r.returncode}): {r.stderr.strip()[:200]} {r.stdout.strip()[:200]}")
    if a.enter:
        subprocess.run(["adb", "shell", "input", "keyevent", "66"], check=True)
    print(f"typed {len(line)} chars in {len(pieces)} chunk(s)")


main()
