# Overview

## Getting a peer onto the rules

The rules live in `rules/account-instructions.md`: desktop sessions import it from `~/.claude/CLAUDE.md`, cloud sessions read the same text from the Claude account settings. A session loads them when it **starts**. So a running peer must be restarted.

**After you change the rules file** (no PR, no merge: it is not copied into repos):

1. Paste it into Claude account settings. Cloud sessions read it there.
2. Desktop sessions read your laptop copy. The `SessionStart` hook pulls it for you; without that hook, run `git -C ~/Devl/Projects/claude-playbook pull`.
3. Restart the peers that should follow it (below).

```
peer pushes branch ─▶ writes status on its issue/PR ─▶ end the old session
      ─▶ start a fresh session on that issue ─▶ it loads the account prompt ─▶ spot-check its next PR
```

| Step | Who |
|---|---|
| 1. Push the branch. Write where it stopped, on the peer's own issue or PR. | peer |
| 2. End the old session. Start a new one on that issue: "Continue issue #N, read its latest comment." | you |
| 3. The new session loads the account prompt by itself. No message needed. | automatic |
| 4. Check its next PR: review block present? messages short? two different reviewer names? | you |

No nudge message: a fresh session wouldn't remember it. Don't rely on peers reading this repo: it's private, and a cloud session only opens repos attached to it. The account prompt is self-contained.

A desktop session gets no spawn brief. When you start one on a repo with a `Pattern:` line, name its role in your first message ("You are the reviewer"); otherwise it asks.

## Who owns what

```
repo ──▶ ONE writer (branches, merges)
         everyone else: read-only, reviews by PR comment
PR   ──▶ 2 reviews (4-line block) ──▶ writer merges
thread ─▶ only its owner reports to you
```

Which rule is enforced, by which gate, and where it works: [enforcement.md](enforcement.md).

Repo-specific ownership stays in each repo's CLAUDE.md.

## What can enforce this

- **GitHub** (rulesets, CODEOWNERS, required checks) is what refuses things. Not third-party.
- **[policy-bot](https://github.com/palantir/policy-bot/blob/v1.34.1/README.md)** (open source) can count reviews. Not tested with plain comments.
- **Claude Code hooks** (`claude/hooks/guard.py`) refuse or ask on: new branches, release commands, merges without `two-reviews`. Run from the playbook clone through user settings, so desktop and cloud sessions both get it in every repo. See [how-it-works.md](how-it-works.md#the-guard-hook).
- **Nothing** enforces how a session talks or how old it gets. Only `autoCompactWindow` limits the age.

Details of the sync and the review check: [how-it-works.md](how-it-works.md).
