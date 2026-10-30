#!/bin/sh
# POSTs a JSON file to one of the agent console's ingest routes (#86).
#
#   scripts/console-post.sh <path> <json-file>
#   scripts/console-post.sh sessions /tmp/snapshot.json
#
# Why this exists rather than a curl command: the auto-mode check blocks a session's own
# POST to the console as data exfiltration. A fixed script can be allowed by name
# (scripts/cloud-setup.sh adds it to permissions.allow), and a curl pattern cannot be,
# because the pattern would allow any URL and any body.
#
# The allow rule ends in :*, so any argument reaches this script. That is why <path> is
# one plain segment and nothing else: no scheme, no host, no "..", no slash. Otherwise the
# rule would hand out a general-purpose POST tool.
#
# Needs CONSOLE_URL (default below, as claude/hooks/signal.py uses) and INGEST_SECRET in the
# environment. The secret is passed to curl on stdin, never in an argument, so it stays out
# of `ps` and out of anything this script prints.
#
# Exit: 0 when the console answers 2xx, 2 on a usage or input error, 3 with no secret,
# 4 when the request fails or the console answers anything else.
set -u

die() { echo "console-post: $1" >&2; exit "$2"; }

[ $# -eq 2 ] || die "usage: console-post.sh <path> <json-file>" 2

path=$1
file=$2

# One segment of a known shape. Anything else is a bug or an attempt to post elsewhere.
case $path in
  *[!a-z0-9-]* | "" | -* | *-) die "path must be one lower-case segment, e.g. sessions (got: $path)" 2 ;;
esac

[ -f "$file" ] || die "no such file: $file" 2
python3 -m json.tool "$file" >/dev/null 2>&1 || die "not valid JSON: $file" 2

[ -n "${INGEST_SECRET:-}" ] || die "INGEST_SECRET is not set in this environment" 3

url="${CONSOLE_URL:-https://claude-agent-console.vercel.app}"
url="${url%/}/api/ingest/$path"

body=$(mktemp) || die "cannot write a temp file" 4
trap 'rm -f "$body"' EXIT INT TERM

# --config - keeps the Authorization header off the command line.
code=$(printf 'header = "Authorization: Bearer %s"\n' "$INGEST_SECRET" \
  | curl -sS --config - --max-time 20 \
      -X POST "$url" \
      -H 'Content-Type: application/json' \
      --data-binary "@$file" \
      -o "$body" -w '%{http_code}') || die "the request to $url failed" 4

case $code in
  2??) echo "console-post: $path $code"; sed -n '1,20p' "$body"; exit 0 ;;
  *)   echo "console-post: $path $code" >&2; sed -n '1,20p' "$body" >&2; exit 4 ;;
esac
