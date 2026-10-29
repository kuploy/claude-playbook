#!/usr/bin/env python3
"""Tells the agent console the moment a session waits on its owner, and when it stops waiting (#64).

Prompts are live state: they go to the console only, never to a PR (Ed, 2026-10-29). A question or
decision a session needs from its owner is not a prompt; the session writes that in the PR itself.

Events, wired in claude/settings.json and scripts/cloud-setup.sh:
- PermissionRequest (before the prompt shows) -> {"state": "waiting", "kind": "permission", ...}
- Notification, idle_prompt                    -> {"state": "waiting", "kind": "input", ...}
- UserPromptSubmit, PostToolUse                -> {"state": "cleared"}, only after a "waiting" was sent
  (a marker file under ~/.claude/attention/), so an ordinary tool call costs a file check, no request.

Contract with the console (kuploy/claude-agent-console#70): POST $CONSOLE_URL/api/ingest/attention,
`Authorization: Bearer $INGEST_SECRET`, body {"sessionId", "localSessionId", "state", "kind",
"message", "cwd", "at"}. sessionId is the cloud session's id (session_...) when there is one, else
null. The message names the tool and its description only, never the command, which can hold a secret.

No INGEST_SECRET: does nothing. Never blocks and never decides: a 2-second timeout, any error exits 0.
"""
import datetime
import json
import os
import sys
import urllib.request

URL = os.environ.get("CONSOLE_URL", "https://claude-agent-console.vercel.app").rstrip("/") + "/api/ingest/attention"
TIMEOUT = 2
MARKS = os.path.expanduser("~/.claude/attention")


def cloud_id():
    """The cloud session's id as the console knows it (session_...), from Claude Code's cse_... form."""
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID") or ""
    return "session_" + sid[4:] if sid.startswith("cse_") else (sid or None)


def waiting(data):
    """(kind, message) when this event means the session waits on its owner, else None."""
    event = data.get("hook_event_name")
    if event == "PermissionRequest":
        tool = data.get("tool_name") or "a tool"
        inp = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        what = inp.get("description") if isinstance(inp.get("description"), str) else ""
        return "permission", f"Approve or deny {tool}" + (f": {what[:200]}" if what else "")
    if event == "Notification" and data.get("notification_type") == "idle_prompt":
        return "input", (data.get("message") or "Waiting for your input")[:200]
    return None


def post(body, secret):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=TIMEOUT).close()


def main():
    secret = os.environ.get("INGEST_SECRET")
    if not secret:
        return
    data = json.load(sys.stdin)
    local = str(data.get("session_id") or "")
    mark = os.path.join(MARKS, local or "unknown")
    found = waiting(data)
    if found is None and data.get("hook_event_name") in ("UserPromptSubmit", "PostToolUse"):
        if not os.path.exists(mark):
            return
        os.remove(mark)   # first: a console that is down must not make every later tool call retry
        state, kind, message = "cleared", None, None
    elif found:
        state, (kind, message) = "waiting", found
        os.makedirs(MARKS, exist_ok=True)
        open(mark, "w").close()
    else:
        return
    post({"sessionId": cloud_id(), "localSessionId": local or None, "state": state, "kind": kind, "message": message,
          "cwd": data.get("cwd"), "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, secret)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
