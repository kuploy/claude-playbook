#!/usr/bin/env python3
"""PreToolUse/PostToolUse guard: turns written rules into refusals and reminders.

Wired in settings.json (see docs/how-it-works.md). Claude Code runs it before a tool call
and passes the call as JSON on stdin.

  1. New branch  -> ask the user first.
  2. Release, build or cluster-write commands -> deny unless CLAUDE_RELEASE_OWNER=1.
  3. Merge       -> deny if the `two-reviews` status exists and is not green;
                    ask if it is missing or cannot be checked.
  4. PR body     -> deny over 15 lines (footer lines not counted).
  5. Review      -> deny a comment with `Reviewer:` that lacks the 4 lines,
                    or has more than 5 lines after the block.
  6. After a PR is opened (PostToolUse) -> remind: subscribe, schedule a check-in.

Silent exit 0 means no opinion: the normal permission flow continues.
Fails open on bad input, so a bug here never bricks a session.
Text patterns can be sidestepped by an unusual command. This catches the usual ones.
"""
import json
import os
import re
import shlex
import subprocess
import sys

NEW_BRANCH_MSG = "Rule: never create a new branch without asking first. Approve only if the user said so in this conversation."
RELEASE_MSG = ("Rule: only the release owner session runs releases, builds or cluster writes "
               "(kuploy-cloud CLAUDE.md). If you are that session, start it with CLAUDE_RELEASE_OWNER=1.")

PR_BODY_MAX = 15
FINDINGS_MAX = 5
FOOTER = re.compile(r"Generated (with|by) \[Claude Code\]|^https://claude\.ai/code|^Co-Authored-By:|^Claude-Session:|^-{3,}$")
CHECKIN_MSG = ("You just opened a PR. Rule: nudge each reviewer with one line and the link, subscribe to the PR, "
               "and schedule one check-in about an hour from now (cloud: send_later). Then end your turn.")

CREATE_FLAGS = {"-b", "-B", "-c", "-C", "--create", "--force-create", "--orphan"}
NOT_CREATING = {"-d", "-D", "--delete", "-m", "-M", "--move", "-a", "--all", "-r", "--remotes",
                "--list", "-l", "-v", "-vv", "--verbose", "--show-current", "--contains",
                "--merged", "--no-merged", "-u", "--set-upstream-to", "--unset-upstream",
                "--edit-description", "--sort", "--points-at", "--format"}


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def counted(text):
    return [l for l in (text or "").splitlines() if l.strip() and not FOOTER.search(l.strip())]


def pr_body_problem(body):
    n = len(counted(body))
    if n > PR_BODY_MAX:
        return (f"Rule: a PR body is at most {PR_BODY_MAX} lines (this one has {n}): what changed, why, "
                "how you verified it, reviewers. Move detail into commits or a linked file.")
    return None


def review_problem(body):
    lines = (body or "").splitlines()
    if not any(l.startswith("Reviewer:") for l in lines):
        return None
    missing = [k for k in ("Verdict:", "Ran:", "Would catch:") if not any(l.startswith(k) for l in lines)]
    if missing:
        return "Rule: a review is the 4-line block. Missing: " + ", ".join(missing) + "."
    i = next(i for i, l in enumerate(lines) if l.startswith("Would catch:"))
    extra = len(counted("\n".join(lines[i + 1:])))
    if extra > FINDINGS_MAX:
        return (f"Rule: after the review block, at most {FINDINGS_MAX} one-line findings (this has {extra} lines). "
                "Put anything longer in a file and link it.")
    return None


def bash_body(cmd):
    """Body text of a gh command: a heredoc if present, else the --body/-b value."""
    m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\s*\1\s*(\n|$)", cmd, re.S)
    if m:
        return m.group(2)
    try:
        toks = shlex.split(cmd)
    except ValueError:
        return None
    for i, t in enumerate(toks):
        if t in ("--body", "-b") and i + 1 < len(toks):
            return toks[i + 1]
        if t.startswith("--body="):
            return t.split("=", 1)[1]
    return None


def check_text(tool, inp, cmd):
    """Rules 4 and 5, for the GitHub MCP tools and for gh in Bash."""
    if tool in ("mcp__github__create_pull_request", "mcp__github__update_pull_request"):
        problem = pr_body_problem(inp.get("body"))
    elif tool in ("mcp__github__add_issue_comment", "mcp__github__pull_request_review_write"):
        problem = review_problem(inp.get("body"))
    elif tool == "Bash" and re.search(r"\bgh\s+pr\s+(create|edit)\b", cmd):
        problem = pr_body_problem(bash_body(cmd))
    elif tool == "Bash" and re.search(r"\bgh\s+(pr\s+(comment|review)|issue\s+comment)\b", cmd):
        problem = review_problem(bash_body(cmd))
    else:
        problem = None
    if problem:
        decide("deny", problem)


def opened_pr(tool, inp):
    return tool == "mcp__github__create_pull_request" or (
        tool == "Bash" and re.search(r"\bgh\s+pr\s+create\b", inp.get("command") or ""))


def segments(cmd):
    return [s.strip() for s in re.split(r"&&|\|\||;|\||\n", cmd) if s.strip()]


def tokens(seg):
    try:
        toks = shlex.split(seg)
    except ValueError:
        toks = seg.split()
    while toks and re.match(r"^\w+=", toks[0]):   # leading VAR=value
        toks = toks[1:]
    return toks


def git_call(toks):
    """(subcommand, args) of a `git ...` segment."""
    i = 1
    while i < len(toks):
        t = toks[i]
        if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return t, toks[i + 1:]
    return None, []


def creates_branch(sub, args):
    if sub in ("checkout", "switch"):
        return any(a in CREATE_FLAGS for a in args)
    if sub == "worktree":
        return args[:1] == ["add"] and any(a in ("-b", "-B") for a in args)
    if sub == "branch":
        flags = [a.split("=")[0] for a in args if a.startswith("-")]
        names = [a for a in args if not a.startswith("-")]
        return bool(names) and not any(f in NOT_CREATING for f in flags)
    if sub == "push":   # first push of a new branch is nearly always `-u`
        return any(a in ("-u", "--set-upstream") for a in args)
    return False


def is_release(cmd, cwd):
    in_cloud = "kuploy-cloud" in cwd or "kuploy-cloud" in cmd
    if re.search(r"docker/release\.sh", cmd):
        return True
    if in_cloud and re.search(r"(^|[\s/])(release|build)\.sh\b", cmd):
        return True
    if re.search(r"\bdocker\s+(buildx\s+)?(build|push)\b.*kuploy-cloud", cmd):
        return True
    return bool(re.search(r"\bkubectl\b.*\b(rollout|delete|apply|scale|patch|edit|replace|drain|cordon)\b", cmd))


def gh(*args):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def check_merge(owner, repo, number):
    where = f"{owner}/{repo}#{number}"
    if not (owner and repo and number):
        decide("ask", "Rule: 2 reviews before merge. Could not tell which PR this merges. Confirm two reviews exist.")
    sha = gh("api", f"repos/{owner}/{repo}/pulls/{number}", "--jq", ".head.sha")
    state = None
    if sha:
        state = gh("api", f"repos/{owner}/{repo}/commits/{sha}/status", "--jq",
                   '[.statuses[]|select(.context=="two-reviews")|.state]|first // "absent"')
    if state == "success":
        return
    if state is None:
        decide("ask", f"Rule: 2 reviews before merge. Could not check the two-reviews status of {where}. Confirm two reviews exist.")
    if state == "absent":
        decide("ask", f"Rule: 2 reviews before merge. {where} has no two-reviews status (check not set up). Confirm two reviews exist.")
    decide("deny", f"Rule: 2 reviews before merge. two-reviews on {where} is '{state}', not success. Get two reviews after the last push.")


def gh_merge_target(toks):
    args = toks[3:]
    repo = None
    number = None
    for i, a in enumerate(args):
        if a in ("-R", "--repo") and i + 1 < len(args):
            repo = args[i + 1]
        elif a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        elif number is None and not a.startswith("-"):
            m = re.search(r"(\d+)$", a)
            if m and (a.isdigit() or "/pull/" in a):
                number = m.group(1)
    if repo is None:
        repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    owner, _, name = (repo or "").partition("/")
    return owner, name, number


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    tool = event.get("tool_name", "")
    inp = event.get("tool_input") or {}
    cwd = event.get("cwd") or ""

    if event.get("hook_event_name") == "PostToolUse":
        if opened_pr(tool, inp):
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": CHECKIN_MSG}}))
        return

    check_text(tool, inp, inp.get("command") or "")

    if tool == "mcp__github__create_branch":
        decide("ask", NEW_BRANCH_MSG)
    if tool == "mcp__github__merge_pull_request":
        check_merge(inp.get("owner"), inp.get("repo"), inp.get("pullNumber"))
    if tool != "Bash":
        return

    cmd = inp.get("command") or ""
    for seg in segments(cmd):
        toks = tokens(seg)
        if toks[:3] == ["gh", "pr", "merge"]:
            check_merge(*gh_merge_target(toks))
        if toks[:1] == ["git"]:
            sub, args = git_call(toks)
            if creates_branch(sub, args):
                decide("ask", NEW_BRANCH_MSG)
    if os.environ.get("CLAUDE_RELEASE_OWNER") != "1" and is_release(cmd, cwd):
        decide("deny", RELEASE_MSG)


if __name__ == "__main__":
    try:
        main()
    except Exception:   # fail open
        sys.exit(0)
