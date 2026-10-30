#!/usr/bin/env python3
"""PreToolUse/PostToolUse guard: turns written rules into refusals and reminders.

Wired in settings.json (see docs/how-it-works.md). Claude Code runs it before a tool call
and passes the call as JSON on stdin.

  1. New branch  -> scope gate (#13): deny if the name has no issue number or the repo
                    has another open PR of yours; allow if the issue is a sub-issue of an
                    open `scope:frozen` epic; else ask the user.
                    A repo whose CLAUDE.md has a `Pattern:` line gets the pattern's branch
                    rule instead of one PR per repo (#29): `feat/<role>/<n>-slug`, one open
                    branch per role, at most the pattern's writers. No line: unchanged.
  2. Owner-only commands -> deny those listed in the config's `owner_only` (#44) unless
                    this session has the config's `allow_env` set to 1. No config: none.
  3. Merge       -> no opinion on a sync PR whose files all match the playbook (#40);
                    else deny if the `two-reviews` status exists and is not green;
                    if it is missing, count the reviews here and deny under two (#30);
                    ask if neither can be checked.
                    CLAUDE_REVIEW_GATE=local counts the reviews here instead and denies
                    under two; =both needs the green status and the local count (#34).
  4. PR body     -> deny over 15 lines (footer lines not counted).
  5. Review      -> deny a comment with `Reviewer:` that lacks the 4 lines,
                    or has more than 5 lines after the block.
  6. After a PR is opened (PostToolUse) -> remind: subscribe, schedule a check-in.

Config (#44): $CLAUDE_PLAYBOOK_CONFIG, else ~/.claude/playbook-config.json. It holds the
customer's choices: `owner_only` and `epic_home`. Missing or unreadable: both are off.

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
PLAYBOOK = "kuploy/claude-playbook"    # this repo: the source of synced files
# Per pattern: (writers, whether the lead named by `lead = <role>` may write). Mirrors patterns/*.md.
PATTERNS = {"lead-writer": (1, False), "peer-review": (1, True), "release-train": (2, False), "solo-audit": (1, True)}
ROLE_BRANCH = re.compile(r"^feat/([A-Za-z0-9._-]+)/\d+-[A-Za-z]")
# Options a frozen-epic branch command may carry and still be auto-approved. None runs a program.
SAFE_OPTS = {"-b", "-B", "-c", "-C", "-u", "--set-upstream", "-t", "--track", "--no-track"}
OWNER_ONLY_MSG = "Rule: only one session may run this command."

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


HEREDOC = r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\s*\1\s*(\n|$)"


def body_span(cmd):
    """Where a body sits in cmd: (intro, start, end, inert) for a heredoc's text or a --body/-b value, else None.

    bash_body returns that text; this returns its place, so a caller can cut it out by index instead of
    by value. Cutting by value removed every copy, which took a real invocation out along with the body
    that quoted it (#73 review).

    `intro` is where the thing that introduces the body starts -- the `<<` or the flag -- so a caller can
    ask which simple command the body belongs to. `start`/`end` bound the body text itself.

    `inert` says the shell will not run anything inside the body: a quoted heredoc tag, a single-quoted
    value or a $'' one. A review body is full of backticks, so this is what keeps markdown cuttable."""
    m = re.search(HEREDOC, cmd, re.S)
    if m:
        quoted_tag = re.match(r"<<-?\s*['\"]", m.group(0)) is not None
        return (m.start(),) + m.span(2) + (quoted_tag,)
    # a double-quoted value may hold \" ; $'...' and a single-quoted one can't hold an escape.
    # gh takes the last --body, so the last match is the body that will be sent.
    last = None
    for m in re.finditer(r"(?:--body=|(?:--body|-b)[ \t]+)"
                         r"(?:\$'([^']*)'|'([^']*)'|\"((?:[^\"\\]|\\.)*)\"|(\S+))", cmd):
        last = m
    if last:
        i = next(i for i in (1, 2, 3, 4) if last.group(i) is not None)
        # $'...' and '...' are inert; "..." and bare are not
        return (last.start(), last.start(i), last.end(i), i in (1, 2))
    return None


def segment_start(cmd, i):
    """Index where the simple command around position i begins: just past the last separator before i
    that the shell would act on, skipping separators inside quotes.

    A command substitution starts a command even inside double quotes, so `$(` and a backtick count
    there too: the text after them is a command of its own, whatever quotes surround it."""
    pos, quote, start = 0, None, 0
    while pos < i:
        two = cmd[pos:pos + 2]
        if quote:
            if quote == '"':
                if cmd[pos] == "\\":
                    pos += 2
                    continue
                if two == "$(" or cmd[pos] == "`":
                    pos += len(two) if two == "$(" else 1
                    start = pos
                    continue
            if cmd[pos] == quote:
                quote = None
            pos += 1
        elif cmd[pos] in "'\"":
            quote = cmd[pos]
            pos += 1
        elif cmd[pos] in "&|;\n()`" or two == "$(":
            pos += 2 if two in ("&&", "||", "$(") else 1
            start = pos
        else:
            pos += 1
    return start


def body_is_ghs(cmd, intro):
    """Does the body introduced at `intro` belong to a gh command, and is that gh the real one?

    The simple command the `<<` or the --body flag sits in has to be gh. One step outward is allowed:
    `--body "$(cat <<'EOT' ... EOT)"` is how a review with a long body is usually written, and a bare
    `cat` reading a heredoc runs nothing -- it copies the text out -- so the body is still gh's. Any
    other command there keeps its own body: `"$(bash <<'E' ... E)"` runs what the heredoc holds.

    And that gh has to be the *first* command, with nothing run before it. `gh` is a name, and anything
    the shell runs first can give the name to something else: a function, an alias, `hash -p /bin/bash
    gh`, `export PATH=/tmp/evil`. Earlier heads here enumerated those spellings and kept missing one
    (#75 reviews 7, 8, 9) -- and a PATH export is not a rebinding at all, so no list of rebindings was
    ever going to cover it. Nothing before gh covers the whole family at once.

    The cost, taken deliberately: a review chained after another command, `cd /tmp && gh pr comment
    ... "$(cat <<'E'`, stops being cut, so a body of it that names an owner-only command is refused.
    Run the gh on its own and it passes. One hole is left either way -- a gh planted on PATH by some
    earlier, separate Bash call -- and no guard that reads one command's text can see that."""
    i = intro
    while True:
        s = segment_start(cmd, i)
        seg = cmd[s:]
        if re.match(r"\s*gh\s", seg):
            return cmd[:s].strip() == ""
        # the cat has to be bare and the line has to end there: `cat <<'E' | bash` emits the heredoc
        # into a shell, and `cat <<'E' > /tmp/x; bash /tmp/x` runs it from the file (#75 review)
        if s >= 2 and re.match(r"\s*cat\s*<<-?\s*['\"]?\w+['\"]?[ \t]*\n", seg):
            i = s - (2 if cmd[s - 2:s] == "$(" else 1)
            continue
        return False


def outside_body(cmd):
    """cmd without the body of a gh command in it; cmd unchanged when there is no such body.

    Two conditions, both learned from breaking earlier versions of this (#73 review):

    Only a body the shell cannot execute is cut: a single-quoted or $'' value, or a heredoc with a
    quoted delimiter. A double-quoted or bare value is left alone, because $(...), a backtick and
    ${...} all run, so the invocation can sit inside the very text we would remove. Checking for those
    three spellings instead would be a blacklist; being unable to run anything is the property we want.

    And the body has to be gh's. `gh pr comment 1 --body hi` on one line and `bash <<'E'` on the next
    starts with gh, but that heredoc feeds bash, so cutting it would take a real invocation out. Asking
    whether the whole remainder looks like one gh command needs a complete list of separators, and the
    list was never complete -- a newline, a lone `&` and `<(` all got through it. So ask the question
    that was meant instead: whose body is this, and is that gh the real one (body_is_ghs)?"""
    found = body_span(cmd)
    if not found:
        return cmd
    intro, start, end, inert = found
    if not inert:
        return cmd
    if not body_is_ghs(cmd, intro):
        return cmd
    return cmd[:start] + cmd[end:]


def bash_body(cmd):
    """Body text of a gh command: a heredoc if present, else the --body/-b value."""
    m = re.search(HEREDOC, cmd, re.S)
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


def load_config():
    path = os.environ.get("CLAUDE_PLAYBOOK_CONFIG") or os.path.expanduser("~/.claude/playbook-config.json")
    try:
        with open(path, encoding="utf-8") as f:
            conf = json.load(f)
    except (OSError, ValueError):
        return {}
    return conf if isinstance(conf, dict) else {}


CONFIG = load_config()
EPIC_HOME = CONFIG.get("epic_home") or ""   # where epics live; empty: only the repo itself is asked


def owner_only(cmd, cwd):
    """The deny message when cmd matches one of the config's owner-only commands and this session isn't exempt.
    A command's `match` is a regex on the command text with any `gh` body taken out; `only_in`, if set, must
    appear in the folder or in what is left of the command.
    A field of the wrong type fails closed: no exemption, no folder limit, the default message. notes.py reports it."""
    rule = CONFIG.get("owner_only")
    if not isinstance(rule, dict) or not isinstance(rule.get("commands"), list):
        return None
    env = rule.get("allow_env")
    if isinstance(env, str) and env and os.environ.get(env) == "1":
        return None
    cmd = outside_body(cmd)   # a review that names an owner-only command is not running it (#73)
    msg = rule.get("message")
    for c in rule["commands"]:
        if not isinstance(c, dict):
            continue
        where = c.get("only_in")
        if isinstance(where, str) and where and where not in cwd and where not in cmd:
            continue
        try:
            hit = bool(c.get("match")) and re.search(c["match"], cmd)
        except (re.error, TypeError):   # notes.py reports a bad pattern at session start
            continue
        if hit:
            return msg if isinstance(msg, str) and msg else OWNER_ONLY_MSG
    return None


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
    shape = "{body, at: (.created_at // .submitted_at), login: .user.login}"
    comments = gh("api", "--paginate", f"{full}/issues/{number}/comments", "--jq", f".[] | {shape} | @json")
    reviews = gh("api", "--paginate", f"{full}/pulls/{number}/reviews", "--jq", f".[] | {shape} | @json")
    if comments is None or reviews is None:
        return None, ""
    # Split on "\n" only: splitlines() also splits on U+2028/U+2029, which gh leaves raw in @json.
    # A pending review has no time yet; skipped here, since a crash would fail open.
    items = sorted((it for it in (json.loads(l) for l in (comments + "\n" + reviews).split("\n") if l.strip())
                    if it.get("at")), key=lambda it: when(it["at"]))
    # Write access is asked of GitHub per author (#55): author_association can't see a private org
    # membership, so an org member shows up as CONTRIBUTOR. A failed lookup is unreadable GitHub: ask.
    writers = {}
    for login in {it.get("login") for it in items if it.get("login") and field(it["body"], "Reviewer")}:
        perm = gh("api", f"{full}/collaborators/{login}/permission", "--jq", ".permission")
        if perm is None:
            return None, ""
        writers[login] = perm.strip() in ("admin", "write")
    latest = {}   # latest verdict per reviewer name, from people with write access, after the push
    for it in items:
        if not writers.get(it.get("login")) or when(it["at"]) <= since:
            continue
        who, verdict = field(it["body"], "Reviewer"), field(it["body"], "Verdict")
        if who and verdict:
            latest[who.lower()] = (verdict.lower().startswith("approve")
                                   and bool(field(it["body"], "Ran")) and bool(field(it["body"], "Would catch")))
    return sum(latest.values()), note


def blob(full, path, ref):
    # Type with the sha: a symlink whose target text equals the file has the same blob sha.
    return gh("api", f"repos/{full}/contents/{path}?ref={ref}", "--jq", '.type + " " + .sha')


def sync_copy(owner, repo, number, sha):
    """True when every file the PR adds or modifies is a sync.yml dest, a plain file whose blob at the head equals its
    source on playbook main (#40). Any other file, a rename, a deletion, a mode change, a mismatch or an unreadable reply:
    False, and the review rules apply."""
    if repo.lower() == PLAYBOOK.split("/")[1]:
        return False
    conf = gh("api", f"repos/{PLAYBOOK}/contents/.github/sync.yml?ref=main", "-H", "Accept: application/vnd.github.raw")
    pairs = dict((d, s) for s, d in re.findall(r"-\s*source:\s*(\S+)\s*\n\s*dest:\s*(\S+)", conf or ""))
    files = gh("api", "--paginate", f"repos/{owner}/{repo}/pulls/{number}/files", "--jq", ".[] | [.filename, .status] | @json")
    if not pairs or not files:
        return False
    # Split on "\n" only, as in count_approvals: a filename can hold U+2028.
    for name, status in (json.loads(l) for l in files.split("\n") if l.strip()):
        if name not in pairs or status not in ("added", "modified"):
            return False
        head = blob(f"{owner}/{repo}", name, sha)
        if not head or not head.startswith("file ") or head != blob(PLAYBOOK, pairs[name], "main"):
            return False
    return True


def check_merge(owner, repo, number):
    where = f"{owner}/{repo}#{number}"
    if not (owner and repo and number):
        decide("ask", "Rule: 2 reviews before merge. Could not tell which PR this merges. Confirm two reviews exist.")
    sha = gh("api", f"repos/{owner}/{repo}/pulls/{number}", "--jq", ".head.sha")
    try:
        if sha and sync_copy(owner, repo, number, sha):
            return   # a sync PR needs one check, not two reviews (docs/how-it-works.md), and this was it
    except Exception:
        pass
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
        # No Action posted the status (#30: Actions minutes run out), so count the reviews here.
        n, note = local_approvals(owner, repo, number, sha)
        if n is None:
            decide("ask", f"Rule: 2 reviews before merge. {where} has no two-reviews status and its reviews could not be counted. Confirm two reviews exist.")
        if n >= 2:
            return
        decide("deny", f"Rule: 2 reviews before merge. {where} has no two-reviews status and {n} approving review(s) after the last push{note}. "
                       "Get two reviews (the 4-line block) on the current head.")
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


def repo_pattern(full):
    """(pattern, lead role) from the `Pattern: <name>, lead = <role>` line in the repo's CLAUDE.md.
    None when there is no line, the name is unknown or GitHub can't be read: the one-PR rule applies."""
    text = gh("api", "-H", "Accept: application/vnd.github.raw", f"repos/{full}/contents/CLAUDE.md")
    m = re.search(r"^Pattern:\s*([a-z-]+)(?:\s*,\s*lead\s*=\s*([A-Za-z0-9._-]+))?", text or "", re.M)
    return (m.group(1), m.group(2)) if m and m.group(1) in PATTERNS else None


def listed(prs):
    return ", ".join(f"#{n} {ref}" for n, ref in prs)


def role_of(ref):
    r = ROLE_BRANCH.match(ref)
    return r.group(1).lower() if r else ref   # a branch without a role holds a writer slot of its own


def check_role(full, name, mine, pattern, lead):
    """Branch rule of the repo's pattern (#29). Best effort: every session pushes as Ed, so a role is what the branch says."""
    writers, lead_writes = PATTERNS[pattern]
    m = ROLE_BRANCH.match(name)
    if not m:
        decide("deny", f"Rule ({pattern} in {full}): a branch reads feat/<role>/<issue>-slug, with your role from "
                       f"your spawn brief or Ed. '{name}' has no role.")
    role = m.group(1).lower()
    if lead and role == lead.lower() and not lead_writes:
        decide("deny", f"Rule ({pattern} in {full}): the lead, {lead}, doesn't write code here. Hand the issue to a writer.")
    held = [(n, ref) for n, ref in mine if role_of(ref) == role]
    if held:
        decide("deny", f"Rule ({pattern} in {full}): one open branch per writer. {role} already has open: {listed(held)}. "
                       "Finish that first; review fixes stay on its branch.")
    if len({role_of(ref) for _, ref in mine} | {role}) > writers:
        decide("deny", f"Rule ({pattern} in {full}): at most {writers} writer(s). Open now: {listed(mine)}. "
                       "Wait for one to merge.")


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
    mine = [(p["number"], p["head"]["ref"]) for p in json.loads(pulls)
            if p["user"]["login"] == me and p["head"]["ref"] != name]
    n = m.group(1)
    full = f"{owner}/{repo}"
    pattern = repo_pattern(full)
    if pattern:
        check_role(full, name, mine, *pattern)
    elif mine:
        decide("deny", f"Rule: one branch per repo until it merges. {full} already has open: {listed(mine)}. "
                       "Finish that first; review fixes stay on its branch. While it waits, review others or plan in an issue comment.")
    frozen = frozen_parent(full, n)
    # The epic home is asked only when this repo has no issue n of its own (none, or it is a PR).
    # A failed lookup is not "no issue": it falls through to ask.
    if frozen is None and EPIC_HOME and full != EPIC_HOME and issue_kind(full, n) in ("pr", "none"):
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
    msg = owner_only(cmd, cwd)
    if msg:
        decide("deny", msg)
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
