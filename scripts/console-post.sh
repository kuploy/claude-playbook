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
# The host is pinned here, not taken from the environment: an allowed script that posts
# wherever CONSOLE_URL says is an exfiltration tool with a nicer name. CONSOLE_URL may only
# name the console below, or a 127.0.0.1 or localhost port, which is how a harness points it at a local
# listener. The whole string after that prefix must be the port: a tail-of-the-string check accepts
# http://127.0.0.1:1@evil.test:80, where curl reads 127.0.0.1:1 as user:password and requests evil.test.
#
# Needs INGEST_SECRET in the environment. It goes to curl on stdin, never in an argument, so it
# stays out of `ps` and out of anything this script prints. Its characters are checked first:
# curl's config parser reads backslashes and quotes inside a quoted value, and a newline in the
# value adds a second config line, which POSTs the secret to whatever url that line names.
#
# Cloud only: scripts/cloud-setup.sh adds the allow rule, and claude/settings.json (the desktop
# template) has no permissions key, so a desktop session is asked as usual.
#
# Exit: 0 when the console answers 2xx, 2 on a usage or input error, 3 on a missing or
# unusable secret, 4 when the request fails or the console answers anything else.
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
# A bearer token is this alphabet, which covers the hex the console documents (openssl rand -hex 32,
# claude-agent-console/docs/setup.md:18). Anything else is either not the secret or an attempt to add a
# second line to curl's config, so refuse it rather than sending a mangled header. A rotation to
# rand -base64 would need "+", "/" and "=" added here, and each of those is safe in a quoted value.
case ${INGEST_SECRET} in
  *[!A-Za-z0-9_-]*) die "INGEST_SECRET holds characters a bearer token cannot: refusing to send it" 3 ;;
esac

CONSOLE="https://claude-agent-console.vercel.app"
origin="${CONSOLE_URL:-$CONSOLE}"
origin="${origin%/}"
case $origin in
  "$CONSOLE") ;;
  *)
    # The whole string after the prefix must be the port. Don't read the tail after the last colon:
    # http://127.0.0.1:1@evil.test:80 ends in digits, and curl reads 127.0.0.1:1 as user:password and
    # requests evil.test (console-reviewer, comment 6529138633).
    rest=
    case $origin in
      http://127.0.0.1:*) rest="${origin#http://127.0.0.1:}" ;;
      http://localhost:*) rest="${origin#http://localhost:}" ;;
    esac
    case $rest in
      "" | *[!0-9]*) die "CONSOLE_URL may name $CONSOLE or a 127.0.0.1 port, not $origin" 2 ;;
    esac ;;
esac
url="$origin/api/ingest/$path"

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
