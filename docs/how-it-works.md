# How it works

## The picture

- **Rules the model follows** live in `rules/account-instructions.md`. Desktop sessions import it from `~/.claude/CLAUDE.md`. Cloud sessions read the same text pasted into the Claude account settings.
- **This repo holds files that tools read.** A robot copies them into your other repos.
- Nothing here is read by a session unless it is copied somewhere first.

## Who reads what

| File in this repo | Copied to | Read by | Copied by |
|---|---|---|---|
| `sync/pull_request_template.md` | `.github/pull_request_template.md` in each repo | GitHub, when a PR opens | sync Action |
| `sync/two-reviews.yml` | `.github/workflows/two-reviews.yml` in each repo | GitHub Actions | sync Action |
| `claude/agents/chore.md` | `~/.claude/agents/` on each machine | Claude Code, at session start | you, once (symlink) |
| `claude/settings.json` | merged into `~/.claude/settings.json` | Claude Code | you, once |
| `sync/claude-settings.json` | `.claude/settings.json` in each repo | Claude Code (desktop and cloud), at session start | sync Action |
| `claude/hooks/guard.py` | `.claude/hooks/guard.py` in each repo | Claude Code, before tool calls | sync Action |
| `claude/hooks/notes.py` | `.claude/hooks/notes.py` in each repo | Claude Code, at start and after a compaction | sync Action |
| `scripts/cloud-setup.sh` | the cloud environment's Setup script | the container, when it is built | you, on each change |
| `rules/account-instructions.md` | desktop: imported by `~/.claude/CLAUDE.md`; cloud: pasted into account settings | Claude Code, at session start | you, on each change |

## The sync Action (disabled)

[repo-file-sync-action](https://github.com/BetaHuhn/repo-file-sync-action) copies the files in `.github/sync.yml` into the other repos as PRs. It is switched off (Actions minutes). Use `scripts/copy-by-hand.sh` instead (below).

- **New repo:** add its name to `.github/sync.yml`.
- **A repo wants its own version of a file:** merge once, then remove that repo from the list for that file.
- **Sync PRs need one check, not two reviews:** the file's blob hash matches the playbook (`git hash-object sync/<file>`). Post it once as a comment. Any difference, and the 2-review rule applies. (Owner decision, 2026-10-20.)
- **If the Action is turned on again:** it needs a `SYNC_TOKEN` secret (classic PAT, `repo` scope; you have three owners).

## The two-reviews check

Blocks a merge until two reviewers have approved. Your sessions all act as you, so it counts comments, not accounts.

A reviewer posts one comment:

```
Reviewer: <session or person name>
Verdict: approve
Ran: <what you ran>
Would catch: <what that would have caught>
```

- Two different `Reviewer:` names, each with all four lines.
- Counts only after the last push. A new push voids old reviews. "The push" is when GitHub
  received the head (earliest check suite for the sha), not when it was committed — a commit
  held locally for an hour would otherwise count reviews written during that hour. With no
  check suites it falls back to the committer date.
- A reviewer's latest comment wins.
- Only people with write access count.
- Result: a commit status `two-reviews` on the PR head (`success` at 2, else `pending`).
- To enforce it: ruleset on `dev` and `main` requiring `two-reviews`. Manual, per repo.

**Limits:** it trusts the `Reviewer:` name and does not check that `Ran:` is true. Not yet run on a real PR. Not live (Actions billing limit).

## Per machine, once

Desktop sessions don't get the account-settings prompt. Give them the rules with `~/.claude/CLAUDE.md`:

```
# Working instructions
Cloud sessions get these from my Claude account settings. Desktop sessions get them from the playbook file below.
@~/Devl/Projects/claude-playbook/rules/account-instructions.md
```

```sh
git clone git@github.com:kuploy/claude-playbook.git ~/Devl/Projects/claude-playbook
ln -s ~/Devl/Projects/claude-playbook/claude/agents ~/.claude/agents
```

Then merge `claude/settings.json` into `~/.claude/settings.json`.

## Per cloud environment, once

A cloud session with several repos starts in `/home/user`. No repo's `.claude/settings.json` loads there, so the guard and the notes hook don't run (#42). The sign: the session's compaction threshold reads "model-default", not "settings".

Fix: paste `scripts/cloud-setup.sh` into the environment's settings, under Setup script. It writes `/home/user/.claude/settings.json` and a launcher that runs the hooks from the playbook clone, wherever it sits under `/home/user`. A session without the playbook as a source runs no hooks. New sessions only. Check with the canary test below. When `sync/claude-settings.json` changes, change the script too and paste it again.

The notes hook: at start and after each compaction it prints the path of `~/.claude/notes/<session_id>.md` and what it holds. Why the file and what goes in it: `rules/account-instructions.md`, "Notes file". Its `SessionStart` hook pulls the clone at each session start, so you no longer pull by hand. Check in a **new** desktop session: it should know the "Sessions and quota" section (passed 2026-10-24).

## The guard hook

`claude/hooks/guard.py` runs before a tool call and can refuse it. Claude Code runs it, not the model.

| Rule | What it does |
|---|---|
| Scope gate on new branches (#13) | On `git checkout -b`, `switch -c`, `branch <name>`, `worktree add -b`, `push -u` and the GitHub create-branch tool: **denies** a name without an issue number (`feat/<n>-slug`) or a repo with another open PR of yours; **allows** if issue `<n>` (in that repo, else in claude-playbook) is a sub-issue of an open epic labelled `scope:frozen`; **asks you** otherwise or if GitHub can't be reached. To add scope, add the issue to the epic yourself |
| Pattern branches (#29) | Only in a repo whose CLAUDE.md has a `Pattern:` line, in place of one open PR per repo: **denies** a branch that isn't `feat/<role>/<n>-slug`, a branch for the lead in lead-writer and release-train (the lead doesn't write), a second open branch for a role, and more roles than the pattern's writers (release-train 2, others 1). No line, or a name it doesn't know: the one-PR rule, as before |
| Only the release owner releases | **Denies** `docker/release.sh`, `build.sh`/`release.sh` in kuploy-cloud, `docker build/push ... kuploy-cloud`, `kubectl` writes. `CLAUDE_RELEASE_OWNER=1` exempts a session |
| 2 reviews before merge | On a merge: **allows** if `two-reviews` is green, **denies** if red. If missing, it counts the reviews itself and **denies** under two; **asks** only if GitHub can't be read (#30). With `CLAUDE_REVIEW_GATE=local` it counts the reviews itself and **denies** under two: see [enforcement.md](enforcement.md#claude_review_gate) |
| Short PR bodies | **Denies** a PR body over 15 lines (footer not counted) |
| Review format | **Denies** a `Reviewer:` comment missing a line or with more than 5 lines after the block |
| Check-in after hand-off | After a PR opens, **reminds** the session to subscribe and schedule a check-in |

It lives in each repo as `.claude/settings.json` and `.claude/hooks/guard.py` (copied by the sync), so desktop and cloud read the same files. A new repo needs a line in `.github/sync.yml`.

**Gaps:**
- Only runs in a repo that has the files, and only in sessions started after they landed.
- Matches command text. `git update-ref` or a script that runs git gets past it.
- `git push -u` of a branch already on the remote is not gated. A first push outside a frozen epic asks again, even if you approved its `checkout -b`.
- A branch must read `<prefix>/<n>-<word>`. `feat/2026-10-25-x` or `7-3` is denied as having no issue number.
- The open-PR check counts PRs by the GitHub user, and all cloud sessions share yours. One writer per repo makes that right. Under a pattern, the role is whatever the branch name says: any session can push `feat/<someone-else>/...`.
- The `Pattern:` line is read from the repo's default branch on GitHub, not from your checkout.
- The line must start the line, plain: `**Pattern:** ...` is not read, so the repo silently keeps the one-PR rule. A `Pattern:` line at the start of a line inside a code block *is* read. Without `lead = <role>`, nothing stops the lead from writing.
- Role names compare without case. Under a pattern every branch needs a role, hotfixes too: use `feat/<role>/<n>-slug`, not `fix/<n>-slug`.
- The epic home (claude-playbook) is asked only when the repo has no issue `<n>` of its own.
- A frozen-epic branch is auto-approved only as a bare `git [-C dir] <sub> ...` of plain words: no `-c`, env prefix, quote, `$`, glob, backtick or redirect, and only the options `-b -B -c -C -u -t --set-upstream --track --no-track` after the subcommand (so no `push --receive-pack`/`--exec`, which run a program). Otherwise the normal prompt runs.
- If GitHub can't say whether the repo has issue `<n>`, the guard asks rather than trying claude-playbook.
- Silent bypasses: `bash -c`, `env git`, `/usr/bin/git`, `git push origin HEAD:<new>` without `-u`, `gh api .../git/refs`. A pushed branch with no PR doesn't count as open.
- Branches made inside a script (like `copy-by-hand.sh`) aren't seen.
- A wrong script path blocks nothing. Run the self-test after setup.
- Results by session type: [enforcement.md](enforcement.md).

**Self-test** (should print `"deny"`: no issue number), from a repo that has the files:
```sh
echo '{"tool_name":"Bash","tool_input":{"command":"git checkout -b x"}}' | python3 .claude/hooks/guard.py
```
In a repo with a `Pattern:` line, `git checkout -b feat/9-x` (no role) should also print `"deny"`.

**Canary test** (once per session type, in a **new** session): ask it to run `echo docker/release.sh`, then `git checkout -b canary-test`, one at a time, and report each outcome without retrying.
- First refused ("only the release owner") → hook runs.
- Second shows an approval prompt → ask works. Click **Deny**.
- First just prints → hook did not run. Check the folder-trust prompt, `python3` on PATH, and that the session started after the files landed.

Passed on cloud and desktop.

## When Actions minutes run out

`scripts/copy-by-hand.sh` does the sync Action's job from your terminal, reading `.github/sync.yml`. Needs SSH access and the `gh` CLI.

```sh
scripts/copy-by-hand.sh --list                         # show plan, change nothing
scripts/copy-by-hand.sh --dry-run --only .claude       # rehearse
scripts/copy-by-hand.sh --only .claude                 # one draft PR per repo
scripts/copy-by-hand.sh --only .claude ceduth/roadprep # just these repos
```

- Always pass `--only`: without it the script also copies `two-reviews.yml`, and a required check that never runs blocks every merge.
- Don't run it twice while PRs are open: you get a duplicate PR. A same-day rerun adds the time to the branch name instead of failing.

## Not covered

- Per-repo write tokens (one writer per repo). Needs GitHub token setup, not files.
- Subagents on other models. Add a file in `claude/agents/` when you delegate to one.
