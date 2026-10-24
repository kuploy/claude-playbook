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

To give **desktop** sessions the rules, make `~/.claude/CLAUDE.md` contain:

```
# Working instructions
Cloud sessions get these from my Claude account settings. Desktop sessions get them from the playbook file below.
@~/Devl/Projects/claude-playbook/rules/account-instructions.md
```

Desktop sessions did not get the account-settings prompt (checked 2026-10-24). Check in a **new** desktop session that it knows the "Sessions and quota" section. Done once: passed.

```sh
git clone git@github.com:ceduth/claude-playbook.git ~/Devl/Projects/claude-playbook
ln -s ~/Devl/Projects/claude-playbook/claude/agents ~/.claude/agents
```

Then merge `claude/settings.json` into `~/.claude/settings.json`. `git pull` in the clone updates the agents. If you cloned elsewhere before, move it and recreate the symlink: `mv ~/claude-playbook ~/Devl/Projects/ && ln -sfn ~/Devl/Projects/claude-playbook/claude/agents ~/.claude/agents`.

## The guard hook

`claude/hooks/guard.py` runs before a tool call and can refuse it. Claude Code runs it, not the model, so the model can't skip it.

| Rule | What it does |
|---|---|
| Never create a new branch without asking | **Asks you** on `git checkout -b`, `git switch -c`, `git branch <name>`, `git worktree add -b`, `git push -u`, and the GitHub create-branch tool. |
| Only the release owner releases | **Denies** `docker/release.sh`, `docker/build.sh` and `release.sh` in kuploy-cloud, `docker build/push ... kuploy-cloud`, and `kubectl` write verbs. A session started with `CLAUDE_RELEASE_OWNER=1` is exempt. |
| 2 reviews before merge | On `gh pr merge` and the GitHub merge tool: **allows** if the `two-reviews` status is green, **denies** if it exists and isn't, **asks** if it's missing or can't be checked (needs `gh` logged in). |

**Where it lives:** in each repo, as `.claude/settings.json` (the hook entry) and `.claude/hooks/guard.py`, copied by the sync. The command uses `$CLAUDE_PROJECT_DIR` so the path works on any machine. Repo-level, so desktop and cloud sessions read the same files. A new repo needs nothing but a line in `.github/sync.yml`.

**The release owner:** the session that runs `docker/release.sh` must be started with `CLAUDE_RELEASE_OWNER=1`, or the guard denies it.

**Self-test** (should print a JSON `"ask"`), from a repo that has the files:
```sh
echo '{"tool_name":"Bash","tool_input":{"command":"git checkout -b x"}}' | python3 .claude/hooks/guard.py
```
Then run the canary test below in a fresh session.

**When it does not protect you:**
- The hook only runs in a repo that has the files merged. Changes apply to sessions started afterwards. A repo with its own `.claude/settings.json`: merge the hook entry by hand and remove that repo from the settings entry in `.github/sync.yml`.
- Results by session type and the release-owner setting: [enforcement.md](enforcement.md).
- A wrong script path doesn't block anything. The tool call just goes ahead. Run the self-test after setup.
- It matches command text. An unusual command (`git update-ref`, a script that runs git) gets past it.
- `git push -u` also asks for an existing branch. That is the price of catching a new one.
- **Verified** on a cloud session (ariselabs.co, kuploy-cloud) and a desktop session: release commands are refused, `git checkout -b` raises an approval request, and hook files added mid-session load live. `$CLAUDE_PROJECT_DIR` resolved and `python3` was present. The merge rule is only tested with a fake `gh`; it has not run inside a real session.

## Canary test (desktop or cloud)

Run it once per kind of session after the files land in a repo. Hooks load when a session **starts**, so use a new session, not a running one.

1. Pull the repo so `.claude/settings.json` and `.claude/hooks/guard.py` are there. Check `python3 --version` works.
2. Self-test outside Claude, from the repo folder. Expect `"permissionDecision": "deny"`:
   ```sh
   echo '{"tool_name":"Bash","tool_input":{"command":"echo docker/release.sh"},"cwd":"/x"}' | python3 .claude/hooks/guard.py
   ```
3. Open the repo in a **new** session. Accept the folder-trust prompt if you get one. `/hooks` should list a PreToolUse hook (from memory).
4. Send this prompt:
   > Canary test of a PreToolUse hook. Do exactly this and nothing else: 1. Run this Bash command: `echo docker/release.sh` 2. Run this Bash command: `git checkout -b canary-test`. Run them one at a time. For each, report the exact outcome in one line. Do not retry, rephrase or work around a refusal. Then stop. Do not edit files or push anything.

| Result | Meaning |
|---|---|
| 1 is refused with "Rule: only the release owner..." | Hook runs. |
| 2 shows an approval prompt citing "never create a new branch" | Ask works. Click **Deny**. If you approve, delete it: `git checkout - && git branch -D canary-test`. |
| 1 just prints `docker/release.sh` | Hook did not run. Check the trust prompt, `/hooks`, that `python3` is on the PATH, and that the session started after the pull. |

Results: cloud (ariselabs.co) and desktop both passed.

## When Actions minutes run out

`scripts/copy-by-hand.sh` does the sync Action's job from your terminal. It reads the same `.github/sync.yml`.

```sh
cd ~/Devl/Projects/claude-playbook
scripts/copy-by-hand.sh --list                       # what it would use, changes nothing
scripts/copy-by-hand.sh --dry-run --only pull_request_template
scripts/copy-by-hand.sh --only pull_request_template # do it: one draft PR per repo
scripts/copy-by-hand.sh --only pull_request_template ceduth/roadprep   # just these repos
scripts/copy-by-hand.sh --only .claude              # the guard hook files
```

- **Needs:** SSH access to the repos, and the `gh` CLI. Without `gh` it pushes the branch and tells you which PRs to open by hand.
- **Always pass `--only`** while `two-reviews` can't run. Without it the script also copies `two-reviews.yml`, and a required check that never runs blocks every merge.
- **Don't run it twice for the same repos** while their PRs are open. Same day it fails on the existing branch. On another day it opens a duplicate PR.
- **After the PRs are merged,** a rerun says "already up to date".

## Not covered

- Per-repo write tokens (one writer per repo). Needs GitHub token setup, not files.
- Subagents on other models. Add a file in `claude/agents/` when you actually delegate to one.
