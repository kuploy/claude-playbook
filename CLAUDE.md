Pattern: peer-review, lead = lead

# claude-playbook

This repo holds the rules the other repos' sessions work by. Everything in
`rules/account-instructions.md` is Ed's account instructions, and the hooks in `claude/hooks/`
enforce a part of them. So a change here changes how sessions elsewhere behave.

## Two things are different here

**A rule change reaches desktop sessions by itself and cloud sessions only when Ed re-pastes.**
`~/.claude/CLAUDE.md:3` is an `@` import of `rules/account-instructions.md` *in this checkout*, so a
desktop session reads the merged file at its next start, by the same `SessionStart` pull described
for hooks below. Cloud sessions read the text from his Claude account settings, which nothing here
writes to. So merging a rule change makes desktop strict and leaves cloud lax until he pastes, and
the gap runs in whichever direction the change went. A PR that edits those rules says in its body
that a re-paste is owed, and the session that merged it tells him — batched, not once per PR.

**A hook change reaches every session on its own, desktop and cloud alike**, and never by a
re-paste. Both places pull this repo at session start: `~/.claude/settings.json` on the desktop runs
the hooks out of this working checkout by absolute path, and `scripts/cloud-setup.sh:42` installs the
same `SessionStart` pull against its `~/.claude/playbook` clone. So a merged hook change is live at
the next session start in both. There is no staging, so a broken `claude/hooks/guard.py` blocks work
in every repo at once. That is why the suites exist and why CI runs them (#88).

Two ways a session can still be running an old hook, and neither says so:

- **Both pulls throw away their output and their exit status.** A diverged local `main`, a dead
  network and a missing clone all look exactly like success. Nothing in the session reports it.
- **On the desktop, the checkout may be on a feature branch.** The pull then fast-forwards *that*
  branch and `main`'s change never arrives. The cloud clone is `--depth 1` on `main`, so it has that
  problem only if someone checks something else out in it.

So after merging a hook change, the thing to check is not whether the pull runs — it does — but
whether the session that matters got it.

When a change touches both — the rule text and the hook that enforces it — they land in the same PR.
Otherwise the laxer of the two decides for however long the gap lasts.

## Git

This repo has one long-lived branch: `main`. There is no `dev`, so the account rules' "branch off
`dev`, PR into `dev`" does not apply — branch off `main` and PR into `main`. Because the base is the
default branch, `Closes #N` in a PR body does fire here. It does not in the repos that use `dev`.

Branches are `feat/<role>/<n>-slug`, which is what `claude/hooks/guard.py`'s `ROLE_BRANCH` matches:
`^feat/([A-Za-z0-9._-]+)/\d+-[A-Za-z]`. The slug must start with a letter: `feat/lead/95-2fa` is
refused as having no role. Worse if one is already open — `role_of` falls back to the whole ref, so
such a branch counts as a writer of its own and eats a slot nobody can see.

**Why `peer-review` and not `lead-writer`.** `patterns/lead-writer.md` gives the lead no code on the
repo, and `PATTERNS["lead-writer"]` is `(1, False)`, so `check_role:587` denies `feat/lead/<n>-slug`
outright. There is no separate writer session for this repo — the lead writes here, and did for #89
and #95 — so `lead-writer` would lock out the only session that writes. `peer-review` is what this
repo already does: one writer, two reviews before merge from sessions that aren't the writer. Ed
settled this on 2026-10-30, against the `lead-writer` he first named on #92.

`lead = lead` reads oddly here, because `peer-review` calls the session that reports to Ed the
*writer*, not the lead. The field names that role whatever the session's own role name is, and this
one's is `lead` — so `feat/lead/<n>-slug` is the writer's branch on this repo, and `(1, True)` lets
it through. Keep the line on the first line of this file by convention only: `repo_pattern:566`
searches with `re.M`, so a second `Pattern:` anywhere below would silently win.

## Tests

`.github/workflows/tests.yml` loops over every `tests/test_*.py`, so a new suite needs no workflow
edit — adding the file is enough. Run them the way CI does:

    for t in tests/test_*.py; do python3 -I "$t"; done

`-I` matters: these suites read scripts out of the repo, and without it an import picks up whatever
sits in the current directory.
