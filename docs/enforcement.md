# What is enforced

**Enforced** = the system refuses or asks. **Best effort** = catches the usual cases, can be sidestepped. **Convention** = a template makes the right thing easy. **Willpower** = only the prompt says so.

## Guard hook (`claude/hooks/guard.py`, run from the playbook clone in every repo, #42)
| What | Level | Status |
|---|---|---|
| New branch, scope gate (#13): **denies** no issue number or another open PR in the repo, **allows** a sub-issue of an open `scope:frozen` epic, else **asks** | Best effort (matches command text) | Each row self-tested with real and fake `gh`, 2026-10-25. Bypass and Auto modes untested. |
| Pattern branches (#29), only with a `Pattern:` line: **denies** a branch without `feat/<role>/`, a lead that doesn't write, a second branch per role, more roles than the pattern's writers | Best effort: the role is what the branch says | Tested with a fake `gh` (21 cases), 2026-10-27. Canary not run |
| Owner-only commands (#44): **denies** each command in your config's `owner_only`, unless the session has its `allow_env` variable set to `1` | Enforced for those commands. An unusual command gets past. No config: none | Built-in version tested cloud and desktop. Config version: canary after setup |
| Config missing, unreadable, or with no owner-only commands | Owner-only commands not blocked. **Each new session is told** | Self-tested |
| Merge (`gh pr merge`, GitHub merge tool): allows if `two-reviews` is green, **denies** if it exists and isn't. Missing (#30): counts the reviews itself like `local` below, **denies** under two. **Asks** only if GitHub can't be read | Enforced on machines with the hook. Trusts the typed `Reviewer:` name; a merge from the web UI gets past | Tested with a fake `gh` (10 cases), 2026-10-27. |
| Merge with `CLAUDE_REVIEW_GATE=local` (#34): counts approving `Reviewer:` blocks after the push, **denies** under two, **asks** only if GitHub can't be reached or replies with something unreadable | Enforced on machines with the hook. A merge from the web UI or a phone gets past | Tested with a fake `gh` (14 cases), 2026-10-26. Not switched on anywhere. |
| PR body over 15 lines (GitHub tools and `gh pr create/edit`): **denies** | Enforced for those tools. Footer lines not counted | In all 14 repos. Refused in a live cloud session, 2026-10-25 |
| Review comment (`Reviewer:`) missing a line or over 5 lines after the block: **denies** | Enforced for those tools | In all 14 repos. Refused in a live cloud session, 2026-10-25 |
| After opening a PR: **reminds** to subscribe and schedule a check-in | Reminder, not a block | Self-tested. That Claude shows the reminder is untested |
| Bad input, a crash or a wrong script path | **Fails open**: no guard, no error | Known gap. Run the self-test after setup. |
| A computer or cloud environment not set up | No guard | Set up once each: [how-it-works.md](how-it-works.md#setting-up). A session that starts without the playbook copy is told so. |
| A session edits or deletes its own playbook copy or config | Guard changed or gone | Known gap. The next pull doesn't undo a local edit. |

## Checks, GitHub, tooling
| What | Level | Status |
|---|---|---|
| `two-reviews` check: two different `Reviewer:` blocks after the last push, from people with write access | Enforced once live | **Not live**: Actions billing limit (seen blocking a test job). Not marked required in any ruleset. Trusts the `Reviewer:` name, not the `Ran:` text. |
| Rulesets, CODEOWNERS, required reviews | None | Not set up |
| One writer per repo | Willpower | Needs per-repo tokens. Not built. |
| PR template with the 4-line review block (13 repos) | Convention | Merged. Applies from each repo's default branch. |
| Sync-only PRs need one hash check, not two reviews | Convention | Recorded in [how-it-works.md](how-it-works.md) |
| Sync Action (copies files to repos) | Tooling | **Disabled**: quota. Use `scripts/copy-by-hand.sh`. |

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
| `autoCompactWindow` on **cloud** | Enforced when read | From `~/.claude/settings.json`, written by the Setup script (#42). Without it, the default (about 784k). |
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

## `CLAUDE_REVIEW_GATE`
Which evidence the guard wants before a merge (#34).

| | |
|---|---|
| `status` (default) | The `two-reviews` commit status. Missing: counts the reviews as `local` does (#30), since Actions may not run. |
| `local` | The guard counts the reviews itself, the way `sync/two-reviews.yml` does: the latest block per `Reviewer:` name, from someone with write access, posted after GitHub received the head (earliest check suite, else the committer date), verdict starting `approve`, `Ran:` and `Would catch:` filled. Under two: **deny**. With no check suites readable it counts from the commit date and says so. It **ignores** the `two-reviews` status, even a red one: use `both` for that. Needs neither Actions nor the console. |
| `both` | Both of the above. A missing status is a **deny**, not an ask. |
| Any other value | **Ask**. Case and spaces are ignored, so ` Local ` is `local`; a typo like `locl` does not silently mean `status`. |
| Where to set it | Cloud: the environment's variables (untested). Desktop: `"env": {"CLAUDE_REVIEW_GATE": "local"}` in `.claude/settings.local.json` (that checkout only). Not in a repo's `.claude/settings.json`: that file is shared through git. Takes effect at session start. |
| Limit | It only guards sessions that run the hook. The status, when something posts it and a ruleset requires it, binds everyone. |

## The owner-only switch
The guard denies your config's `owner_only` commands for every session except one with its `allow_env` variable set to `1` (below, `CLAUDE_RELEASE_OWNER`).

| | |
|---|---|
| Where it is set | `.claude/settings.local.json` in the owner's checkout. Git-ignored. Content: `{"env":{"CLAUDE_RELEASE_OWNER":"1"}}`. |
| Who it exempts | **Every** session opened in that folder. Use the folder for the owner session only. |
| When it takes effect | At session start. Start a **new** session after editing. |
| Terminal alternative | `CLAUDE_RELEASE_OWNER=1 claude` exempts one process. |
| Proof (built-in version, before #44) | Non-owner cloud session: **refused**. New desktop session in the owner folder: **printed**. A same-folder control run was not done. |
