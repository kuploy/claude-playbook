# What is enforced

**Enforced** = the system refuses or asks. **Best effort** = catches the usual cases, can be sidestepped. **Convention** = a template makes the right thing easy. **Willpower** = only the prompt says so.

## Guard hook (`.claude/hooks/guard.py`, in all 13 repos on their working branch)
| What | Level | Status |
|---|---|---|
| New branch: **asks you** on `git checkout -b`, `switch -c`, `branch <name>`, `worktree add -b`, `push -u`, GitHub create-branch | Best effort (matches command text) | Tested cloud and desktop, Manual mode. Bypass and Auto modes untested. |
| Release, build, cluster writes: **denies** `docker/release.sh`, `build.sh`/`release.sh` in kuploy-cloud, `docker build/push ... kuploy-cloud`, `kubectl` write verbs, unless `CLAUDE_RELEASE_OWNER=1` | Enforced for those commands. An unusual command gets past. | Tested cloud and desktop |
| Merge (`gh pr merge`, GitHub merge tool): allows if `two-reviews` is green, **denies** if it exists and isn't, **asks** if missing or unchecked | Enforced once the check is live | Only tested with a fake `gh`. Today it always asks. |
| PR body over 15 lines (GitHub tools and `gh pr create/edit`): **denies** | Enforced for those tools. Footer lines not counted | In all 14 repos. Refused in a live cloud session, 2026-10-25 |
| Review comment (`Reviewer:`) missing a line or over 5 lines after the block: **denies** | Enforced for those tools | In all 14 repos. Refused in a live cloud session, 2026-10-25 |
| After opening a PR: **reminds** to subscribe and schedule a check-in | Reminder, not a block | Self-tested. That Claude shows the reminder is untested |
| Bad input, a crash or a wrong script path | **Fails open**: no guard, no error | Known gap. Run the self-test after setup. |
| Repos without the `.claude/` files | No guard | All 13 repos have them on their working branch. Also on `main`: kuploy, kuploy-hub, growthops, epay-gateway, kuploy-cloud. Other `main` branches: not checked. |

## Checks, GitHub, tooling
| What | Level | Status |
|---|---|---|
| `two-reviews` check: two different `Reviewer:` blocks after the last push, from people with write access | Enforced once live | **Not live**: Actions billing limit (seen blocking jest on epay-gateway). Not marked required in any ruleset. Trusts the `Reviewer:` name, not the `Ran:` text. |
| Rulesets, CODEOWNERS, required reviews | None | Not set up |
| One writer per repo | Willpower | Needs per-repo tokens. Not built. |
| PR template with the 4-line review block (13 repos) | Convention | Merged. Applies from each repo's default branch. |
| Sync-only PRs need one hash check, not two reviews | Convention | Recorded in [how-it-works.md](how-it-works.md) |
| Sync Action (copies files to repos) | Tooling | **Disabled**: quota. Use `scripts/copy-by-hand.sh`. |
| Release gate in kuploy-cloud (`dev` = `main`, core checked by hand) | Willpower, partly `release.sh` | In its CLAUDE.md. `release.sh` ref-locks cloud and only prints core's sha. |

## Prompt, settings, habits
| What | Level | Status |
|---|---|---|
| Account prompt: new cloud session | Willpower (it is text) | Loads. Tested. |
| Account prompt: new desktop session | Willpower | **Does not load.** Fix done: `~/.claude/CLAUDE.md` imports the playbook file. Probe: 3 of 3 yes (2026-10-24). |
| Account prompt: session already running | Willpower | Untested. Start a new session. |
| Per-repo CLAUDE.md (read code first, no new branch, git workflow) | Willpower | Loads in sessions started in that repo |
| Desktop rules stay current: a `SessionStart` hook pulls the playbook | Enforced on your laptop once added | Untested. The pull may land after the rules load, so a change shows one session later |
| Cloud session messaging a desktop peer | Allowed for the playbook session only (Ed approved on a trusted device, 2026-10-25). Other cloud sessions still can't | Tested: delivered |
| Reviewer discovery bullet (`Review requested from:`, `list_sessions`) | Willpower | In the rules file and pasted into account settings (2026-10-24). PR template line not added. |
| `autoCompactWindow` 250000 on **desktop** | Enforced | From `~/.claude/settings.json` |
| `autoCompactWindow` on **cloud** | Enforced when read | Cloud has no user settings, so it used the default (about 784k). **A repo `.claude/settings.json` works** (tested: threshold 184k, source "settings"). Merged in all 13 repos; not re-tested on one of them. |
| Default model and effort | Convention | Desktop only. Cloud sessions are set when started. |
| `chore` Haiku agent | Convention | Main session decides to delegate. Untested. |
| Spawn cap (3 live per spawner), spawner archives on task end, push before leaving, one-line messages, thread owner reports, restart peers after a rule change | Willpower | About ten old idle sessions exist |

## What a session reads (tested 2026-10-23/24)
| | Cloud | Desktop |
|---|---|---|
| Account prompt, new session | **Yes** | **No** |
| `~/.claude/CLAUDE.md` loaded | n/a | Yes (a session quoted it) |
| Repo `.claude/settings.json` (hooks, `autoCompactWindow`) | Yes | Yes |
| Hook files added to a running session | **Load live** | **Load live** |

`/hooks` works only in a terminal session.

## `CLAUDE_RELEASE_OWNER=1`
The guard denies release commands for every session except one with this in its environment.

| | |
|---|---|
| Where it is set | `.claude/settings.local.json` in the release checkout, `~/Devl/Projects/Kuploy/kuploy-cloud`. Git-ignored. Content: `{"env":{"CLAUDE_RELEASE_OWNER":"1"}}`. |
| Who it exempts | **Every** session opened in that folder. Use the folder for the release session only. |
| When it takes effect | At session start. Start a **new** session after editing. |
| Terminal alternative | `CLAUDE_RELEASE_OWNER=1 claude` exempts one process. |
| Proof | Non-owner cloud session on kuploy-cloud: **refused**. New desktop session in the release folder: **printed**. A same-folder control run was not done. |
