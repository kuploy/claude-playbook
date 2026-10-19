# Playbook

One home for the rules sessions follow. Repos copy from here; they don't restate.

| File | What |
|---|---|
| `templates/CLAUDE.base.md` | Block every repo's CLAUDE.md starts with. Repo-specific rules go below it. |
| `rules/collaboration.md` | Peers, reviews, messages, session hygiene. |
| `.github/pull_request_template.md` | Copy into each repo. |
| `claude/settings.json` | Merge into `~/.claude/settings.json` (or the repo's). |
| `claude/agents/chore.md` | Haiku subagent for mechanical work. Copy to `.claude/agents/`. |

Not built yet: the 2-reviewer status check, per-repo write tokens.
