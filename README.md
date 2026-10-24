# Playbook

Rules and files that keep Claude sessions consistent across repos.

```
repo ──▶ one writer        PR ──▶ 2 reviews ──▶ writer merges
```

- [docs/overview.md](docs/overview.md): getting peers onto the rules, who owns what
- [docs/enforcement.md](docs/enforcement.md): what is enforced, by which gate, where it works, `CLAUDE_RELEASE_OWNER`
- [docs/how-it-works.md](docs/how-it-works.md): sync, review check, per-machine setup
- [docs/agent-console.md](docs/agent-console.md): the planned web app for assigning and watching agent work
- [rules/account-instructions.md](rules/account-instructions.md): the rules sessions follow (desktop imports it, cloud gets it pasted into account settings)
