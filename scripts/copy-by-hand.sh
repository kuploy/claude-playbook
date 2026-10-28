#!/usr/bin/env bash
# Manual stand-in for the sync Action (use when Actions minutes run out).
# Reads file pairs from .github/sync.yml and repos from your playbook config (#44), opens one draft PR per repo.
# Needs: git with SSH access to the repos, python3, and the gh CLI (without gh it tells you which PRs to open by hand).
#
#   scripts/copy-by-hand.sh --list                         show what would be used, change nothing
#   scripts/copy-by-hand.sh --dry-run [options]            clone, copy, show the diff, push nothing
#   scripts/copy-by-hand.sh [options] [owner/repo ...]     do it
#
# Options:
#   --only <text>   only the file pairs whose line in sync.yml contains <text>
#                   e.g. --only pull_request_template
# With no owner/repo arguments it uses every repo in the config's "repos":
# $CLAUDE_PLAYBOOK_CONFIG, else ~/.claude/playbook-config.json.
set -uo pipefail

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; }

here=$(cd "$(dirname "$0")/.." && pwd)
cfg="$here/.github/sync.yml"
only=""; dry=0; list=0; repos=()
while [ $# -gt 0 ]; do
  case $1 in
    --only) only=${2:-}; shift 2 ;;
    --dry-run) dry=1; shift ;;
    --list) list=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1"; usage; exit 1 ;;
    *) repos+=("$1"); shift ;;
  esac
done

if [ ${#repos[@]} -eq 0 ]; then
  conf=${CLAUDE_PLAYBOOK_CONFIG:-$HOME/.claude/playbook-config.json}
  repos=($(python3 -c 'import json, sys; print("\n".join(json.load(open(sys.argv[1])).get("repos", [])))' "$conf" 2>/dev/null))
fi
pairs=$(awk '/^ *- source:/{s=$3} /^ *dest:/{print s" "$2}' "$cfg")
[ -n "$only" ] && pairs=$(echo "$pairs" | grep -F -- "$only")

if [ -z "$pairs" ] || [ ${#repos[@]} -eq 0 ]; then echo "nothing to do (no repos or no file pairs)"; exit 1; fi

echo "files:"; echo "$pairs" | sed 's/^/  /'
echo "repos:"; printf '  %s\n' "${repos[@]}"
[ $list -eq 1 ] && exit 0

git -C "$here" pull -q --ff-only 2>/dev/null || true   # use the latest playbook files

for r in "${repos[@]}"; do
  (
    d=$(mktemp -d) && git clone -q --depth 1 --no-single-branch "git@github.com:$r.git" "$d" && cd "$d" || { echo "$r: clone failed"; exit 1; }
    # same rule as the repos' CLAUDE.md: branch off dev when it exists, else the default branch
    base=$(git ls-remote --heads origin dev | grep -q 'refs/heads/dev' && echo dev || git rev-parse --abbrev-ref HEAD)
    branch="playbook/sync-$(date +%Y%m%d)"
    # a same-day rerun would collide with the first run's branch, so add the time
    if git ls-remote --heads origin "$branch" | grep -q .; then
      branch="playbook/sync-$(date +%Y%m%d-%H%M)"
      echo "$r: today's branch already exists, using $branch"
    fi
    git checkout -q "$base" && git checkout -q -b "$branch" || { echo "$r: branch failed"; exit 1; }
    echo "$pairs" | while read -r src dst; do mkdir -p "$(dirname "$dst")"; cp "$here/$src" "$dst"; done
    git add -A
    if git diff --cached --quiet; then echo "$r: already up to date"; exit 0; fi
    if [ $dry -eq 1 ]; then echo "$r: would open PR into $base:"; git diff --cached --stat; exit 0; fi
    git commit -qm "Sync files from claude-playbook" && git push -q -u origin "$branch" || { echo "$r: push failed"; exit 1; }
    body="Copied from kuploy/claude-playbook by scripts/copy-by-hand.sh:
$(echo "$pairs" | awk '{print "- " $2}')"
    gh pr create --draft --base "$base" --title "Sync files from claude-playbook" --body "$body" \
      || echo "$r: pushed $branch, open the PR by hand"
  )
done
