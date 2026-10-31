# Mechanisms

Things a session had to run something to learn. One entry each: the claim, the evidence, the date.

**What belongs here.** The bar is "I could not have reasoned this out — I had to probe it." An API that
answers differently than its docs say, a hook that reads from somewhere you would not guess, a tool that
is broken on these repos only. If you spent twenty minutes finding it and the next session would spend
twenty more, it goes here.

**What does not.** Anything already written down: `docs/how-it-works.md` explains how the system is meant
to work, `CLAUDE.md` holds this repo's own rules, and an issue holds a decision. This file is for what
none of them say. It is not a changelog and not a decision log.

**Write the mechanism, not the release state.** An entry naming where code is deployed goes stale at the
next promotion with nothing to notice — one below was false within the hour. If an entry has to name a
release state, it carries the sha it was true at, so the next reader can check it instead of trusting it.

An entry that turns out wrong gets corrected or deleted, not left standing with a caveat.

---

### `repo_pattern` reads `CLAUDE.md` from the default branch, not from the checkout

The hooks run from the working checkout, so a hook change is live on the branch you are on. The
`Pattern:` line is not: `repo_pattern` fetches `CLAUDE.md` over the API with no `?ref=`, which is the
repo's default branch. So an unmerged edit to that line changes nothing, and a merged one is live
everywhere at the next hook call.

Conflating the two is how one session concluded an unmerged branch was changing the pattern for
everybody, and nearly acted on it.

Evidence: `claude/hooks/guard.py`, `repo_pattern` — grep the name; `CLAUDE.md` describes the same split.
2026-10-30.

### Branch protection is free on a public repo and refused on a private one

On the free plan the split is visibility, not the account. `kuploy/claude-playbook` is public, so
protection is available and simply not configured; `kuploy/claude-agent-console` is private, so the
endpoints refuse outright and say why. The same split explains the Actions billing refusal.

So today no check is required anywhere and a red check blocks nothing mechanically — but that is a
choice on the playbook, not a limit. The console would have to go public or be paid for.

Evidence, both re-run 2026-10-31:

    playbook (public)  branches/main/protection -> 404 "Branch not protected";  rulesets -> []
    console  (private) both -> 403 "Upgrade to GitHub Pro or make this repository public"

Corrected the same day: the first version of this entry said 403 on both, two lines above its own
evidence line showing the 404. It would have told a session that protecting the playbook is
impossible when it is free and available. Caught in review of #108 by console-writer.

### A review's `commit_id` is not the tree the reviewer read

GitHub stamps a review with the PR head at submission time, not with whatever the reviewer actually had
open. Issue comments carry no sha at all. Every session here posts as `ceduth`, so authorship proves
nothing either. The `Head:` line a reviewer writes by hand is the only staleness signal that exists.

That is why `two-reviews` counts it and why a review without one cannot be aged.

Evidence: playbook#89, review `5717184782`. Its body says "Ran: 5a080d5"; its `commit_id` is
`515a37e`, which was pushed at 18:48:26Z, 66 seconds before the review was submitted at 18:49:32Z.
So the stamp named a tree the reviewer had not read. 2026-10-30.

    gh api repos/kuploy/claude-playbook/pulls/89/reviews --jq '.[]|{submitted_at,commit_id}'

### `gh pr edit` is broken on these repos

It fails with a Projects-classic GraphQL error, on every PR, whatever the flags. Three sessions have hit
it and worked out the same way around from scratch. Edit a PR body with the REST call instead:

    gh api -X PATCH repos/<owner>/<repo>/pulls/<n> --input body.json

2026-10-29.

### A green Vercel build is not proof of what it built with

`engines.node` in `package.json` overrides the project's Node setting in the dashboard. A READY
deployment means the build succeeded, not that it used the version you set. Checking the setting and
checking the build are two different checks.

A PR was approved on that mistake and had to be corrected by a reviewer.
Evidence: `package.json` `engines.node` against the project's configured version. 2026-10-29.

### The console's production branch is `main`, and `main` can lag `dev` by weeks

Vercel deploys `main`; every other branch gets a preview. `dev` is where work lands, and it is promoted
only when Ed asks. So code that exists on `dev` is not running in production, and reading `dev` to
explain a production behaviour gives the wrong answer.

That is what console#107 turned out to be: a staleness suffix was reported missing from a status, and the
code producing it on `dev` had the feature while `main` had no `head` parameter at all. The gap was 17
commits.

That gap is closed: `dev` was promoted to `main` at `0d0d121` on 2026-10-31, and the two are identical
as this is written. The mechanism is what to keep — the next gap opens with the next merge to `dev`.

Evidence: `kuploy/claude-agent-console/CLAUDE.md`, the promotion section;
`gh api repos/kuploy/claude-agent-console/compare/main...dev` → `identical`. 2026-10-31.

### The Claude GitHub App is installed on the `kuploy` org, for all repositories

A session that cannot reach a repo through it is usually not missing an install. The common cause is a
session source still named `ceduth/<repo>`: that is a redirect name after the move to `kuploy`, and
`add_repo` and `subscribe_pr_activity` fail on it. The move is recorded in #32; nothing else says the old
names break.

Reported by the advisor session after re-deriving it wrongly a second time; see #104's body for the
three cases. Not re-verified here. 2026-10-30.
