Pattern: lead-writer, lead = lead

# claude-playbook

This repo holds the rules the other repos' sessions work by. Everything in
`rules/account-instructions.md` is Ed's account instructions, and the hooks in `claude/hooks/`
enforce a part of them. So a change here changes how sessions elsewhere behave.

## Two things are different here

**A rule only takes effect when Ed re-pastes it.** Cloud sessions read the account instructions
from his Claude account settings; desktop sessions read them through his global `CLAUDE.md`. Neither
reads this repo. Merging a change to `rules/account-instructions.md` publishes the text and changes
nothing until he pastes it. So a PR that edits those rules says in its body that a re-paste is owed,
and the session that merged it tells him — batched, not once per PR.

**A hook change reaches sessions on its own, but not at the same time in both places**, and never
by a re-paste. There is no staging either, so a broken `claude/hooks/guard.py` blocks work in every
repo at once. That is why the suites exist and why CI runs them (#88).

On the desktop, `~/.claude/settings.json` runs the hooks out of this working checkout by absolute
path, and a `SessionStart` hook does `git pull -q --ff-only` on it first. So a merged change is live
at the next session start — unless the checkout is sitting on a feature branch, when the pull is a
no-op and the session runs whatever that branch has.

In the cloud, `scripts/cloud-setup.sh:26` clones this repo to `~/.claude/playbook` only when
`$PB/.git` is absent. Nothing ever pulls it. A container created before your change keeps the old
hooks until it is recreated; a new one gets `main` at clone time. So after merging a hook change,
assume long-lived cloud containers are still on the old one.

When a change touches both — the rule text and the hook that enforces it — they land in the same PR.
Otherwise the laxer of the two decides for however long the gap lasts.

## Git

This repo has one long-lived branch: `main`. There is no `dev`, so the account rules' "branch off
`dev`, PR into `dev`" does not apply — branch off `main` and PR into `main`. Because the base is the
default branch, `Closes #N` in a PR body does fire here. It does not in the repos that use `dev`.

Branches are `feat/<role>/<n>-slug`, which is what `claude/hooks/guard.py`'s `ROLE_BRANCH` matches.

## Tests

`.github/workflows/tests.yml` loops over every `tests/test_*.py`, so a new suite needs no workflow
edit — adding the file is enough. Run them the way CI does:

    for t in tests/test_*.py; do python3 -I "$t"; done

`-I` matters: these suites read scripts out of the repo, and without it an import picks up whatever
sits in the current directory.
