#!/usr/bin/env python3
"""SessionStart hook (#42): hands the session its notes file, so where the work stands survives a compaction.

On startup, resume and compact, prints the path of ~/.claude/notes/<session_id>.md and what it holds (the last
4,000 characters, so a runaway file can't flood the context). Creates ~/.claude/notes/. Claude Code adds
a SessionStart hook's stdout to the model's context. The session_id is the transcript's, which a compaction keeps.
Never blocks: any error prints nothing and exits 0.
"""
import json
import os
import re
import sys

LIMIT = 4000


def main():
    sid = json.load(sys.stdin).get("session_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        return
    path = os.path.expanduser(f"~/.claude/notes/{sid}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except FileNotFoundError:
        text = ""
    print(f"Your notes file is {path}. Keep it current (account rules, \"Notes file\").")
    if len(text) > LIMIT:
        print(f"It is long; here are its last {LIMIT} characters:\n\n" + text[-LIMIT:])
    elif text:
        print("It holds:\n\n" + text)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
