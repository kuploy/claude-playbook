# Release train

Use: repos that ship a release, such as kuploy-cloud and core.

## Roles
- writer: builds. Up to 2, named `writer-1` and `writer-2`.
- reviewer: reviews PRs. Any session that isn't the PR's writer.
- release owner: reviews every PR, promotes `dev` to `main` and runs the release, both only when Ed asks. The only role that touches the release.

## Writers and branches
- Writers: up to 2.
- Open branches per writer: 1, named `feat/writer-1/<n>-slug` or `feat/writer-2/<n>-slug`.

## Reviews
- Reviews before merge: 2. One of them from the release owner.

## Reports to Ed
- The release owner.

## Spawn cap and archiving
- The release owner keeps at most 3 live sessions it spawned. Others don't spawn.
- The release owner archives each child when its task ends: PR merged or review posted.
