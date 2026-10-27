#!/usr/bin/env python3
"""PreToolUse/PostToolUse guard: turns written rules into refusals and reminders.

Wired in settings.json (see docs/how-it-works.md). Claude Code runs it before a tool call
and passes the call as JSON on stdin.

  1. New branch  -> scope gate (#13): deny if the name has no issue number or the repo
                    has another open PR of yours; allow if the issue is a sub-issue of an
                    open `scope:frozen` epic; else ask the user.
  2. Release, build or cluster-write commands -> deny unless CLAUDE_RELEASE_OWNER=1.
  3. Merge       -> deny if the `two-reviews` status exists and is not green;
                    ask if it is missing or cannot be checked.
                    CLAUDE_REVIEW_GATE=local counts the reviews here instead and denies
                    under two; =both needs the green status and the local count (#34).
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
from datetime import datetime

NEW_BRANCH_MSG = "Rule: never create a new branch without asking first. Approve only if the user said so in this conversation."
FROZEN_MSG = "Scope gate: branch for a sub-issue of an open scope:frozen epic. Approved by the freeze."
EPIC_HOME = "kuploy/claude-playbook"   # where epics and most of their issues live
# Options a frozen-epic branch command may carry and still be auto-approved. None runs a program.
SAFE_OPTS = {"-b", "-B", "-c", "-C", "-u", "--set-upstream", "-t", "--track", "--no-track"}
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
    """Simple commands in cmd, split on && || ; | ( ) and newlines, but not inside quotes."""
    try:
        lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:   # e.g. a heredoc: fall back to a plain split
        return [s.strip() for s in re.split(r"&&|\|\||;|\||\n", cmd) if s.strip()]
    segs, cur = [], []
    for t in toks + [";"]:
        if set(t) <= set("&|;()"):
            if cur:
                segs.append(shlex.join(cur))
            cur = []
        else:
            cur.append(t)
    return segs


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
    """Name of the branch a git call creates (or first-pushes), '' if unknown, None if none."""
    names = [a for a in args if not a.startswith("-")]
    if sub in ("checkout", "switch"):
        for i, a in enumerate(args):
            if a in CREATE_FLAGS:
                return args[i + 1] if i + 1 < len(args) else ""
            if a.startswith("--") and a.split("=")[0] in CREATE_FLAGS:   # --create=name
                return a.split("=", 1)[1]
            if re.match(r"^-[bBcC].", a):                               # -bname
                return a[2:]
        return None
    if sub == "worktree":
        if args[:1] == ["add"] and any(a in ("-b", "-B") for a in args):
            i = next(i for i, a in enumerate(args) if a in ("-b", "-B"))
            return args[i + 1] if i + 1 < len(args) else ""
        return None
    if sub == "branch":
        flags = [a.split("=")[0] for a in args if a.startswith("-")]
        return names[0] if names and not any(f in NOT_CREATING for f in flags) else None
    if sub == "push":   # first push of a new branch is nearly always `-u`
        if not any(a in ("-u", "--set-upstream") for a in args):
            return None
        ref = names[1] if len(names) > 1 else ""
        return ref.split(":")[-1].removeprefix("refs/heads/") if ref not in ("", "HEAD") else ""
    return None


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


def issue_kind(full, n):
    """'issue', 'pr', 'none' (GitHub says 404), or None when GitHub could not be asked."""
    try:
        r = subprocess.run(["gh", "api", f"repos/{full}/issues/{n}", "--jq",
                            'if .pull_request then "pr" else "issue" end'],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode == 0:
        return r.stdout.strip() or None
    return "none" if "HTTP 404" in r.stderr else None


def when(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def field(body, name):
    m = re.search(rf"^\s*{name}:[ \t]*(.+)$", body or "", re.I | re.M)
    return m.group(1).strip() if m else None


def local_approvals(owner, repo, number, sha):
    """(approving reviewers after the head was pushed, note), counted as sync/two-reviews.yml does.
    Count None: GitHub unreachable or a reply we could not read, so the caller asks rather than failing open."""
    try:
        return count_approvals(owner, repo, number, sha)
    except Exception:
        return None, ""


def count_approvals(owner, repo, number, sha):
    full = f"repos/{owner}/{repo}"
    committed = gh("api", f"{full}/commits/{sha}", "--jq", ".commit.committer.date")
    if not committed:
        return None, ""
    # Push time is the earliest check suite (when GitHub received the sha), never the committer
    # date alone: a verdict written between commit and push has not seen the pushed head.
    since = when(committed)
    suites = gh("api", "--paginate", f"{full}/commits/{sha}/check-suites", "--jq", ".check_suites[].created_at")
    seen = sorted(when(s) for s in (suites or "").split())
    if seen and seen[0] > since:
        since = seen[0]
    note = "" if suites is not None else " (push time unknown: counted from the commit date)"
    shape = "{body, at: (.created_at // .submitted_at), assoc: .author_association}"
    comments = gh("api", "--paginate", f"{full}/issues/{number}/comments", "--jq", f".[] | {shape} | @json")
    reviews = gh("api", "--paginate", f"{full}/pulls/{number}/reviews", "--jq", f".[] | {shape} | @json")
    if comments is None or reviews is None:
        return None, ""
    # Split on "\n" only: splitlines() also splits on U+2028/U+2029, which gh leaves raw in @json.
    # A pending review has no time yet; skipped here, since a crash would fail open.
    items = sorted((it for it in (json.loads(l) for l in (comments + "\n" + reviews).split("\n") if l.strip())
                    if it.get("at")), key=lambda it: when(it["at"]))
    latest = {}   # latest verdict per reviewer name, from people with write access, after the push
    for it in items:
        if it["assoc"] not in ("OWNER", "MEMBER", "COLLABORATOR") or when(it["at"]) <= since:
            continue
        who, verdict = field(it["body"], "Reviewer"), field(it["body"], "Verdict")
        if who and verdict:
            latest[who.lower()] = (verdict.lower().startswith("approve")
                                   and bool(field(it["body"], "Ran")) and bool(field(it["body"], "Would catch")))
    return sum(latest.values()), note


def check_merge(owner, repo, number):
    where = f"{owner}/{repo}#{number}"
    if not (owner and repo and number):
        decide("ask", "Rule: 2 reviews before merge. Could not tell which PR this merges. Confirm two reviews exist.")
    sha = gh("api", f"repos/{owner}/{repo}/pulls/{number}", "--jq", ".head.sha")
    mode = os.environ.get("CLAUDE_REVIEW_GATE", "status").strip().lower()
    if mode not in ("status", "local", "both"):
        decide("ask", f"Rule: 2 reviews before merge. CLAUDE_REVIEW_GATE='{mode}' is not status, local or both. Confirm two reviews exist.")
    if mode in ("local", "both"):
        n, note = local_approvals(owner, repo, number, sha) if sha else (None, "")
        if n is None:
            decide("ask", f"Rule: 2 reviews before merge. Could not count the reviews on {where}. Confirm two reviews exist.")
        if n < 2:
            decide("deny", f"Rule: 2 reviews before merge. {where} has {n} approving review(s) after the last push{note}. "
                           "Get two reviews (the 4-line block) on the current head.")
        if mode == "local":
            return
    state = None
    if sha:
        state = gh("api", f"repos/{owner}/{repo}/commits/{sha}/status", "--jq",
                   '[.statuses[]|select(.context=="two-reviews")|.state]|first // "absent"')
    if state == "success":
        return
    if state is None:
        decide("ask", f"Rule: 2 reviews before merge. Could not check the two-reviews status of {where}. Confirm two reviews exist.")
    if state == "absent" and mode == "both":
        decide("deny", f"Rule: 2 reviews before merge. {where} has no two-reviews status, and CLAUDE_REVIEW_GATE=both needs it green.")
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


def git_out(where, *args):
    try:
        r = subprocess.run(["git", "-C", where or ".", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def origin_repo(where):
    url = git_out(where, "remote", "get-url", "origin") or ""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(\.git)?$", url)
    return (m.group(1), m.group(2)) if m else (None, None)


def frozen_parent(repo, n):
    """True/False: issue n of repo is a sub-issue of an open scope:frozen epic. None: no such parent found."""
    out = gh("api", f"repos/{repo}/issues/{n}/parent", "--jq",
             '(.state=="open") and ([.labels[].name]|index("scope:frozen")!=null)')
    return None if out is None else out == "true"


def check_new_branch(owner, repo, name):
    """Scope gate (#13). One branch per repo until merged; frozen-epic work needs no prompt."""
    if name == "" or name is None:
        decide("ask", NEW_BRANCH_MSG + " Could not read the branch name.")
    m = re.search(r"(?:^|/)(\d+)-[A-Za-z]", name)
    if not m:
        decide("deny", f"Rule: a branch names its issue, e.g. feat/<issue>-slug. '{name}' has no issue number.")
    if not (owner and repo):
        decide("ask", NEW_BRANCH_MSG + " Could not tell which repo this is.")
    me = gh("api", "user", "--jq", ".login")
    pulls = me and gh("api", f"repos/{owner}/{repo}/pulls?state=open&per_page=100")
    if not pulls:
        decide("ask", NEW_BRANCH_MSG + " Could not reach GitHub to check scope.")
    others = ", ".join(f"#{p['number']} {p['head']['ref']}" for p in json.loads(pulls)
                       if p["user"]["login"] == me and p["head"]["ref"] != name)
    if others:
        decide("deny", f"Rule: one branch per repo until it merges. {owner}/{repo} already has open: {others}. "
                       "Finish that first; review fixes stay on its branch. While it waits, review others or plan in an issue comment.")
    n = m.group(1)
    full = f"{owner}/{repo}"
    frozen = frozen_parent(full, n)
    # The epic home is asked only when this repo has no issue n of its own (none, or it is a PR).
    # A failed lookup is not "no issue": it falls through to ask.
    if frozen is None and full != EPIC_HOME and issue_kind(full, n) in ("pr", "none"):
        frozen = frozen_parent(EPIC_HOME, n)
    if frozen:
        return True
    decide("ask", f"Scope gate: issue #{n} is not in an open scope:frozen epic. New scope needs the user's yes in this "
                  "conversation (or they add it as a sub-issue of the epic).")


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
        if check_new_branch(inp.get("owner"), inp.get("repo"), inp.get("branch") or ""):
            decide("allow", FROZEN_MSG)
    if tool == "mcp__github__merge_pull_request":
        check_merge(inp.get("owner"), inp.get("repo"), inp.get("pullNumber"))
    if tool != "Bash":
        return

    cmd = inp.get("command") or ""
    where = cwd
    segs = segments(cmd)
    allowed = False
    for seg in segs:
        toks = tokens(seg)
        if toks[:1] == ["cd"] and len(toks) > 1:
            where = os.path.join(where, os.path.expanduser(toks[1]))
        if toks[:3] == ["gh", "pr", "merge"]:
            check_merge(*gh_merge_target(toks))
        if toks[:1] == ["git"]:
            sub, args = git_call(toks)
            name = creates_branch(sub, args)
            if name is not None:
                d = toks[toks.index("-C") + 1] if "-C" in toks[:toks.index(sub)] else where
                d = os.path.join(where, os.path.expanduser(d))
                if name == "":
                    name = git_out(d, "rev-parse", "--abbrev-ref", "HEAD") or ""
                if sub == "push" and name and git_out(d, "ls-remote", "--heads", "origin", name):
                    continue   # branch already on the remote: not new
                allowed = check_new_branch(*origin_repo(d), name) or allowed
    if os.environ.get("CLAUDE_RELEASE_OWNER") != "1" and is_release(cmd, cwd):
        decide("deny", RELEASE_MSG)
    # Auto-approve only a bare `git [-C dir] <sub> ...` of plain words: no compound, substitution,
    # redirect, env prefix or `-c` setting, since those can run a program the user never saw.
    # Options after the subcommand must be on SAFE_OPTS: `push --receive-pack <cmd>` (or any
    # abbreviation git accepts, like `--rece`) runs <cmd> when the remote is a local path.
    toks = cmd.split()
    plain = all(re.fullmatch(r"[A-Za-z0-9._/@:+-]+", t) for t in toks)
    if allowed and len(segs) == 1 and plain and toks[0] == "git":
        if toks[1] == "-C":
            toks = toks[2:]
        opts = [t for t in toks[2:] if t.startswith("-")]
        if not toks[1].startswith("-") and all(o in SAFE_OPTS for o in opts):
            decide("allow", FROZEN_MSG)


if __name__ == "__main__":
    try:
        main()
    except Exception:   # fail open
        sys.exit(0)
