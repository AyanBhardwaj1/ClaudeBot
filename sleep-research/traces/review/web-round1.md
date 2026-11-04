# Web app review, round 1 (039d464: "feat: web app, served by the bot itself")

Repro scripts: /tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/webrev/test_repro.py
(run: `PYTHONPATH=tests .venv/bin/python -m pytest -q -s -p no:cacheprovider -o asyncio_mode=auto <that file>`)
Suite: tests/test_web.py 12 passed.

No High findings. No XSS, CSRF, path-traversal or auth-bypass found.

## Medium

M1. Anyone can lock the owner out of signing in, from anywhere. claudebot/web/__init__.py:33,142-153
`_failures` is one global list. `login()` checks it *before* it looks at the token. 20 bad POSTs in 10 minutes
(no Origin header, so `_same_origin` passes, as with curl) return 429 to everyone, including the owner's fresh,
valid link. Reproduced in test_global_login_lockout: 20 junk tries, then a valid token gets 429.
- On Fly the port is on the internet. Two requests a minute keep sign-in off for good.
- On localhost, any web page the owner visits can do the same through DNS rebinding (see M2).
- Sessions that are already open keep working, and the token is not used up.
Fix: redeem the token first. A 256-bit token can't be brute-forced, so a valid token should always get in. Throttle
only the failure path (sleep, or a per-client limit). Never return 429 to a request that holds a valid token.

M2. The Host header is never checked, and the Origin check trusts whatever host the request names.
claudebot/web/__init__.py:115-127
`allowed = {http://{request.host}, https://{request.host}}`. Under DNS rebinding the attacker's page is
`http://rebind.evil:8765`, and its requests carry `Host: rebind.evil:8765` and the same Origin, so the check passes.
Reproduced: a POST to /api/login with that Host and Origin gets 401 (token wrong), not 403.
What the attacker gets today:
- No cookie. The session cookie is host-only on `localhost` (from `login_url`), so every session endpoint returns 401
  (reproduced). The cookie, the CSRF token and the SameSite=Strict flag still protect the data.
- The open paths: /api/health (shows ClaudeBot is running), the static shell, and /api/login. Through M1 that is
  enough to lock out sign-in.
- One mistake away from more: if a later endpoint is open, or reads `request.host` (for example to build a link),
  rebinding reaches it.
Fix: allow only known Hosts: `localhost`, `127.0.0.1` and `[::1]` with WEB_PORT, plus the host of WEB_PUBLIC_URL.
Answer anything else with 421 before routing. Build the allowed Origins from that list, not from `request.host`. When
WEB_PUBLIC_URL is https, accept only that https origin. The http and https pair is not needed, because the browser's
Origin is the public https URL, not what the proxy forwards.

## Low

- L1 fly.toml:5-10. `WEB_PUBLIC_URL = "https://claudebot-change-me.fly.dev"` matches the placeholder app name. Fly app
  names are global, so someone else already owns or can claim that name. An owner who renames `app` (Fly makes them)
  but forgets this line gets /web links that send their token (in the fragment, which JavaScript can read) to a
  stranger's site. That site is also added to the allowed Origins. The stranger would still need the owner's real
  host to use the token, so the risk is low, but the fix is trivial: default to `https://$FLY_APP_NAME.fly.dev`
  (Fly sets FLY_APP_NAME), and drop the hardcoded URL.
- L2 config.py:107-109 / web_commands.py. Nothing stops a plain-http deployment that other machines can reach. Example:
  WEB_HOST=0.0.0.0 with WEB_PUBLIC_URL=http://192.168.1.5:8765. Login tokens and the session cookie then cross the LAN
  in clear, and the cookie has no Secure flag. Fix: when WEB_PUBLIC_URL is http:// on a host that isn't loopback,
  refuse to start, or have /web refuse to send a link. Mention the risk in the log.
- L3 __init__.py:78-94 and api.py:139-141. The security headers are set *after* the handler has run.
  - SSE: `/api/chat` has already called `prepare()`, so its headers are on the wire. The CSP, nosniff,
    Referrer-Policy and frame headers never reach it (reproduced: the SSE response has none of them).
  - Errors: an unhandled exception (a 500) skips the header code entirely (reproduced: the 500 has no CSP). The 500
    body is aiohttp's generic text and has no traceback, even with loop debug on.

  Fix: set the headers in an `app.on_response_prepare` signal.
- L4 api.py:131-168. Chat turns have no per-session limit and no keepalive.
  - Each tab can queue any number of turns behind `_message_order`, and `shield` runs every one of them, even after
    the client goes away (reproduced: 5 posted, 3 clients cancelled, all 5 ran and were billed). Only a signed-in
    session can do this, so it is a cost and reliability issue, not an exposure.
  - No bytes are sent while waiting for the lock or during long tool calls. Proxies with an idle timeout (Fly,
    Caddy) can cut the stream, and the owner sees "connection dropped".

  Fix: one turn in flight per session (409 otherwise), and a `: ping` comment every 15s.
- L5 app.js:60-73. If the redemption fails for a reason other than a bad token (429 from M1, the server restarting,
  network trouble), the token stays valid for 10 minutes. It stays in the browser's global history entry for
  `/login#t=...`, because `replaceState` rewrites the session-history entry but not the browser's visited-URL record.
  Low: it is single use and expires soon. Fix: none needed beyond M1. Optionally use a short code to exchange instead.
- L6 web/__init__.py:38. With `WEB_HOST=::1` the link is `http://::1:8765/login` (reproduced), which is invalid.
  IPv6 literals need brackets. Functional only.
- L7 auth.py:2. The docstring documents `python -m claudebot web-login`, which doesn't exist (`__main__.py` has no
  such command).

## Info

- From the web, an email sent with the owner present gets its Undo button only in Telegram. This matches Telegram:
  owner-present turns send without a tap there too. The chat footnote ("Anything that needs a tap to confirm ... shows
  up in Telegram") is accurate for held emails and guests. No web API skips a confirmation that Telegram requires.
  Bill, birthday and memory deletes, Paid, and the quiet, alert-mode and urgent-wakes settings are all one tap in
  Telegram too. The web adds a `confirm()` for bill removal and sign-out-all.
- The session cookie is shared by every port on `localhost`. Pages on other localhost ports are same-site, so the
  Strict cookie goes with their requests. They still can't read responses (no CORS) or send the CSRF header (needs a
  preflight). Harmless. With HTTPS, a `__Host-` cookie prefix would add cookie-tossing protection.
- Sessions last 30 days with no idle timeout and no list of active sessions. Fine for a single owner. "Sign out
  everywhere" exists in both the web app and Telegram.

## What is correct

- Login token: 256 bits, in the fragment (not sent to the server, a log or a Referer), only its hash is stored,
  single use, 10 minutes, at most 5 pending. get+delete runs with no await in between, so it is atomic. The token is
  removed from the address bar before the POST. Telegram link previews are off globally. `/web` is private chat only
  (not groups, forwards, edits or business messages).
- Sessions: the server makes the id, so there is no fixation. Only its hash is stored, so a copy of the database
  can't sign in. The cookie is HttpOnly, SameSite=Strict, and Secure when WEB_PUBLIC_URL is https (correct behind
  Fly's TLS). Logout and logout-all need CSRF and Origin. Login CSRF is moot: an attacker can't get a token.
- CSRF: every non-GET request needs the per-session token in a custom header. Nothing sends CORS headers, so
  cross-origin pages can't send it. The no-Origin case only allows `Sec-Fetch-Site` missing or `same-origin`, which
  is sound because the CSRF token is the real gate. `Origin: null` is rejected.
- XSS: app.js builds everything with `createElement` and `textContent`. Attribute names are constants, `href` is
  internal only, and there is no innerHTML or eval anywhere. Untrusted fields (event titles, DM names and messages,
  memories, model replies, the User-Agent in the action log) are all rendered as text.
- CSP: `script-src 'self'` and `style-src 'self'` with no unsafe-inline or unsafe-eval, plus frame-ancestors 'none',
  base-uri 'none', form-action 'none' and object-src 'none'. The only inline styling is via the CSSOM (`el.style`),
  which CSP allows. Also sent: X-Frame-Options DENY, no-referrer, nosniff, COOP, and HSTS over HTTPS.
- Static handler: an exact-path dict. Traversal and encoding variants all return 404 (`//api/me`, `/%61pi/me` (401 via
  the same auth path), `/static/%2e%2e/...`, `/x/../api/me`). The auth middleware and the router see the same decoded
  path, so no bypass was found.
- Errors: there is no access log, the 500 body is generic, and API errors are short fixed strings. Request size is
  capped at 64 KB and chat at 8,000 characters.
- The service worker caches only the five shell files, network-first, and never /api or /login.
- Lifecycle: the server starts in `_post_init` (a port conflict is logged, and the bot runs on) and stops in
  `_post_shutdown`, so the port is freed for in-process restarts. Web turns take `_message_order`, run with
  owner_present=True (correct, since the owner typed them), and skip the Telegram preview and typing indicator.
- Docker publishes only to 127.0.0.1. Fly has force_https.

Score: 7/10
Verdict: not ready. Fix M1 and M2 first (both are small: redeem before throttling, and a Host allowlist). L1 and L3
are quick follow-ups.
