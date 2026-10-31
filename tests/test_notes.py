#!/usr/bin/env python3
"""notes.py's two prompts, so neither can silently drop out (#103, #104).

    python3 -I tests/test_notes.py [path/to/notes.py]

Exits 0 when every case lands where it should, 1 otherwise. No dependencies, no network.

The hook is run as a subprocess, not imported: both prompts are printed by `stop()` and `main()`
rather than returned, and stdout is the only thing Claude Code reads. Importing would test the
wording and miss the printing.

Each case gets its own HOME. `stop()` writes a stamp file beside the notes file before it prints,
and only prints once per COOLDOWN_MINUTES, so a shared HOME would make every case after the first
pass or fail for the wrong reason. The config, the transcript and the window all come from the case
too, so the answer is the same in every session: nothing is read from the machine.

What the cases are for:

ASKS    the warning fires and carries both the old ask (rewrite the notes) and the new one (put what
        another session needs somewhere else first). Checking the old one with the new is deliberate:
        the new sentence sits inside the same string, where a careless edit replaces it.
QUIET   the warning says nothing when the notes are current. Without this a prompt that always fires
        would pass ASKS.
NAMES   the SessionStart hook names docs/mechanisms.md. `no-notes` is the case that matters: the line
        has to print before main() gives up on an unusable session_id, or a session without a notes
        file never hears about the file.
"""
import json, os, subprocess, sys, tempfile

USAGE = "usage: python3 -I tests/test_notes.py [path/to/notes.py]"
NOTES = sys.argv[1] if len(sys.argv) > 1 else os.path.join("claude", "hooks", "notes.py")
if len(sys.argv) > 2:
    raise SystemExit(USAGE)

WINDOW = 1000          # tokens; the warning fires above WARN_AT of it
OVER = 900             # 0.9 of the window
UNDER = 100
SID = "0000-test"
MECHANISMS = "docs/mechanisms.md"
ELSEWHERE = "the issue or PR it is about"
REWRITE = "under 30 lines"
NOTES_LINE = "Your notes file is"


def transcript(home, used):
    path = os.path.join(home, "transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": used}}}) + "\n")
    return path


def config(home):
    """A config with nothing wrong with it, so no case depends on the machine's."""
    path = os.path.join(home, "playbook-config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"owner_only": {"commands": []}, "config_repo": "kuploy/claude-playbook-config"}, f)
    return path


def run(home, args, data, env=None):
    out = subprocess.run([sys.executable, "-I", NOTES] + args, input=json.dumps(data),
                         capture_output=True, text=True, timeout=30,
                         env={"HOME": home, "PATH": os.environ.get("PATH", ""),
                              "CLAUDE_PLAYBOOK_CONFIG": config(home),
                              "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(WINDOW), **(env or {})})
    return out.stdout


def case_stop_asks(home):
    out = run(home, ["--stop"], {"session_id": SID, "transcript_path": transcript(home, OVER)})
    return [w for w in (MECHANISMS, ELSEWHERE, REWRITE) if w not in out]


def case_stop_quiet(home):
    """Notes written just now: there is nothing to ask for."""
    notes = os.path.join(home, ".claude", "notes")
    os.makedirs(notes)
    with open(os.path.join(notes, SID + ".md"), "w", encoding="utf-8") as f:
        f.write("current\n")
    out = run(home, ["--stop"], {"session_id": SID, "transcript_path": transcript(home, OVER)})
    return ["it printed %r" % out[:80]] if out.strip() else []


def case_start_names(home):
    out = run(home, [], {"session_id": SID})
    return [w for w in (MECHANISMS, NOTES_LINE) if w not in out]


def case_start_no_notes(home):
    """An unusable session_id: no notes file, and the mechanisms line is still owed."""
    out = run(home, [], {"session_id": "not/a/path"})
    missing = [MECHANISMS] if MECHANISMS not in out else []
    return missing + ([NOTES_LINE] if NOTES_LINE in out else [])


CASES = [("stop-asks", case_stop_asks), ("stop-quiet", case_stop_quiet),
         ("start-names", case_start_names), ("start-no-notes", case_start_no_notes)]


def main():
    if not os.path.exists(NOTES):
        print("no notes.py at %s -- pass its path as the first argument" % NOTES)
        return 2
    bad = []
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as home:
            try:
                missing = fn(home)
            except Exception as e:                    # a case that cannot run is a failure, not a pass
                missing = ["%s: %s" % (type(e).__name__, e)]
        if missing:
            bad.append((name, missing))
        print("%-5s %-15s %s" % ("ok" if not missing else "FAIL", name,
                                 "" if not missing else "missing " + ", ".join(map(repr, missing))))
    print("\n%d cases, %d failing" % (len(CASES), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
