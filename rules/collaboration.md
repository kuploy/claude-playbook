# Collaboration rules

**Reference copy only.** The source of truth is the "Working with other sessions" and "Sessions and quota" sections of the Claude account settings. Sessions read those, not this file. Change the account settings first, then update this copy. If they disagree, the account settings win.

Enforced = the system refuses. Convention = a template makes it the easy path. Willpower = only the rule.

## Peers and repos

- A repo has **one writer** (one peer). Everyone may read every repo. *(Not enforced yet: needs per-repo tokens.)*
- Every piece of work needs **2 reviewers** before it merges. *(Enforced by the `two-reviews` check, once required in the ruleset. See `docs/how-it-works.md`.)*
- **Never hold a finished review.** Post it and reply to the peer with the result. *(Willpower.)*
- A review says **what was run and what it would have caught**. "Looks good" doesn't count. *(Enforced: the check needs `Ran:` and `Would catch:`.)*

## Messages (quota)

1. Reviews live on the PR, not in session messages. A message is one line plus a link.
2. Only the peer who owns a thread reports to the user. Not every reviewer, every round.
3. Don't re-verify a peer's claim unless it is load-bearing and cheap.
4. Batch messages to: done, blocked, or wrong. Not one per commit.
5. State what work is prioritised over everything else.

Keep: mutation testing, running a proposal before recommending it, checking premises at source. That is the cheap part of the bill.

## Sessions

A session's age is its cost. Context is re-billed every turn.

- Finish or archive. An idle session still wakes on PR events and pays full price to do nothing.
- Cap context once, in settings (`autoCompactWindow`). Don't rely on remembering.
- Right-size the model: Haiku for renames and chores, Sonnet by default, Opus only for design and review.
- Push the branch before walking away. Work in one place only is lost work.

## Talking to the user

Simple words. Terse. Answer first ("Short answers:"), then focused breakdowns. Decisions go in a table: what's wrong | why it matters | what to do | whose call.
