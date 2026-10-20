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
| `rules/collaboration.md` | nowhere | people, as a reference | nobody |

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
