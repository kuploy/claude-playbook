# Release train

Use: repos that ship a release.

## Roles
- writer: builds. Up to 2, each with its own role name.
- reviewer: reviews PRs. Any session that isn't the PR's writer.
- release owner: reviews every PR, promotes `dev` to `main` and runs the release, both only when Ed asks. The guard blocks release, build and cluster commands for everyone else; promotion is held by this rule, not by the guard.

## Writers and branches
- Writers: up to 2.
- Open branches per writer: 1, named `feat/<role>/<n>-slug`, where `<role>` is the session's role name.
- The guard holds this (#29): one open branch per role, at most 2 roles, none for the release owner.

## Reviews
- Reviews before merge: 2. One of them from the release owner.

## Reports to Ed
- The release owner.

## Spawn cap and archiving
- Spawn cap: 3 (the release owner; other roles 0)
- The release owner keeps at most 3 live sessions it spawned. Others don't spawn.
- The release owner archives each child when its task ends: PR merged or review posted.
