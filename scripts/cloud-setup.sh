#!/bin/sh
# Cloud environment setup script (#42). Paste this file's contents into the environment's settings,
# under Setup script. New sessions in that environment then load the playbook's hooks.
#
# Why: a cloud session with several repos starts in /home/user, so no repo's .claude/settings.json
# loads and neither the guard nor the notes hook runs. This writes /home/user/.claude/settings.json
# and a launcher. The launcher finds the playbook clone under /home/user when a hook runs (it may
# not be cloned yet when this script runs) and does nothing when there is none.
#
# Keep in step with sync/claude-settings.json: same window, same matchers.
set -eu
mkdir -p /home/user/.claude/hooks
cat > /home/user/.claude/hooks/run.sh <<'EOF'
#!/bin/sh
# Runs the playbook's hook named in $1 from the clone under /home/user. No clone: no opinion.
for f in /home/user/*/claude/hooks/"$1"; do
  [ -f "$f" ] && exec python3 "$f"
done
exit 0
EOF
cat > /home/user/.claude/settings.json <<'EOF'
{
  "autoCompactWindow": 250000,
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|resume|compact",
        "hooks": [{ "type": "command", "command": "sh /home/user/.claude/hooks/run.sh notes.py" }] }
    ],
    "PreToolUse": [
      { "matcher": "Bash|mcp__github__create_branch|mcp__github__merge_pull_request|mcp__github__create_pull_request|mcp__github__update_pull_request|mcp__github__add_issue_comment|mcp__github__pull_request_review_write",
        "hooks": [{ "type": "command", "command": "sh /home/user/.claude/hooks/run.sh guard.py" }] }
    ],
    "PostToolUse": [
      { "matcher": "Bash|mcp__github__create_pull_request",
        "hooks": [{ "type": "command", "command": "sh /home/user/.claude/hooks/run.sh guard.py" }] }
    ]
  }
}
EOF
