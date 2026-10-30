#!/bin/sh
# Cloud environment setup script (#42). Paste this file's contents into the environment's settings,
# under Setup script, once. New sessions in that environment then run the playbook's hooks.
#
# Why: a repo's .claude/settings.json loads only when the session starts in that repo. A session
# with several repos starts in /home/user, and a session without a synced repo has no hooks at all.
# User settings (~/.claude/settings.json) load in every cloud session (tested 2026-10-28), so this
# clones the public playbook and points user settings at it. Each session start pulls the clone,
# so a hook change needs no re-paste. No clone: the hooks do nothing.
#
# Your own settings (#44) go between the CONFIG lines: the contents of config.json from your config repo.
# {} means none: no owner-only commands are blocked. After changing config.json, paste again, or set
# PLAYBOOK_CONFIG_TOKEN in the environment once and each session reads the latest itself (#53,
# docs/how-it-works.md, "When your settings change").
#
# It overwrites ~/.claude/settings.json; a fresh cloud container has none.
# Keep the matchers in step with claude/settings.json. Changing this file means pasting again.
set -u
PB="$HOME/.claude/playbook"
mkdir -p "$HOME/.claude"
[ -d "$PB/.git" ] || git clone -q --depth 1 https://github.com/kuploy/claude-playbook.git "$PB" \
  || echo "cloud-setup: playbook clone failed; sessions run without its hooks" >&2
cat > "$HOME/.claude/playbook-config.json" <<'CONFIG'
{}
CONFIG
cat > "$HOME/.claude/settings.json" <<EOF
{
  "autoCompactWindow": 250000,
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "git -C $PB pull -q --ff-only >/dev/null 2>&1; exit 0" }] },
      { "matcher": "startup|resume|compact",
        "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/notes.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; echo 'No playbook checks in this session: the playbook copy is missing.'; exit 0" }] }
    ],
    "PreToolUse": [
      { "matcher": "Bash|mcp__github__create_branch|mcp__github__merge_pull_request|mcp__github__create_pull_request|mcp__github__update_pull_request|mcp__github__add_issue_comment|mcp__github__pull_request_review_write",
        "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/guard.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] }
    ],
    "PostToolUse": [
      { "matcher": "Bash|mcp__github__create_pull_request",
        "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/guard.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] },
      { "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/signal.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] }
    ],
    "PermissionRequest": [
      { "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/signal.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] }
    ],
    "Notification": [
      { "matcher": "idle_prompt", "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/signal.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/signal.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/signal.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/plain.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\"; exit 0" }] },
      { "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/notes.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\" --stop; exit 0" }] }
    ],
    "PreCompact": [
      { "matcher": "auto|manual", "hooks": [{ "type": "command", "command": "F=\"$PB/claude/hooks/notes.py\"; [ -f \"\$F\" ] && exec python3 \"\$F\" --pre-compact; exit 0" }] }
    ]
  }
}
EOF
exit 0
