# Agent console

A web app (planned, epic #7) to give agents work, watch their progress, check reviews, and see what rules are enforced and what sessions cost. App code and its own plumbing docs will live in the app's repo.

## The design rule

Sessions read files and GitHub. They cannot read the app. So anything an agent must obey or act on stays where agents already look.

| What | Source of truth | The app |
|---|---|---|
| Rules, synced settings, guard hook | this repo | shows them, edits them by opening a PR here |
| Work for agents | GitHub issues: `agent:<role>`, `priority:p0`–`p3`, one Project for status | assigns, reorders, shows progress |
| Reviews | PR comments (the 4-line block) | reads, times, checks `Ran:` |
| Review times, tokens, session snapshots | the app's database | owns them |

The database never holds a rule or a task. If the app is down, agents keep working.

## Roles, not session names

Session names change on every restart. Work goes to a **role** (`docs`, `review`, …). The app tracks which session holds each role now.

## Agents pull their work

At start and after each task, a session reads its role's open issues, highest priority first. The app cannot push into a session. A scheduled Claude task can wake cloud sessions; desktop sessions need the trusted-device approval first.

## Data in

- **GitHub:** a GitHub App sends webhooks (issues, PRs, comments). No Actions minutes.
- **Sessions:** an hourly Haiku task sends session snapshots. No public API for Claude sessions was found.
- **Repair:** a daily Vercel cron re-reads GitHub to catch missed webhooks.
