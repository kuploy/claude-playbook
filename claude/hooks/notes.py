#!/usr/bin/env python3
"""SessionStart hook (#42): hands the session its notes file, so where the work stands survives a compaction.

On startup, resume and compact, prints the path of ~/.claude/notes/<session_id>.md and what it holds (the last
4,000 characters, so a runaway file can't flood the context). Creates ~/.claude/notes/. Claude Code adds
a SessionStart hook's stdout to the model's context. The session_id is the transcript's, which a compaction keeps.

Two more modes warn before a compaction (#59):

`--stop`, a Stop hook. When the session re-sends more than WARN_AT of the auto-compact window and its notes
file is missing or over STALE_MINUTES old, it returns `hookSpecificOutput.additionalContext` once with the
numbers, and the session rewrites the file before the turn ends. That field, not `decision: block`: the
reference keeps it for a hook "working as designed and giving Claude guidance", with the same loop
protections, and the transcript shows it as feedback instead of a hook error in front of the owner.
The warning rides a Stop hook because that is the only place a message reaches the model: a PreCompact
hook's stderr goes to the user, on `manual` only, and its `systemMessage` is
discarded (hooks reference, PreCompact). Context size comes from the transcript's last reply: the reference
adds up input, cache-read, cache-creation and output tokens for `context_tokens`, and so does this. The window
is read from CLAUDE_CODE_AUTO_COMPACT_WINDOW, then from the settings files. When none of them sets it, the
hook says nothing at all, because then Claude Code's own default decides, and that default is the model's
context limit: about 967K on Sonnet 5 and the other 1M models, 200K on Sonnet 4.6 and Opus 4.6, and whatever
is assumed for a model ID it doesn't recognise (model-config, "Default auto-compact thresholds"). A guess
would nag from 160K in a session with 800K to spare. A window saved per model with /autocompact also wins
over both and can't be read, so a number that is set can still be wrong; being set is the signal that
somebody chose it.
Never traps a session: it says nothing when Claude Code is already continuing from a Stop block, and at most
once every COOLDOWN_MINUTES.

`--pre-compact`, a PreCompact hook. It never blocks: blocking a proactive compaction leaves the context
growing, and blocking one that recovers from a context-limit error fails the request (hooks reference).
All it does is mark the notes file, so the SessionStart that follows shows the session which lines predate
the compaction.
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
import time
import urllib.error
import urllib.request

LIMIT = 4000
TOKEN_ENV = "PLAYBOOK_CONFIG_TOKEN"
WINDOW_ENV = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
WARN_AT = 0.8              # share of the window at which the Stop hook asks for a rewrite
STALE_MINUTES = 20
COOLDOWN_MINUTES = 20
TAIL = 512_000             # bytes of transcript read from its end, rather than all of it every turn
MARKER = "_A compaction "


def config_path():
    return os.environ.get("CLAUDE_PLAYBOOK_CONFIG") or os.path.expanduser("~/.claude/playbook-config.json")   # as guard.py


def refresh_config(path):
    """Brings the config at path up to date. Returns a line to tell the session, or None."""
    if os.path.islink(path):   # a computer: pull the clone the link points into, quietly, as the playbook pull does
        try:
            subprocess.run(["git", "-C", os.path.dirname(os.path.realpath(path)), "pull", "-q", "--ff-only"],
                           capture_output=True, stdin=subprocess.DEVNULL, timeout=10,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})   # stdin holds the hook's JSON
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
    if not isinstance(repo, str) or not re.fullmatch(r"\w[\w.-]*/\w[\w.-]*", repo):
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
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=2)
        problem = config_problem(tmp)   # a broken latest copy must not replace a good pasted one
        if problem:
            os.remove(tmp)
            return f"The latest settings in {repo} are broken, so they were not used. Using the pasted copy."
        os.replace(tmp, path)
    except OSError as e:
        return f"The latest settings could not be saved ({e}). Using the pasted copy."
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


def notes_file(data):
    """The session's notes file, or None when the id isn't one we can put in a path."""
    sid = data.get("session_id") or ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        return None
    return os.path.expanduser(f"~/.claude/notes/{sid}.md")


def minutes_old(path):
    """How long since path was last written, or None when there is no such file.

    A file that is there but can't be read also comes back as None, so it is treated as missing:
    asking for a rewrite is the right move either way.
    """
    try:
        return (time.time() - os.path.getmtime(path)) / 60
    except OSError:
        return None


def how_old(minutes):
    """Minutes, until that stops reading as a number anyone pictures."""
    if minutes < 90:
        return f"was last written {int(minutes)} minutes ago"
    if minutes < 48 * 60:
        return f"was last written about {round(minutes / 60)} hours ago"
    return f"was last written about {round(minutes / 1440)} days ago"


def compact_window():
    """The tokens a compaction fires at, or None when nothing readable sets it."""
    env = (os.environ.get(WINDOW_ENV) or "").strip()
    if env.isdigit() and int(env) > 0:
        return int(env)
    for path in (".claude/settings.local.json", ".claude/settings.json",
                 os.path.expanduser("~/.claude/settings.json")):
        try:
            with open(path, encoding="utf-8") as f:
                window = json.load(f).get("autoCompactWindow")
        except (OSError, ValueError, AttributeError):
            continue
        if type(window) is int and window > 0:   # not bool, which is an int
            return window
    return None


def usage_in(lines):
    """The newest reply's token total in lines, which run newest first, or None."""
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isSidechain") or entry.get("type") != "assistant":
            continue   # a subagent's usage is not this conversation's
        usage = (entry.get("message") or {}).get("usage")
        if not isinstance(usage, dict):
            continue
        total = sum(usage.get(k) if type(usage.get(k)) is int else 0
                    for k in ("input_tokens", "cache_read_input_tokens",
                              "cache_creation_input_tokens", "output_tokens"))
        return total or None
    return None


def context_tokens(transcript_path):
    """What the next request re-sends, from the last reply's usage, as the hooks reference adds it up.

    Reads the last TAIL bytes, not the file: this runs at every turn end, and the sessions it is for
    have the longest transcripts. Only if that end holds no reply does it read the whole thing.
    """
    try:
        with open(transcript_path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(size - TAIL, 0))
            tail = f.read()
    except (OSError, TypeError, ValueError):
        return None
    if size > TAIL:
        tail = tail.split(b"\n", 1)[-1]   # the first line of the chunk is half a line
    total = usage_in(reversed(tail.decode("utf-8", "replace").splitlines()))
    if total is not None or size <= TAIL:
        return total
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            return usage_in(reversed(f.readlines()))
    except OSError:
        return None


def stop():
    """Asks for a notes rewrite while there is still room to write one."""
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return   # already continuing from a Stop block: never trap the session
    path = notes_file(data)
    if not path:
        return
    age = minutes_old(path)
    if age is not None and age < STALE_MINUTES:
        return   # the notes are current; nothing to ask for
    stamp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.warned")
    asked = minutes_old(stamp)
    if asked is not None and asked < COOLDOWN_MINUTES:
        return   # it asked once already
    used = context_tokens(data.get("transcript_path"))
    if used is None:
        return   # no reply to measure yet
    window = compact_window()
    if window is None or used < window * WARN_AT:
        return
    try:
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        open(stamp, "w").close()
    except OSError:
        return   # with no stamp it would ask every turn
    held = "is missing" if age is None else how_old(age)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": (
        f"A compaction is close: this session re-sends about {used:,} tokens and one fires at "
        f"{window:,}. Your notes file {held}. Write {path} now, then stop. "
        "Overwrite it with what is true now, under 30 lines: open PRs and their heads, who owes what, "
        "decisions with their dates, what comes next. Leave history out. "
        "No other session reads this file, so anything another one would need goes somewhere else first: "
        "a decision or a correction on the issue or PR it is about, and a mechanism you had to run "
        "something to learn in the playbook's docs/mechanisms.md. Then your note can point at it. "
        "A compaction keeps this file and "
        "drops the rest of the conversation, and only its last 4,000 characters are shown afterwards, "
        "so a log pushes the live state out of sight."
    )}}))


def pre_compact():
    """Marks the notes file, so the SessionStart after the compaction shows which lines predate it."""
    data = json.load(sys.stdin)
    path = notes_file(data)
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return   # nothing written yet; the SessionStart hook says so on its own
    kept = [l for l in text.rstrip().splitlines() if not l.startswith(MARKER)]
    trigger = data.get("trigger")
    trigger = trigger if trigger in ("auto", "manual") else "unknown"
    line = (f"{MARKER}({trigger}) started at {time.strftime('%Y-%m-%d %H:%M')}. "
            "Anything above this line is older than the conversation you are reading._")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + "\n\n" + line + "\n")
    except OSError:
        pass


def main():
    conf = config_path()
    try:
        note = refresh_config(conf)
    except Exception:   # a failed refresh never hides the check below
        note = None
    if note:
        print(note)
    problem = config_problem(conf)
    if problem:
        print(problem + " Setting up: the playbook's docs/how-it-works.md.")
    # Unconditional, and before the notes file: a session with no readable session_id still needs it.
    # The path is derived, not named: this file is claude/hooks/notes.py in the playbook, which lives at
    # ~/.claude/playbook in the cloud and in the owner's projects folder on a computer (#108).
    docs = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "docs", "mechanisms.md")
    print(f"What an earlier session had to run something to learn is in {docs}. "
          "Grep it before you say how something works, and add to it what you learn the same way.")
    path = notes_file(json.load(sys.stdin))
    if not path:
        return
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
        if "--stop" in sys.argv:
            stop()
        elif "--pre-compact" in sys.argv:
            pre_compact()
        else:
            main()
    except Exception:
        pass
    sys.exit(0)
