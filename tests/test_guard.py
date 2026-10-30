#!/usr/bin/env python3
"""owner_only() cases from PR #75, kept so the next change to it starts from here (#80).

    python3 -I tests/test_guard.py [path/to/guard.py]

Exits 0 when every case lands where it should, 1 otherwise. No dependencies, no network.

To score any head, which is what made the #75 reviews legible:

    python3 -I tests/test_guard.py --rev 8f7192a

It reads that revision's guard with `git show`, so it needs no checkout and writes nothing you
have to clean up. A shell redirect into a temp file is the obvious alternative and it bit me:
the sandbox created the file and dropped the bytes, every head scored 0 cases, and the suite
said nothing until a case tried to call `owner_only` on an empty module.

Each case is one command string and the verdict it must get.

DENIED  the guard must refuse. Most of these were live bypasses on one of the seven heads of #75:
        main refuses them, some head allowed them. A few are DENIED only because the guard cannot
        prove the body is inert and refusing is the safe answer; those say so in a comment.
ALLOWED a review that merely *names* an owner-only command goes through. That is #73, the bug the
        PR was for. A guard that denies everything fails here, which is the point of these cases.

The config is written by this file, not read from the machine, so the answer is the same in every
session: one owner-only pattern and no `allow_env`, so nothing is exempt. The pattern is assembled
from fragments because the installed guard reads the text of the command that writes this file and
would refuse a literal (#76).

The expectations encode the design #75 settled on: a body is cut before matching only when it is
inert (single-quoted, $'...', or a heredoc with a quoted delimiter), only when it belongs to a gh
segment (one step outward through a bare `cat` whose line ends at the tag), and only when nothing
runs before that gh. If "nothing runs before the gh" is ever relaxed, `chain-cd` is the case to
change deliberately rather than delete.
"""
import importlib.util, json, os, subprocess, sys, tempfile

GUARD = os.path.join("claude", "hooks", "guard.py")
REV = None
if len(sys.argv) > 2 and sys.argv[1] == "--rev":
    REV = sys.argv[2]
elif len(sys.argv) > 1:
    GUARD = sys.argv[1]
CWD = "/anywhere"                 # no case depends on the folder
O = "npm" + " " + "publish"       # the one owner-only pattern (#76: never as a literal)
W = O.split()[1]                  # just the second word, to test a fragment of it
R = "./docker/" + "release" + ".sh"
BT = chr(96)
SUB = "$(cat <<'E'\n%s\nE\n)"     # the long-review form: --body "$(cat <<'EOT' ... EOT)"

CASES = [
 # --- #73 itself: a review that names an owner-only command, in a body the shell cannot run ---
 ("73-quoted",      "gh pr comment 1 --body 'do not run %s'" % O, "ALLOWED"),
 ("73-dollar-sq",   "gh pr comment 1 --body $'I ran %s'" % O, "ALLOWED"),
 ("73-body-eq",     "gh pr comment 1 --body='I ran %s'" % O, "ALLOWED"),
 ("73-dash-b",      "gh pr review 1 -b 'I ran %s'" % O, "ALLOWED"),
 ("73-heredoc",     "gh pr comment 1 -F - <<'A'\nI ran %s\nA\n" % O, "ALLOWED"),
 ("73-cat-sub",     'gh pr comment 1 --body "%s"' % (SUB % ("I ran " + O)), "ALLOWED"),
 ("73-cat-space",   "gh pr comment 1 --body \"$( cat <<'E'\nI ran %s\nE\n)\"" % O, "ALLOWED"),
 ("73-cat-nospace", "gh pr comment 1 --body \"$(cat<<'E'\nI ran %s\nE\n)\"" % O, "ALLOWED"),
 ("73-cat-tab",     "gh pr comment 1 --body \"$(cat <<'E'  \t\nI ran %s\nE\n)\"" % O, "ALLOWED"),
 ("73-backtick-sub","gh pr comment 1 --body \"%scat <<'E'\nI ran %s\nE\n%s\"" % (BT, O, BT), "ALLOWED"),
 ("73-md-ticks",    "gh pr comment 1 -b 'Ran: %s%s%s'" % (BT, O, BT), "ALLOWED"),
 ("73-issue",       "gh issue comment 9 -b 'see %s'" % R, "ALLOWED"),
 ("73-issue-create","gh issue create -t x -b 'see %s'" % R, "ALLOWED"),
 ("73-review-sub",  "gh pr review 971 --comment --body \"$(cat <<'E'\nRan: %s --dry-run\nE\n)\"" % R, "ALLOWED"),
 ("73-says-cat",    "gh pr comment 1 -b 'cat the log, do not %s'" % O, "ALLOWED"),
 ("73-quotes-fn",   "gh pr comment 1 -b 'beware gh() { bash; } in a body, and %s'" % O, "ALLOWED"),
 ("73-lead-space",  "  \n  gh pr comment 1 --body 'I ran %s'" % O, "ALLOWED"),
 ("73-then-echo",   "gh pr comment 1 -b 'Ran: %s' && echo done" % R, "ALLOWED"),

 # --- the command actually runs: always refuse ---
 ("run-plain",      O, "DENIED"),
 ("run-in-folder",  "%s --tag v2" % R, "DENIED"),
 ("run-dquoted",    'gh pr comment 1 --body "%s"' % O, "DENIED"),
 ("run-sub-body",   'gh pr comment 1 --body "$(%s)"' % O, "DENIED"),
 ("run-bare-body",  "gh pr comment 1 -b %s" % R, "DENIED"),
 ("run-body-eq-dq", 'gh pr comment 1 --body="Ran: %s"' % O, "DENIED"),
 ("run-esc-quote",  'gh pr comment 1 -b "he said \\"%s\\" once"' % R, "DENIED"),
 ("run-brace-exp",  'gh pr comment 1 -b "${x:-%s}"' % O, "DENIED"),
 ("run-backtick",   'gh pr comment 1 -b "%s%s%s"' % (BT, O, BT), "DENIED"),
 ("run-sub-bare",   "gh pr comment 1 -b $(%s)" % O, "DENIED"),
 ("run-then-real",  "gh pr comment 1 -b 'Ran: %s' && %s" % (R, R), "DENIED"),
 ("run-after-body", 'gh pr comment 1 -b "note" && %s' % R, "DENIED"),
 ("run-no-body",    "gh pr list && %s" % R, "DENIED"),
 ("run-fragment",   "%s && gh pr comment 1 --body %s" % (O, W), "DENIED"),
 ("run-frag-quoted","%s && gh pr comment 1 --body '%s'" % (O, W), "DENIED"),
 ("run-checkout-b", "git checkout -b %s && %s" % (W, O), "DENIED"),
 ("run-other-tool", "./tool -b %s && %s" % (W, O), "DENIED"),
 ("run-cut-by-val", "%s && gh pr comment 1 --body publish" % O, "DENIED"),
 ("run-2nd-heredoc","gh pr comment 1 -b \"%s\" && %s <<'B'\nx\nB" % (SUB % "note", R), "DENIED"),
 ("run-cat-to-file","cat > notes.md <<EOF\nI ran %s once\nEOF" % R, "DENIED"),

 # --- a heredoc that feeds a shell, with a harmless gh riding along ---
 ("sep-and",        "gh pr comment 1 --body hi && bash <<'E'\n%s\nE\n" % O, "DENIED"),
 ("sep-newline",    "gh pr comment 1 --body hi\nbash <<'E'\n%s\nE\n" % O, "DENIED"),
 ("sep-bare-amp",   "gh pr comment 1 --body hi & bash <<'E'\n%s\nE\n" % O, "DENIED"),
 ("sep-semi",       "gh pr comment 1 --body hi; bash <<'E'\n%s\nE\n" % O, "DENIED"),
 ("sep-pipe",       "gh pr comment 1 --body hi | bash <<'E'\n%s\nE\n" % O, "DENIED"),
 ("sep-reversed",   "bash <<'F'\n%s\nF\ngh pr comment 1 --body hi\n" % O, "DENIED"),
 ("sep-first-cmd",  "gh pr list && bash <<'E'\n%s\nE" % O, "DENIED"),
 ("sep-gh-later",   "echo hi\nbash <<'E'\n%s\nE\ngh pr comment 1 -b ok" % O, "DENIED"),
 ("sep-body-amp",   "gh pr comment 1 -b x&&%s" % O, "DENIED"),
 ("sep-body-semi",  "gh pr comment 1 -b x;%s" % O, "DENIED"),
 ("bash-in-body",   "gh pr comment 1 --body \"$(bash <<'E'\n%s\nE\n)\"" % O, "DENIED"),
 ("sh-c-in-body",   "gh pr comment 1 --body \"$(sh -c x <<'E'\n%s\nE\n)\"" % O, "DENIED"),
 ("proc-sub-file",  "gh pr comment 1 --body-file <(bash <<'E'\n%s\nE\n)" % O, "DENIED"),
 ("unquoted-tag",   "gh pr comment 1 --body \"$(cat <<E\nRan: %s\nE\n)\"" % O, "DENIED"),
 ("bash-unq-tag",   "bash <<EOF\n%s\nEOF\n# gh pr comment" % O, "DENIED"),

 # --- the cat step outward is for a bare cat whose line ends at the tag ---
 ("cat-pipe-bash",  "gh pr comment 1 --body \"$(cat <<'E' | bash\n%s\nE\n)\"" % O, "DENIED"),
 ("cat-pipe-sh",    "gh pr comment 1 --body \"$(cat <<'E' |sh\n%s\nE\n)\"" % O, "DENIED"),
 ("cat-pipe-xargs", "gh pr comment 1 --body \"$(cat <<'E' | xargs -0 sh -c\n%s\nE\n)\"" % O, "DENIED"),
 ("cat-to-file",    "gh pr comment 1 --body \"$(cat <<'E' > /tmp/x; bash /tmp/x\n%s\nE\n)\"" % O, "DENIED"),
 ("cat-cont-pipe",  "gh pr comment 1 --body \"$(cat <<'E' \\\n| bash\n%s\nE\n)\"" % O, "DENIED"),
 ("cat-redir-first","gh pr comment 1 --body \"$( >/tmp/x cat <<'E'\n%s\nE\n; bash /tmp/x)\"" % O, "DENIED"),
 ("cat-flagged",    "gh pr comment 1 --body \"$(cat -n <<'E'\nRan: %s\nE\n)\"" % O, "DENIED"),
 ("eval-cat",       'eval "%s"' % (SUB % O), "DENIED"),
 ("eval-after-gh",  "gh pr comment 1 --body \"$(cat <<'E'\nhi\nE\n)\"; eval \"$(cat <<'F'\n%s\nF\n)\"" % O, "DENIED"),

 # --- gh is a name, and nothing may run before it, whatever the name was given to ---
 ("rebind-fn",      "gh(){ bash; }; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-fn-space","gh () { bash; }; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-fn-kw",   "function gh { bash; }; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-fn-sub",  "gh()( bash ); gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-alias",   "alias gh=bash; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-eval",    "eval 'gh(){ bash; }'; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-hash",    "hash -p /bin/bash gh; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-path",    "export PATH=/tmp/evil; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-path-pre","export PATH=/tmp/evil:$PATH; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-source",  ". ./evil.sh; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-source-kw","source ./evil.sh; gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("rebind-cat-fn",  'cat(){ bash; }; gh pr comment 1 --body "%s"' % (SUB % O), "DENIED"),
 ("rebind-cat-kw",  'function cat { bash; }; gh pr comment 1 --body "%s"' % (SUB % O), "DENIED"),
 ("rebind-cat-alias",'alias cat=bash; gh pr comment 1 --body "%s"' % (SUB % O), "DENIED"),
 ("rebind-cat-hash",'hash -p /bin/bash cat; gh pr comment 1 --body "%s"' % (SUB % O), "DENIED"),

 # --- the shell's own output redirected to a file, then the file run ---
 ("exec-redir",     "exec > /tmp/x\ngh pr comment 1 --body hi 2>/dev/null\ncat <<'E'\n%s\nE\nexec > /dev/tty\nbash /tmp/x" % O, "DENIED"),
 ("exec-append",    "exec >> /tmp/x\ngh pr comment 1 --body hi\ncat <<'E'\n%s\nE\nbash /tmp/x" % O, "DENIED"),
 ("group-redir",    "{ gh pr comment 1 --body hi\ncat <<'E'\n%s\nE\n} > /tmp/x; bash /tmp/x" % O, "DENIED"),
 ("subshell-redir", "( gh pr comment 1 --body hi\ncat <<'E'\n%s\nE\n) > /tmp/x; bash /tmp/x" % O, "DENIED"),

 # --- refused because the guard cannot prove the body is gh's and inert; refusing is the answer ---
 ("chain-cd",       "cd /tmp && gh pr comment 1 --body \"$(cat <<'E'\nRan: %s\nE\n)\"" % O, "DENIED"),
 ("subshell-gh",    "(gh pr comment 1 --body 'Ran: %s')" % O, "DENIED"),
 ("assign-prefix",  "FOO=1 gh pr comment 1 --body 'Ran: %s'" % O, "DENIED"),
 ("env-prefix",     "BASH_ENV=/tmp/e gh <<'E'\n%s\nE\n" % O, "DENIED"),
 ("lead-comment",   "# review\ngh pr comment 1 --body '%s'" % O, "DENIED"),
 ("redir-before-gh","> /tmp/x gh pr comment 1 --body '%s'" % O, "DENIED"),
 ("unterminated",   "gh pr comment 1 --body \"$(cat <<'E'\nhi\n)\" ; %s" % O, "DENIED"),
 ("escaped-dquote", "gh pr comment 1 --body 'hi' && echo \\\" && bash <<'E'\n%s\nE\n" % O, "DENIED"),
]


def from_rev(rev):
    """That revision's guard, written to a temp file. Raises if git gives us nothing."""
    src = subprocess.run(["git", "show", "%s:%s" % (rev, GUARD)],
                         capture_output=True, text=True, check=True).stdout
    if "def owner_only" not in src:
        raise SystemExit("%s:%s has no owner_only (%d bytes)" % (rev, GUARD, len(src)))
    fd, name = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w") as f:
        f.write(src)
    return name


def load(path):
    """Import guard.py with a config of our own, which it reads at import time (guard.py:331)."""
    fd, name = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"owner_only": {"message": "DENIED",
                                  "commands": [{"match": O}, {"match": R}]}}, f)
    os.environ["CLAUDE_PLAYBOOK_CONFIG"] = name
    spec = importlib.util.spec_from_file_location("guard_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, name


def main():
    path = from_rev(REV) if REV else GUARD
    if not os.path.exists(path):
        print("no guard at %s -- pass its path as the first argument" % path)
        return 2
    mod, cfgfile = load(path)
    if not hasattr(mod, "owner_only"):
        print("%s imported but has no owner_only" % path)
        return 2
    try:
        bad = []
        for cid, cmd, want in CASES:
            got = "DENIED" if mod.owner_only(cmd, CWD) else "ALLOWED"
            if got != want:
                bad.append((cid, want, got))
            print("%-5s %-18s want %-7s got %s" % ("ok" if got == want else "FAIL", cid, want, got))
        print("\n%d cases, %d failing" % (len(CASES), len(bad)))
        for cid, want, got in bad:
            print("  %s: wanted %s, got %s" % (cid, want, got))
        return 1 if bad else 0
    finally:
        os.unlink(cfgfile)


if __name__ == "__main__":
    sys.exit(main())
