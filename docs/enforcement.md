# What is enforced

**Enforced** = the system refuses or asks. **Convention** = a template makes the right thing easy. **Willpower** = only the prompt says so.

## Rules and their gate
| Rule | Level | Gate | Status |
|---|---|---|---|
| No new branch without asking | Enforced (asks you) | Guard hook `.claude/hooks/guard.py` | Tested on cloud and desktop |
| Only the release owner releases | Enforced (denies) | Guard hook + `CLAUDE_RELEASE_OWNER=1` | Tested on cloud and desktop |
| 2 reviews before merge | Enforced once live | `two-reviews` status check + guard hook on merge | **Not live**: Actions quota. Merge rule only tested with a fake `gh`. |
| A review has the 4-line block | Enforced once live | Same `two-reviews` check | Not live |
| One writer per repo | Willpower | None. Needs per-repo tokens. | Not built |
| Context size | Enforced on desktop only | `autoCompactWindow` in `~/.claude/settings.json` | Cloud has no such file: it uses the default (about 784k tokens) |
| Cheapest model that fits | Convention | `chore` agent, model set in settings | Desktop only |
| Never hold a finished review, one-line messages, thread owner reports, archive done sessions | Willpower | Account prompt | See below |
| Sync PRs need one hash check, not two reviews | Convention | Documented exception | Recorded in [how-it-works.md](how-it-works.md) |

The guard hook is installed in all 13 repos on their working branch. kuploy-cloud has it on `dev`, not yet on `main`.

## What a session reads (tested 2026-10-23/24)
| | Cloud | Desktop |
|---|---|---|
| Account prompt, new session | **Yes** | **No.** Use the `~/.claude/CLAUDE.md` import. |
| `~/.claude/CLAUDE.md` is loaded | n/a | Yes (a session quoted it) |
| Account prompt through that import | n/a | To verify in a new session |
| Account prompt, session already running | Untested | Untested |
| Hook files appear in a running session | **Load live** | **Load live** |
| A new session sees the repo's `.claude/` files | Yes | Yes, after `git pull` |

`/hooks` works only in a terminal session, not in the desktop app.

## `CLAUDE_RELEASE_OWNER=1`
The guard denies `docker/release.sh`, `docker/build.sh` and `release.sh` in kuploy-cloud, `docker build/push ... kuploy-cloud`, and `kubectl` write commands. A session with `CLAUDE_RELEASE_OWNER=1` in its environment is exempt.

| | |
|---|---|
| Where it is set | `.claude/settings.local.json` in the release checkout, `~/Devl/Projects/Kuploy/kuploy-cloud`. Git-ignored. Content: `{"env":{"CLAUDE_RELEASE_OWNER":"1"}}`. |
| Who it exempts | **Every** session opened in that folder. Use the folder for the release session only. |
| When it takes effect | At session start. Start a **new** session after editing. |
| Terminal alternative | `CLAUDE_RELEASE_OWNER=1 claude` exempts one process. |
| Proof | Non-owner cloud session on kuploy-cloud: **refused**. New desktop session in the release folder: **printed**. A same-folder control run was not done. |

## Gaps
- `two-reviews` is written but not live, because of the Actions quota.
- One writer per repo has no gate.
- Sessions already running when the rules change: account-prompt behaviour is untested. Start a new session.
- The hook matches command text. An unusual command gets past it.
