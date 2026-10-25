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
git clone git@github.com:ceduth/claude-playbook.git ~/Devl/Projects/claude-playbook
ln -s ~/Devl/Projects/claude-playbook/claude/agents ~/.claude/agents
```

Then merge `claude/settings.json` into `~/.claude/settings.json`. Its `SessionStart` hook pulls the clone at each session start, so you no longer pull by hand. Check in a **new** desktop session: it should know the "Sessions and quota" section (passed 2026-10-24).

## The guard hook

`claude/hooks/guard.py` runs before a tool call and can refuse it. Claude Code runs it, not the model.

| Rule | What it does |
|---|---|
| No new branch without asking | **Asks you** on `git checkout -b`, `switch -c`, `branch <name>`, `worktree add -b`, `push -u`, and the GitHub create-branch tool |
| Only the release owner releases | **Denies** `docker/release.sh`, `build.sh`/`release.sh` in kuploy-cloud, `docker build/push ... kuploy-cloud`, `kubectl` writes. `CLAUDE_RELEASE_OWNER=1` exempts a session |
| 2 reviews before merge | On a merge: **allows** if `two-reviews` is green, **denies** if red, **asks** if missing |
| Short PR bodies | **Denies** a PR body over 15 lines (footer not counted) |
| Review format | **Denies** a `Reviewer:` comment missing a line or with more than 5 lines after the block |
| Check-in after hand-off | After a PR opens, **reminds** the session to subscribe and schedule a check-in |

It lives in each repo as `.claude/settings.json` and `.claude/hooks/guard.py` (copied by the sync), so desktop and cloud read the same files. A new repo needs a line in `.github/sync.yml`.

**Gaps:**
- Only runs in a repo that has the files, and only in sessions started after they landed.
- Matches command text. `git update-ref` or a script that runs git gets past it.
- `git push -u` asks even for an existing branch.
- A wrong script path blocks nothing. Run the self-test after setup.
- Results by session type: [enforcement.md](enforcement.md).

**Self-test** (should print `"ask"`), from a repo that has the files:
```sh
echo '{"tool_name":"Bash","tool_input":{"command":"git checkout -b x"}}' | python3 .claude/hooks/guard.py
```

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
- Don't run it twice while PRs are open (same-day branch clash, or a duplicate PR on another day).

## Not covered

- Per-repo write tokens (one writer per repo). Needs GitHub token setup, not files.
- Subagents on other models. Add a file in `claude/agents/` when you delegate to one.
