# Lead / writer

Use: a new repo or a new feature. The default when a repo's CLAUDE.md has no `Pattern:` line.

## Roles
- lead: cuts the work into issues, reviews, reports to Ed. Doesn't write code on the repo.
- writer: builds. One per repo.
- reviewer: the second review. Any session that isn't the writer.

## Writers and branches
- Writers: 1.
- Open branches per writer: 1, named `feat/writer/<n>-slug`.

## Reviews
- Reviews before merge: 2. One from the lead, one from the reviewer.

## Reports to Ed
- The lead.

## Spawn cap and archiving
- The lead keeps at most 3 live sessions it spawned. Children don't spawn.
- The lead archives each child when its task ends: PR merged or review posted.
