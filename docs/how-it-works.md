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
| `claude/settings.json` | merged into `~/.claude/settings.json` | Claude Code | you, once (again after #42: it now carries the hooks) |
| `claude/hooks/guard.py`, `notes.py`, `plain.py` | nowhere: they run from your copy of the playbook (see [Setting up](#setting-up)) | Claude Code, before tool calls / at start and after a compaction / when a turn ends | not copied; each new session updates your copy |
| `scripts/cloud-setup.sh` | the cloud environment's Setup script, with your config pasted in | the container, when it is built | you, once per environment |
| your `config.json` (not in this repo: see [Your config](#your-config)) | `~/.claude/playbook-config.json` | the guard, the notes reminder and the reply check | you, once per computer (a link) and once per environment (in the Setup script) |
| `rules/account-instructions.md` | desktop: imported by `~/.claude/CLAUDE.md`; cloud: pasted into account settings | Claude Code, at session start | you, on each change |

## The sync Action (disabled)

[repo-file-sync-action](https://github.com/BetaHuhn/repo-file-sync-action) copies the files in `.github/sync.yml` into the other repos as PRs. It is switched off (Actions minutes). Use `scripts/copy-by-hand.sh` instead (below).

- **New repo:** add it to `repos` in your config. The Action needs the list in `.github/sync.yml` too, if it is ever turned on again.
- **A repo wants its own version of a file:** merge once, then remove that repo from the list for that file.
- **Sync PRs need one check, not two reviews:** the file's blob hash matches the playbook (`git hash-object sync/<file>`). Post it once as a comment. The guard runs the same check before a merge and lets a matching PR through. Any difference, and the 2-review rule applies. (Owner decision, 2026-10-20.)
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

## Your config

The playbook is the same for everyone. What is yours lives in one file, `config.json`, in a private repo of your own named `claude-playbook-config`. No secrets go in it.

```json
{
  "config_repo": "your-org/claude-playbook-config",
  "epic_home": "your-org/your-planning-repo",
  "repos": ["your-org/app", "your-org/docs"],
  "owner_only": {
    "allow_env": "CLAUDE_RELEASE_OWNER",
    "message": "Only the release session runs this. Start that session with CLAUDE_RELEASE_OWNER=1.",
    "commands": [
      {"match": "scripts/release\\.sh"},
      {"match": "\\bkubectl\\b.*\\b(apply|delete|scale)\\b"},
      {"match": "(^|[\\s/])build\\.sh\\b", "only_in": "your-app"}
    ]
  },
  "plain_language": {
    "words": ["risk", "surface", "failure mode", "semantics", "consequence"],
    "phrases": ["\\bnot just\\b.*\\bbut\\b"],
    "max_words": 30
  }
}
```

- **`config_repo`**: this repo's own name. Cloud sessions with a token use it to read the latest settings ([below](#when-your-settings-change)).
- **`repos`**: the repos `scripts/copy-by-hand.sh` copies files into.
- **`owner_only`**: commands only one session may run. The guard refuses them in every session except one that has the `allow_env` variable set to `1`. `match` is a regular expression on the command. With `only_in`, the command counts only when that text is in the folder name or the command. Setting the variable for the owner's session: [enforcement.md](enforcement.md#the-owner-only-switch).
- **`epic_home`**: the repo where your epics live. The new-branch check looks there for an issue the current repo doesn't have.
- **`plain_language`**: what the reply check flags in a chat reply (#48). `words` match whole words, plurals too. `phrases` are regular expressions. `max_words` is the longest sentence allowed. A hit sends the reply back once, with the lines quoted. Code, tables and link addresses are not checked. No `plain_language`: no check. A part of the wrong type is skipped.

Every part is optional. With no config file, nothing is refused as owner-only, and the new-branch check only looks in the current repo. Each new session says so when the file is missing, can't be read, lists no owner-only commands, or has a field of the wrong type. A wrong-typed field fails closed: the command stays refused everywhere, with no exemption. If you have no owner-only commands, that one line appears in every session; it is a reminder, not an error.

## Setting up

The checks (the guard, the notes reminder and the reply check) run from a copy of this repo. You set that copy up once per computer and once per cloud environment. After that, every session gets the checks, in every repo. Each new session updates the copy first, so a change to the checks reaches everyone without you doing anything.

### On your computer, once

1. Get the playbook:
   ```sh
   git clone git@github.com:kuploy/claude-playbook.git ~/Devl/Projects/claude-playbook
   ln -s ~/Devl/Projects/claude-playbook/claude/agents ~/.claude/agents
   ```
2. Give desktop sessions the rules. Put this in `~/.claude/CLAUDE.md`:
   ```
   # Working instructions
   Cloud sessions get these from my Claude account settings. Desktop sessions get them from the playbook file below.
   @~/Devl/Projects/claude-playbook/rules/account-instructions.md
   ```
3. Turn on the checks: add the `hooks` part of `claude/settings.json` to `~/.claude/settings.json`. The first run keeps a backup (`settings.json.bak`, never overwritten later) and adds only the hooks you are missing; the rest of your file is untouched:
   ```sh
   python3 - <<'EOF'
   import json, os, shutil
   u = os.path.expanduser("~/.claude/settings.json")
   p = os.path.expanduser("~/Devl/Projects/claude-playbook/claude/settings.json")
   os.makedirs(os.path.dirname(u), exist_ok=True)
   if os.path.exists(u) and not os.path.exists(u + ".bak"): shutil.copy(u, u + ".bak")
   mine, pb = (json.load(open(u)) if os.path.exists(u) else {}), json.load(open(p))
   h = mine.setdefault("hooks", {})
   for ev, entries in pb["hooks"].items():
       have = h.setdefault(ev, [])
       have += [e for e in entries if e not in have]
   json.dump(mine, open(u, "w"), indent=2)
   EOF
   ```
   Check: both lines must show a `guard.py` path. An empty list means no session on this computer is guarded.
   ```sh
   python3 -c "import json,os;h=json.load(open(os.path.expanduser('~/.claude/settings.json'))).get('hooks',{});[print(e,[x.get('command', x.get('type')) for m in h.get(e,[]) for x in m['hooks']]) for e in ('PreToolUse','PostToolUse')]"
   ```
4. Give the checks your config. Get your config repo and link its file:
   ```sh
   git clone git@github.com:your-org/claude-playbook-config.git ~/Devl/Projects/claude-playbook-config
   ln -s ~/Devl/Projects/claude-playbook-config/config.json ~/.claude/playbook-config.json
   ```
   After that, each new session pulls this clone first, so a change to `config.json` reaches the next session. Nothing to do.
5. Open a new session and run the canary test (below).

### In the cloud, once per environment

1. Copy `scripts/cloud-setup.sh`. Replace the `{}` between the two `CONFIG` lines with the contents of your `config.json`.
2. In the environment's settings, paste the result under **Setup script**.
3. Open a new session and run the canary test (below).

Only sessions started afterwards get the checks.

#### When your settings change

Cloud sessions use the settings you pasted. When you change `config.json`, pick one way to pass on the change:

- **Paste again.** Repeat steps 1 and 2. Nothing else to set up.
- **Or add a token once, and never paste again.** Each new session then reads the latest `config.json` itself.
  1. On GitHub: **Settings**, **Developer settings**, **Fine-grained tokens**, **Generate new token**. Set **Resource owner** to the account that owns `claude-playbook-config` (your organization, if it is there). Under **Expiration**, pick **No expiration** if offered, else the longest allowed. Under repository access, pick only `claude-playbook-config`. Under permissions, set **Contents** to **Read-only**. If your organization asks for approval, an owner approves it in the organization's settings, under **Personal access tokens**.
  2. In the cloud environment's settings, add an environment variable: `PLAYBOOK_CONFIG_TOKEN=` followed by the token. Never paste the token into a chat.
  3. Check that your `config.json` has `config_repo` set (see [Your config](#your-config)). Paste the Setup script one last time, so the session knows where to look.

  If the token stops working (it expired or was deleted), sessions go on with the last pasted settings, and say so when they start. Make a new token and replace the variable.

With a token, the pasted script still holds your full settings, on purpose. It is the backup: if the token stops working, your blocks and checks stay on, and the session tells you. While the token works, an old pasted copy does no harm, because each session replaces it with the latest.

Either way, paste again when `cloud-setup.sh` itself changes.

### Old copies in repos

Before #42, each repo got its own copy of the checks, in its `.claude/` folder. Those copies no longer update, and they run next to the real ones. Delete them: `.claude/hooks/`, and the `hooks` part of `.claude/settings.json`.

Before you merge a deletion, run the check in step 3 on every computer that works in that repo. If it shows empty lists, the repo copy is the only guard there, and deleting it switches the checks off with no message.

### The notes reminder

When a session starts, and again after it compacts (summarises its own history to make room), it is told where its notes file is and shown what's in it. Why a session keeps notes: `rules/account-instructions.md`, "Notes file".

## The guard hook

`claude/hooks/guard.py` runs before a tool call and can refuse it. Claude Code runs it, not the model.

| Rule | What it does |
|---|---|
| Scope gate on new branches (#13) | On `git checkout -b`, `switch -c`, `branch <name>`, `worktree add -b`, `push -u` and the GitHub create-branch tool: **denies** a name without an issue number (`feat/<n>-slug`) or a repo with another open PR of yours; **allows** if issue `<n>` (in that repo, else in claude-playbook) is a sub-issue of an open epic labelled `scope:frozen`; **asks you** otherwise or if GitHub can't be reached. To add scope, add the issue to the epic yourself |
| Pattern branches (#29) | Only in a repo whose CLAUDE.md has a `Pattern:` line, in place of one open PR per repo: **denies** a branch that isn't `feat/<role>/<n>-slug`, a branch for the lead in lead-writer and release-train (the lead doesn't write), a second open branch for a role, and more roles than the pattern's writers (release-train 2, others 1). No line, or a name it doesn't know: the one-PR rule, as before |
| Owner-only commands (#44) | **Denies** the commands in your config's `owner_only`. A session with the `allow_env` variable set to `1` is exempt. No config: denies none |
| 2 reviews before merge | On a merge: **allows** if `two-reviews` is green, **denies** if red. If missing, it counts the reviews itself and **denies** under two; **asks** only if GitHub can't be read (#30). With `CLAUDE_REVIEW_GATE=local` it counts the reviews itself and **denies** under two: see [enforcement.md](enforcement.md#claude_review_gate) |
| Short PR bodies | **Denies** a PR body over 15 lines (footer not counted) |
| Review format | **Denies** a `Reviewer:` comment missing a line or with more than 5 lines after the block |
| Check-in after hand-off | After a PR opens, **reminds** the session to subscribe and schedule a check-in |

It runs from your copy of the playbook, so every repo gets it with nothing to copy (#42). See [Setting up](#setting-up).

**Gaps:**
- Only runs on a computer or cloud environment that has been set up, and only in sessions started after that.
- A session can edit or delete its own copy of the playbook, and so switch its checks off.
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

**Self-test** (should print `"deny"`: no issue number), from inside any repo. In the cloud the copy is `~/.claude/playbook`:
```sh
echo '{"tool_name":"Bash","tool_input":{"command":"git checkout -b x"}}' | python3 ~/Devl/Projects/claude-playbook/claude/hooks/guard.py
```
In a repo with a `Pattern:` line, `git checkout -b feat/9-x` (no role) should also print `"deny"`.

**Canary test** (once per session type, in a **new** session): ask it to run `echo <a command from your owner_only list>`, then `git checkout -b canary-test`, one at a time, and report each outcome without retrying.
- First refused (your `owner_only` message) → hook runs and found your config.
- Second shows an approval prompt → ask works. Click **Deny**.
- First just prints → the hook did not run, or it has no config. If the session said "No playbook config", fix the config step. Otherwise check the folder-trust prompt, `python3` on PATH, and that the session started after the files landed.

Passed on cloud and desktop.

## When Actions minutes run out

`scripts/copy-by-hand.sh` does the sync Action's job from your terminal. It takes the files from `.github/sync.yml` and the repos from your config. Needs SSH access and the `gh` CLI.

```sh
scripts/copy-by-hand.sh --list                         # show plan, change nothing
scripts/copy-by-hand.sh --dry-run --only .claude       # rehearse
scripts/copy-by-hand.sh --only .claude                 # one draft PR per repo
scripts/copy-by-hand.sh --only .claude your-org/app    # just these repos
```

- Always pass `--only`: without it the script also copies `two-reviews.yml`, and a required check that never runs blocks every merge.
- Don't run it twice while PRs are open: you get a duplicate PR. A same-day rerun adds the time to the branch name instead of failing.

## Not covered

- Per-repo write tokens (one writer per repo). Needs GitHub token setup, not files.
- Subagents on other models. Add a file in `claude/agents/` when you delegate to one.
