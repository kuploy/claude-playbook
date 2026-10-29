#!/usr/bin/env python3
"""SessionStart hook (#42): hands the session its notes file, so where the work stands survives a compaction.

On startup, resume and compact, prints the path of ~/.claude/notes/<session_id>.md and what it holds (the last
4,000 characters, so a runaway file can't flood the context). Creates ~/.claude/notes/. Claude Code adds
a SessionStart hook's stdout to the model's context. The session_id is the transcript's, which a compaction keeps.
Also says when the playbook config (#44) is missing or broken, since the guard then blocks no owner-only command.
Before that check it brings the config up to date (#53): on a computer, where the config is a link into the config
repo's clone, it pulls that clone; in the cloud, only when PLAYBOOK_CONFIG_TOKEN is set, it downloads config.json
from the repo named in the pasted copy's config_repo and replaces the pasted copy. If that fails, the pasted copy
stays and the session is told. The token is sent in a header, never printed.
Never blocks: any error prints nothing and exits 0.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

LIMIT = 4000
TOKEN_ENV = "PLAYBOOK_CONFIG_TOKEN"


def config_path():
    return os.environ.get("CLAUDE_PLAYBOOK_CONFIG") or os.path.expanduser("~/.claude/playbook-config.json")   # as guard.py


def refresh_config(path):
    """Brings the config at path up to date. Returns a line to tell the session, or None."""
    if os.path.islink(path):   # a computer: pull the clone the link points into, quietly, as the playbook pull does
        try:
            subprocess.run(["git", "-C", os.path.dirname(os.path.realpath(path)), "pull", "-q", "--ff-only"],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
        return None
    token = os.environ.get(TOKEN_ENV)
    if not token:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            repo = json.load(f).get("config_repo")
    except (OSError, ValueError, AttributeError):
        repo = None
    if not isinstance(repo, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return f"{TOKEN_ENV} is set, but the pasted settings have no config_repo, so the latest settings were not read. Using the pasted copy."
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/config.json"
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"token {token}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            conf = json.loads(r.read(1_000_000))
        if not isinstance(conf, dict):
            raise ValueError("it is not a JSON object")
        conf.setdefault("config_repo", repo)   # so the next session still knows where to look
    except urllib.error.HTTPError as e:
        why = "the token is wrong, expired, or can't read that repo" if e.code in (401, 403, 404) else f"GitHub answered {e.code}"
        return f"The latest settings could not be read from {repo}: {why}. Using the pasted copy. Check {TOKEN_ENV} in the cloud environment."
    except Exception as e:
        why = str(e).replace(token, "***")
        return f"The latest settings could not be read from {repo} ({why}). Using the pasted copy."
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    os.replace(tmp, path)
    return None


def config_problem(path):
    try:
        with open(path, encoding="utf-8") as f:
            conf = json.load(f)
    except FileNotFoundError:
        return f"No playbook config at {path}: owner-only commands are not blocked."
    except (OSError, ValueError) as e:
        return f"The playbook config {path} can't be read ({e}): owner-only commands are not blocked."
    rule = conf.get("owner_only", {}) if isinstance(conf, dict) else None
    if not isinstance(rule, dict) or not isinstance(rule.get("commands", []), list):
        return f"The playbook config {path} has a bad owner_only part: owner-only commands are not blocked."
    for k in ("allow_env", "message"):
        if k in rule and not isinstance(rule[k], str):
            return f"The playbook config {path} has a bad owner_only {k} ({rule[k]!r}): it must be text."
    for c in rule.get("commands", []):
        try:
            re.compile(c["match"])
        except (TypeError, KeyError, re.error):
            return f"The playbook config {path} has a bad owner_only command ({c!r}): it blocks nothing."
        if "only_in" in c and not isinstance(c["only_in"], str):
            return f"The playbook config {path} has a bad only_in ({c!r}): it must be text, so that command is blocked everywhere."
    if not rule.get("commands"):
        return f"The playbook config {path} lists no owner-only commands: none are blocked."
    return None


def main():
    path = config_path()
    try:
        note = refresh_config(path)
    except Exception:   # a failed refresh never hides the check below
        note = None
    if note:
        print(note)
    problem = config_problem(path)
    if problem:
        print(problem + " Setting up: the playbook's docs/how-it-works.md.")
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
