#!/usr/bin/env python3
"""console-post.sh cases from PR #87, kept so the next change to it starts from here (#88).

    python3 -I tests/test_console_post.py [path/to/console-post.sh]

Exits 0 when every case lands where it should, 1 otherwise. No request leaves this machine: the
script posts to an http.server listener this file starts on a free loopback port, and every other
host a case names is refused before curl runs. One qualifier, because the first draft of this
sentence promised more than it delivers (console-reviewer on #89): while scoring a *broken* head,
`userinfo-elsewhere` does reach curl, which resolves `exfil.invalid` and fails with `curl: (6)`.
A DNS query goes out. Nothing follows it -- `.invalid` never resolves, by RFC 2606 -- and no
bearer is ever sent to it, but a machine that logs DNS will see the name.

To score any head, the way #87's reviews were argued:

    python3 -I tests/test_console_post.py --rev b67f0d8

It reads that revision's script with `git show` into a temp file and deletes it after.

Why these cases exist: the host check was rewritten twice inside #87 and was wrong both times.
The first version let CONSOLE_URL name any host. The second read only the tail after the last
colon, so `http://127.0.0.1:1@localhost:<port>` passed -- curl reads `127.0.0.1:1` as a user and
password and requests the host after the `@`, which posted the bearer to a host the reviewer
chose (console-reviewer, comment 6529138633). Both holes were found by hand, by a harness written
for one review and thrown away. These are those harnesses.

Three things every case asserts, not just the exit code:

  * a refused case reaches no listener at all -- an exit code of 2 after the request went out
    would be the same bug wearing a better error message;
  * the secret appears in nothing the script writes, on either stream;
  * every request that did go out went to 127.0.0.1 or localhost, with the bearer and the body
    intact.

The secret cases are about curl's config parser, which is what `--config -` buys and costs: it
keeps the Authorization header out of `ps`, and inside a quoted value it still reads backslashes
and quotes, and treats a newline as the start of a second config line -- including `url = `. So
the script checks the secret's alphabet before sending, and `secret-newline-url` is the case that
says why. If the console ever rotates to `openssl rand -base64`, that alphabet grows and these
three cases change deliberately rather than get deleted.
"""
import http.server, json, os, re, shutil, subprocess, sys, tempfile, threading

USAGE = "usage: python3 -I tests/test_console_post.py [path/to/console-post.sh | --rev <sha>]"
SCRIPT = os.path.join("scripts", "console-post.sh")
REV = None
if len(sys.argv) > 1 and sys.argv[1] == "--rev":
    if len(sys.argv) < 3:
        raise SystemExit(USAGE)
    REV = sys.argv[2]
elif len(sys.argv) > 1:
    SCRIPT = sys.argv[1]

SENTINEL = "sentinel-secret-do-not-print"
CONSOLE = "https://claude-agent-console.vercel.app"
seen = []
status = [200]


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        seen.append({"path": self.path, "host": self.headers.get("host"),
                     "auth": self.headers.get("authorization"),
                     "ctype": self.headers.get("content-type"),
                     "body": self.rfile.read(n).decode()})
        self.send_response(status[0])
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


BODY = {"sessions": [{"id": "session_01"}]}


def shells():
    """sh is whatever /bin/sh is here; dash is where the POSIX-only reading bites."""
    return [s for s in ("sh", "dash") if shutil.which(s)]


def run(path, shell, args, secret=SENTINEL, url=None):
    env = dict(os.environ)
    env.pop("INGEST_SECRET", None)
    env.pop("CONSOLE_URL", None)
    if secret is not None:
        env["INGEST_SECRET"] = secret
    if url is not None:
        env["CONSOLE_URL"] = url
    p = subprocess.run([shell, path] + args, capture_output=True, text=True, env=env)
    return p.returncode, (p.stdout + p.stderr)


def cases(base, good, bad):
    """(id, want_exit, args, kwargs). want_exit 0 means the listener must see the request."""
    return [
        # --- the happy path, and the only two hosts a harness may point it at ---
        ("ok-sessions",        0, ["sessions", good], {"url": base}),
        ("ok-trailing-slash",  0, ["sessions", good], {"url": base + "/"}),
        ("ok-localhost",       0, ["sessions", good], {"url": base.replace("127.0.0.1", "localhost")}),
        # No case runs with CONSOLE_URL unset: the default is the real console, the script would
        # accept it, and curl would post this sentinel to production. That one branch is read, not run.

        # --- the path is one segment, because the allow rule ends in :* ---
        ("path-slash",         2, ["api/ingest/sessions", good], {"url": base}),
        ("path-dotdot",        2, ["../../x", good], {"url": base}),
        ("path-full-url",      2, ["http://evil.test/x", good], {"url": base}),
        ("path-upper",         2, ["Sessions", good], {"url": base}),
        ("path-empty",         2, ["", good], {"url": base}),
        ("path-leading-dash",  2, ["-X", good], {"url": base}),
        ("arg-count",          2, ["sessions"], {"url": base}),

        # --- the body ---
        ("file-missing",       2, ["sessions", "/no/such/file.json"], {"url": base}),
        ("file-not-json",      2, ["sessions", bad], {"url": base}),

        # --- the secret: absent, empty, or a shape curl's config parser would mis-read ---
        ("secret-absent",      3, ["sessions", good], {"url": base, "secret": None}),
        ("secret-empty",       3, ["sessions", good], {"url": base, "secret": ""}),
        ("secret-backslash",   3, ["sessions", good], {"url": base, "secret": 'ab\\cd"ef'}),
        ("secret-quote",       3, ["sessions", good], {"url": base, "secret": 'abc"def'}),
        ("secret-space",       3, ["sessions", good], {"url": base, "secret": "abc def"}),
        ("secret-newline-url", 3, ["sessions", good],
         {"url": base, "secret": "abc\nurl = %s/api/ingest/INJECTED" % base}),

        # --- the host. CONSOLE_URL may name the console or a loopback port, nothing else ---
        ("host-elsewhere",     2, ["sessions", good], {"url": "https://evil.example.test"}),
        ("host-console-suffix", 2, ["sessions", good], {"url": CONSOLE + ".evil.test"}),
        ("host-http-other",    2, ["sessions", good], {"url": "http://evil.example.test:80"}),
        ("host-with-path",     2, ["sessions", good], {"url": base + "/api/ingest"}),
        ("host-query",         2, ["sessions", good], {"url": base + "?x=1"}),
        ("host-fragment",      2, ["sessions", good], {"url": base + "#@evil.test"}),
        ("host-dotted-suffix", 2, ["sessions", good], {"url": "http://127.0.0.1.evil.test:80"}),
        ("host-no-port",       2, ["sessions", good], {"url": "http://127.0.0.1:"}),
        ("host-hex-port",      2, ["sessions", good], {"url": "http://127.0.0.1:0x50"}),
        ("host-port-suffix",   2, ["sessions", good], {"url": "http://127.0.0.1:80x"}),
        ("host-https-local",   2, ["sessions", good], {"url": base.replace("http://", "https://")}),
        ("host-file-scheme",   2, ["sessions", good], {"url": "file:///etc/passwd"}),
        ("host-ipv6-local",    2, ["sessions", good], {"url": base.replace("127.0.0.1", "[::1]")}),

        # --- curl's userinfo parsing: the hole comment 6529138633 posted the bearer through.
        # Each of these ends in digits after the last colon, which is what the second version of
        # the check read. curl requests the host after the @.
        ("userinfo-localhost",  2, ["sessions", good],
         {"url": "http://127.0.0.1:1@" + base.split("//")[1].replace("127.0.0.1", "localhost")}),
        ("userinfo-elsewhere",  2, ["sessions", good], {"url": "http://127.0.0.1:1@exfil.invalid:80"}),
        ("userinfo-from-local", 2, ["sessions", good], {"url": "http://localhost:1@exfil.invalid:80"}),
        ("userinfo-self",       2, ["sessions", good],
         {"url": "http://127.0.0.1:%s@%s" % (base.rsplit(":", 1)[1], base.split("//")[1])}),
    ]


def main():
    path = SCRIPT
    if REV:
        text = subprocess.run(["git", "show", "%s:scripts/console-post.sh" % REV],
                              capture_output=True, text=True)
        if text.returncode != 0:
            print("cannot read scripts/console-post.sh at %s:\n%s" % (REV, text.stderr.strip()))
            return 2
        # Written here rather than through a shell redirect: the guard suite lost its bytes that
        # way and scored every head 0 (tests/test_guard.py).
        fd, path = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as f:
            f.write(text.stdout)
    try:
        return run_all(path)
    finally:
        if REV:
            os.unlink(path)


def run_all(path):
    if not os.path.exists(path):
        print("no script at %s -- pass its path as the first argument" % path)
        return 2
    found = shells()
    if not found:
        print("no sh on PATH")
        return 2

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]

    good = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(BODY, good)
    good.close()
    bad = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    bad.write("{nope")
    bad.close()

    rows, failing = [], 0
    try:
        for shell in found:
            for cid, want, args, kw in cases(base, good.name, bad.name):
                before = len(seen)
                code, out = run(path, shell, args, **kw)
                hits = seen[before:]
                leaked = SENTINEL in out
                # A refused case must not have reached the listener, and an accepted one must have.
                wrong_hits = (want == 0 and not hits) or (want != 0 and bool(hits))
                ok = code == want and not leaked and not wrong_hits
                failing += 0 if ok else 1
                rows.append((shell, cid, want, code, len(hits), leaked, ok,
                             out.strip().replace("\n", " / ")[:70]))

            # The console's own answer, which only the exit code can tell you about.
            status[0] = 500
            code, out = run(path, shell, ["sessions", good.name], url=base)
            ok = code == 4 and SENTINEL not in out
            failing += 0 if ok else 1
            rows.append((shell, "console-500", 4, code, 1, SENTINEL in out, ok, ""))
            status[0] = 200
            code, out = run(path, shell, ["sessions", good.name], url="http://127.0.0.1:1")
            ok = code == 4 and SENTINEL not in out
            failing += 0 if ok else 1
            rows.append((shell, "console-unreachable", 4, code, 0, SENTINEL in out, ok, ""))
    finally:
        srv.shutdown()
        os.unlink(good.name)
        os.unlink(bad.name)

    # The production arm is read and not run, so no case above would notice CONSOLE= being edited
    # to another host -- the one exfiltration path these cases leave open (console-reviewer on #89).
    # This is the cheap close: the literal has to be in the script, spelled exactly.
    # Presence is not enough, and the first draft of this check only asked for presence: a second
    # CONSOLE= line after it left the suite green while `origin` resolved to the attacker's host,
    # because the last assignment is the one the shell uses (console-writer on #89). So: exactly
    # one assignment, and it is this line. Quoting counts -- re-quoting the same URL fails this
    # case with no change in behaviour, which is the price of reading source text instead of
    # running it, and the message below says so rather than leaving someone hunting.
    pinned = 'CONSOLE="https://claude-agent-console.vercel.app"'
    assign = re.compile(r"^\s*(?:export\s+|readonly\s+)?CONSOLE=")
    with open(path) as f:
        lines = [l.rstrip("\n") for l in f]
    # Not `found`: that name holds the shells, and shadowing it here printed the CONSOLE= line
    # where the summary says which shells ran.
    assigns = [l for l in lines if not l.lstrip().startswith("#") and assign.match(l)]
    has_pin = len(assigns) == 1 and assigns[0].strip() == pinned
    why = ""
    if len(assigns) != 1:
        why = "expected exactly one CONSOLE= assignment, found %d: %s" % (
            len(assigns), " | ".join(l.strip() for l in assigns) or "none")
    elif not has_pin:
        why = "the one CONSOLE= assignment must read exactly %s (quoting included, so re-quoting " \
              "the same URL fails here with no change in behaviour)" % pinned
    failing += 0 if has_pin else 1
    rows.append(("-", "console-pinned", "1 line", "yes" if has_pin else "no", 0, False, has_pin, why))

    print("%-5s %-20s %-5s %-4s %-5s %-6s %s" % ("sh", "case", "want", "got", "hits", "leak", "output"))
    for shell, cid, want, code, hits, leaked, ok, out in rows:
        print("%-5s %-20s %-5s %-4s %-5s %-6s %s%s"
              % (shell, cid, want, code, hits, leaked, out, "" if ok else "   <-- FAIL"))

    wanted_auth = "Bearer " + SENTINEL
    local = [r for r in seen if (r["host"] or "").split(":")[0] in ("127.0.0.1", "localhost")]
    right = [r for r in seen if r["path"] == "/api/ingest/sessions" and r["auth"] == wanted_auth
             and r["ctype"] == "application/json" and json.loads(r["body"]) == BODY]
    print("\n%d request(s) went out; all to a loopback host: %s; all correct: %s"
          % (len(seen), len(local) == len(seen), len(right) == len(seen)))
    if len(local) != len(seen):
        for r in seen:
            print("  REACHED %s path=%s bearer=%s" % (r["host"], r["path"], r["auth"] == wanted_auth))
    print("%d case(s) over %s, %d failing" % (len(rows), "+".join(found), failing))
    off = len(seen) - len(local) + len(seen) - len(right)
    return 1 if failing or off else 0


if __name__ == "__main__":
    sys.exit(main())
