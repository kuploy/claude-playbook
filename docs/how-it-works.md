# How it works

## The picture

- **Rules the model follows** live in your Claude account settings. One home. This repo does not hold them.
- **This repo holds files that tools read.** A robot copies them into your other repos.
- Nothing here is read by a session unless it is copied somewhere first.

## Who reads what

| File in this repo | Copied to | Read by | Copied by |
|---|---|---|---|
| `sync/pull_request_template.md` | `.github/pull_request_template.md` in each repo | GitHub, when a PR opens | sync Action |
| `sync/two-reviews.yml` | `.github/workflows/two-reviews.yml` in each repo | GitHub Actions | sync Action |
| `claude/agents/chore.md` | `~/.claude/agents/` on each machine | Claude Code, at session start | you, once (symlink) |
| `claude/settings.json` | merged into `~/.claude/settings.json` | Claude Code | you, once |
| `claude/hooks/guard.py` | stays in your `~/claude-playbook` clone | Claude Code, before tool calls | nobody (settings point at it) |
| `rules/collaboration.md` | nowhere | people, as a reference | nobody |
| `rules/account-instructions.md` | nowhere | people: backup of the account prompt | nobody |

## The sync Action

[repo-file-sync-action](https://github.com/BetaHuhn/repo-file-sync-action), set up in `.github/workflows/sync.yml` and `.github/sync.yml`.

1. You push to `main` here.
2. The Action reads `.github/sync.yml`: which files go to which repos.
3. For each repo where the file is missing or different, it opens a PR there.
4. You merge that PR. Done.

- **New repo:** add its name to `.github/sync.yml`.
- **A repo wants its own version of a file:** merge once, then remove that repo from the list for that file. After that the file belongs to the repo.
- **Token:** add a repo secret `SYNC_TOKEN` (a PAT that can write contents and PRs on the target repos). A fine-grained PAT covers one owner only. You have three (`kuploy`, `ceduth`, `leeram-hq`), so use a classic PAT with `repo` scope, or one token and one step per owner. Until the secret exists, the sync run fails. That is expected.
- **Review rule for sync PRs (exception to the 2-review rule).** A PR that only copies files from the playbook needs one check: the file's git blob hash matches the playbook's (`git hash-object sync/<file>`). Post it as a review comment, once. No second review. Any difference from the source, and the full 2-review rule applies. The source file itself is reviewed once, in the playbook. Decided by the repo owner, 2026-10-20.
- **If `two-reviews` is required in a repo,** it will still block a sync PR that has only one review. Exempt the sync PRs there, or post a second comment.

## The two-reviews check

Blocks a merge until two reviewers have approved. It does not need separate GitHub accounts, because your sessions all act as you.

**How a reviewer approves.** Post one comment (or review) on the PR:

```
Reviewer: <session or person name>
Verdict: approve
Ran: <what you ran>
Would catch: <what that would have caught>
```

**What counts:**
- Two different `Reviewer:` names, each with `Verdict: approve`, `Ran:` and `Would catch:` filled in.
- Posted after the last push. Push code and old reviews stop counting.
- A reviewer's latest comment wins. A later "changes requested" cancels their approval.
- Only people with write access count.

**What it does:** posts a commit status named `two-reviews` on the PR head: `success` at 2, `pending` below.

**Turn it on, per repo, once:** ruleset for `dev` and `main` → require status check `two-reviews`. This is manual. The Action cannot do it.

**Limits:**
- It trusts the `Reviewer:` name. One session can write two names. It makes skipping visible, not impossible.
- It does not judge whether `Ran:` is true.
- Tested with mocked data only. Not yet run on a real PR.

## Per machine, once

```sh
git clone git@github.com:ceduth/claude-playbook.git ~/claude-playbook
ln -s ~/claude-playbook/claude/agents ~/.claude/agents
```

Then merge `claude/settings.json` into `~/.claude/settings.json`. `git pull` in the clone updates the agents.

## The guard hook

`claude/hooks/guard.py` runs before a tool call and can refuse it. Claude Code runs it, not the model, so the model can't skip it.

| Rule | What it does |
|---|---|
| Never create a new branch without asking | **Asks you** on `git checkout -b`, `git switch -c`, `git branch <name>`, `git worktree add -b`, `git push -u`, and the GitHub create-branch tool. |
| Only the release owner releases | **Denies** `docker/release.sh`, `docker/build.sh` and `release.sh` in kuploy-cloud, `docker build/push ... kuploy-cloud`, and `kubectl` write verbs. A session started with `CLAUDE_RELEASE_OWNER=1` is exempt. |
| 2 reviews before merge | On `gh pr merge` and the GitHub merge tool: **allows** if the `two-reviews` status is green, **denies** if it exists and isn't, **asks** if it's missing or can't be checked (needs `gh` logged in). |

**Self-test** (should print a JSON `"ask"`):
```sh
echo '{"tool_name":"Bash","tool_input":{"command":"git checkout -b x"}}' | python3 ~/claude-playbook/claude/hooks/guard.py
```
Then in a fresh session, ask it to run `git checkout -b test`. You should get a prompt.

**When it does not protect you:**
- The hook only runs where it's configured: your Mac's `~/.claude/settings.json` (merge `claude/settings.json`), or a repo's `.claude/settings.json` for cloud sessions. Changes apply to sessions started afterwards.
- A wrong script path doesn't block anything. The tool call just goes ahead. Run the self-test after setup.
- It matches command text. An unusual command (`git update-ref`, a script that runs git) gets past it.
- `git push -u` also asks for an existing branch. That is the price of catching a new one.
- Tested with a fake `gh` only. Not yet run inside a real session.

## When Actions minutes run out

`scripts/copy-by-hand.sh` does the sync Action's job from your terminal. It reads the same `.github/sync.yml`.

```sh
cd ~/claude-playbook
scripts/copy-by-hand.sh --list                       # what it would use, changes nothing
scripts/copy-by-hand.sh --dry-run --only pull_request_template
scripts/copy-by-hand.sh --only pull_request_template # do it: one draft PR per repo
scripts/copy-by-hand.sh --only pull_request_template ceduth/roadprep   # just these repos
```

- **Needs:** SSH access to the repos, and the `gh` CLI. Without `gh` it pushes the branch and tells you which PRs to open by hand.
- **Always pass `--only`** while `two-reviews` can't run. Without it the script also copies `two-reviews.yml`, and a required check that never runs blocks every merge.
- **Don't run it twice for the same repos** while their PRs are open. Same day it fails on the existing branch. On another day it opens a duplicate PR.
- **After the PRs are merged,** a rerun says "already up to date".

## Not covered

- Per-repo write tokens (one writer per repo). Needs GitHub token setup, not files.
- Subagents on other models. Add a file in `claude/agents/` when you actually delegate to one.
