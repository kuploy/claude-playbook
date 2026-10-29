#!/usr/bin/env python3
"""Stop hook (#48): sends a chat reply back once when it breaks the plain-language rules.

Reads the reply that ends the turn (the assistant text after the last tool result) from the
transcript, and flags what can be matched: listed words, listed phrases, sentences over a length.
On a hit it returns `decision: block` with the lines quoted, so the session rewrites before the
owner reads it. Once per turn: when the session is already continuing from a Stop block
(`stop_hook_active`), it says nothing, so a session is never trapped.

Code, inline code, links and table rows are skipped; they are not prose.
PR bodies, commits and reviews go through tools, not the reply, so guard.py keeps their rules.

Config (#44), same file as guard.py: `plain_language` = {"words": [...], "phrases": [regex, ...],
"max_words": 30}. Each part is optional. No `plain_language`: no check.
Never blocks on its own failure: bad input, a missing transcript or a bad config exits 0.
"""
import json
import os
import re
import sys

QUOTES = 5   # most lines quoted back, so the reason stays short


def load_rules():
    path = os.environ.get("CLAUDE_PLAYBOOK_CONFIG") or os.path.expanduser("~/.claude/playbook-config.json")   # as guard.py
    try:
        with open(path, encoding="utf-8") as f:
            conf = json.load(f)
    except (OSError, ValueError):
        return None
    rules = conf.get("plain_language") if isinstance(conf, dict) else None
    return rules if isinstance(rules, dict) else None


def last_reply(transcript_path):
    """The assistant text blocks after the last tool result or user prompt, in order."""
    texts = []
    with open(transcript_path, encoding="utf-8") as f:
        lines = f.readlines()
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isSidechain"):
            continue
        msg = entry.get("message") or {}
        content = msg.get("content")
        if entry.get("type") == "user":
            break
        if entry.get("type") != "assistant" or not isinstance(content, list):
            continue
        for block in reversed(content):
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
    return "\n\n".join(reversed(texts))


def prose(text):
    """The reply with code, inline code, links and table rows taken out, one line per entry."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            continue
        line = re.sub(r"`[^`]*`", "", line)
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"https?://\S+", "", line)
        out.append(line)
    return out


def findings(text, rules):
    words = [w for w in rules.get("words", []) if isinstance(w, str) and w]
    phrases = []
    for p in rules.get("phrases", []):
        try:
            phrases.append(re.compile(p, re.I))
        except (TypeError, re.error):
            continue
    limit = rules.get("max_words")
    limit = limit if isinstance(limit, int) and limit > 0 else None
    word_re = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")s?\b", re.I) if words else None

    hits = []
    for line in prose(text):
        for sentence in re.split(r"(?<=[.!?])\s+", line.strip()):
            if not sentence:
                continue
            why = []
            if word_re:
                why += [f'"{m.group(0)}"' for m in word_re.finditer(sentence)]
            why += [f'"{m.group(0)}"' for p in phrases for m in p.finditer(sentence)]
            n = len(re.findall(r"[A-Za-z0-9'’-]+", sentence))
            if limit and n > limit:
                why.append(f"{n} words")
            if why:
                hits.append((sentence, why))
    return hits


def main():
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return
    rules = load_rules()
    path = data.get("transcript_path")
    if not rules or not isinstance(path, str):
        return
    hits = findings(last_reply(path), rules)
    if not hits:
        return
    quoted = "\n".join(f"- {', '.join(why)}: \"{s[:200]}\"" for s, why in hits[:QUOTES])
    more = f"\n(and {len(hits) - QUOTES} more)" if len(hits) > QUOTES else ""
    reason = ("Your reply breaks the plain-language rules (rules: \"How to talk to me\"). Rewrite it and send it again: "
              "someone does X, then Y happens; one idea per sentence.\n" + quoted + more)
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
