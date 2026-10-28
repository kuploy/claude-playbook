# Solo + audit

Use: docs and low-risk chores.

## Roles
- writer: builds and merges.
- auditor: reads merged PRs afterwards. Any session that isn't the writer.

## Writers and branches
- Writers: 1.
- Open branches per writer: 1, named `feat/<role>/<n>-slug`, where `<role>` is the session's role name, such as `console-writer`.

## Reviews
- Reviews before merge: 0. The writer merges once its own checks pass.
- After merge: the auditor reviews at least 1 in 3 merged PRs, in the usual review format. A problem found goes into a new PR, not a revert, unless it breaks production.
- The guard doesn't apply patterns to merges. It refuses a merge with fewer than 2 approving reviews after the last push, from the `two-reviews` check or, when that check is missing, by counting them itself. So ask Ed to merge by hand. It asks Ed only when it can't read GitHub or tell which PR is merged.

## Reports to Ed
- The writer.

## Spawn cap and archiving
- Spawn cap: 0
- No spawning. Ed starts the auditor when he wants a sample.
