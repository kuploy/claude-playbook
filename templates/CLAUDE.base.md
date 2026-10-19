# Claude operating rules for this repo

<!-- Copied from leeram playbook: templates/CLAUDE.base.md. Repo-specific rules go BELOW the last section. -->

## 🛑 READ CODE ON TURN 1 OF ANY ARCHITECTURAL QUESTION, EVERY TIME 🛑

Never reason from a user assertion, issue body, PR description, code comment, or doc claim. Open the cited file. Verify behavior. Then answer. If you can't verify, say "couldn't verify" — don't guess.

## 🛑 NEVER CREATE A NEW BRANCH WITHOUT ASKING FIRST 🛑

Work on the branch already checked out / the existing feature branch for the task. Do NOT create, switch to, or push a new branch — including the session's assigned/default branch — unless the user has explicitly approved it **in this conversation**. One active feature branch per repo at a time. If the work seems to need its own branch, STOP and ask first.

## Other rules

- **Talk to the user simply and tersely.** Lead with the answer ("Short answers:" then focused breakdowns). Simple words, short sentences. Dense is worse than long.
- **Cleanup means cleanup**. Don't add features, refactors, or abstractions unless explicitly asked. Ask before expanding scope.
- **Cite `path:line`** before claiming any behavior. Unverifiable claims get a "couldn't verify" tag.
- **Take a position**. Don't list 3 options when you have a defensible recommendation. Offer options only when explicitly asked or when the trade-offs are genuinely close.
- **No issue/doc-wording reliance**. If a previous issue, PR, or comment makes a claim about code, verify in code before acting on it. Documentation rots; code is truth.
- **Stop-on-pushback is fast**. When the user says "stop", "not like you", "you're guessing" — stop, re-ground in code, restart.
- **Collaboration rules** (one writer per repo, 2 reviewers, message etiquette, session hygiene): see the playbook's `rules/collaboration.md`. Summary: reviews live on the PR; a session message is one line plus a link.

## Git workflow

- **One branch at a time.** Keep related work on a single feature branch — don't fan out into many. Spin up a separate branch only when work is genuinely orthogonal, and **ask first** before doing so.

1. **Branch off `dev`** for every feature / fix. Never start from `main`.
2. **PR feature → `dev`**. Land via merge once green, after **two** clean reviews (see `rules/collaboration.md`).
3. **PR `dev` → `main`** (promotion) — **only on explicit user request**. Don't open it automatically when feature PRs merge.
4. **After the promotion merges**, fast-forward `dev = main` so they stay aligned. Also user-triggered, paired with step 3.
