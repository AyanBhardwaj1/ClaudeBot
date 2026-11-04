# Desktop app (8ef16ca) and web fixes (4796686), review round 2

Repro scripts are in /tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/rev2/:
- `e2e.js` and `e2e2.js` run the real Electron app (xvfb, Playwright `_electron`) against a hostile "server" on
  localhost and record navigation events and `shell.openExternal` calls. Run: `xvfb-run -a node e2e.js`
- `test_rev2.py` holds the web repros. Run from the repo root:
  `PYTHONPATH=tests .venv/bin/python -m pytest -q -s -p no:cacheprovider -o asyncio_mode=auto <file>`

Test results: `desktop npm test` 6/6 passed. `tests/test_web.py` 20/20 passed.

No High or Medium findings. Nothing on the remote page reaches Node, IPC or the file system (reproduced below).

## Low

L1. The login failure list has no size limit, so a flood of junk logins costs more CPU the longer it runs. This is a
regression from the M1 fix. `claudebot/web/__init__.py:176`
`self._failures = [t for t in self._failures if now - t < 600] + [now]` now runs on every failure, and the list
keeps every failure from the last 10 minutes. Before the fix it stopped at 20. Each failed login copies the whole
list on the event loop, and that loop also runs Telegram polling.
- Reproduced: 2,000 junk POSTs leave 2,000 entries. With 300k entries (about 500 req/s for 10 minutes), each failed
  login blocks the loop for about 25 ms.
- Estimate: the load settles at about 87k entries, roughly 7 ms per request. Then about 150 req/s from a single
  client keeps the loop near 100% busy. A plain flood with no list would need about 2.5k req/s for the same effect.
- On Fly this endpoint is public, but it is still only a DoS.
- The 429 no longer slows anyone down. It only changes the status code.
- Fix: keep only a count, for example `collections.deque(maxlen=MAX_LOGIN_FAILURES + 1)`, or stop appending once
  the list is over the limit. An `await asyncio.sleep(0.5)` on failure would actually throttle.

L2. The L2 fix misses one case. `claudebot/web/__init__.py:51-55` (`check_public_url`), `:41-47` (`login_url`)
- `check_public_url` only looks at WEB_PUBLIC_URL. Set WEB_HOST=192.168.1.5 and leave WEB_PUBLIC_URL unset. The
  server then starts and sends /web links to `http://192.168.1.5:8765/login#t=...` (reproduced). That host is also
  allowed by `_host_ok`, because `web_host` is added to the allow-list. The token and the cookie cross the LAN in
  clear, which is exactly what L2 was meant to stop.
- `python -m claudebot web-login` prints such a link without running the check.
- Fix: in `check_public_url`, when there is no WEB_PUBLIC_URL, refuse a `web_host` that isn't loopback or a wildcard.
  Call the check from `web-login` too.

L3. When WEB_PUBLIC_URL is a loopback http address, direct access stops working. `__init__.py:150-151`
- Example: WEB_PUBLIC_URL=http://localhost:9000. The Docker host port differs from 8765, or a local proxy is in front.
- Then every localhost request must carry `Origin: http://localhost:9000`. A direct visit to http://localhost:8765
  gets 403 on login (reproduced).
- This fails safe and the setup is rare. Fix: compare `request.host` (which includes the port) with
  `public.netloc`, not just the hostname. Or skip the public branch when the public host is loopback.

L4. The desktop app opens other-origin navigations in the browser without any click. `desktop/src/main.js:56-60`
- A meta refresh or `location=` to another origin is blocked, and its URL is then passed to `shell.openExternal`
  automatically (reproduced: `http://127.0.0.1:47812/meta` and the target of a form POST were opened).
- A compromised or malicious server, or XSS in the web app, can therefore open any number of http(s) or mailto URLs
  in the default browser. The scheme allow-list keeps this to web links only.
- Fix: open externally only after a user gesture. Electron 44 passes `isUserInitiated`/`hasUserGesture` in the
  will-navigate details. Without a gesture, just block.

L5. The GitHub workflow pins actions by tag, not by SHA. `.github/workflows/desktop.yml:24,25,35`
- `actions/checkout@v4`, `setup-node@v4` and `upload-artifact@v4` are moving tags. The job builds installers that
  people will run, so pin full commit SHAs.
- Also add `persist-credentials: false` to checkout. As it is, `npm ci` install scripts run with the read-only
  `GITHUB_TOKEN` in `.git/config`.
- The good parts: `permissions: contents: read`, no secrets, no `pull_request_target`, `npm ci` from a lockfile.

## Info

- `grantFileProtocolExtraPrivileges` keeps its default (on). The built binary's fuse wire is `0:0 1:1 2:0 3:0 4:1
  5:1 6:0 7:1 8:1`. Setting it to `false` still lets `loadFile` load the setup page and narrows what file:// pages
  can do.
- "Forget this server" clears local storage but doesn't end the session on the server. The cookie is gone, but the
  server-side session stays valid for 30 days. Optionally POST /api/logout first.
- With `spellcheck: true` on Linux, Chromium downloads dictionaries from Google. This is privacy only, no risk.
- There is no auto-update. That is a sound choice for the attack surface, but Chromium fixes reach users only when
  they reinstall. Say so in desktop/README.
- If `agent.run` raises something other than the handled API errors, the SSE stream is cut off with no `done` event
  (reproduced: ClientPayloadError). The chat slot is still released by `finally`. This predates this commit.

## Verified fixes from round 1

- M1 fixed. The token is redeemed first, and after 30 junk tries a valid token still gets 200 (test + repro). See L1
  for the side effect.
- M2 fixed. Unknown Host gets 421 before routing, also for `/` and `/api/health` (repro: `evil`, `localhost.`,
  `127.0.0.1.nip.io` get 421; `localhost`, `LOCALHOST`, `127.0.0.1`, `[::1]` get 200). The 421 carries the security
  headers. The Origin check is built from the allowed host, not trusted from the request. The public host accepts only
  its exact https origin.
  Legitimate setups:
  - Docker on 127.0.0.1 (Host localhost or 127.0.0.1, any published port): OK.
  - Fly (Host `<app>.fly.dev`, public host from FLY_APP_NAME, Origin `https://<app>.fly.dev`): OK. fly.toml has no
    http checks that could hit 421.
  - A proxy that keeps Host plus WEB_PUBLIC_URL: OK.
  - A proxy that rewrites Host to localhost or 127.0.0.1 and has no WEB_PUBLIC_URL: OK for GET, 403 on POST (as
    before).
  - A proxy that rewrites to a container name (`claudebot:8765`): 421. Intended, but worth one line in the README.
  - IPv6 `[::1]`: OK, including the POST Origin check.
- L1 fixed. FLY_APP_NAME gives `https://<app>.fly.dev`, the placeholder is gone, and an explicit WEB_PUBLIC_URL wins.
- L2 partly fixed (see L2 above).
- L3 fixed. `on_response_prepare` adds the headers to the SSE stream, to 404 and 421, and to aiohttp's own 500
  (reproduced: the 500 has a CSP).
- L4 fixed. The key is the session's CSRF value, so there is one turn per sign-in (tabs share it).
  - A second POST gets 409.
  - A client that disconnects mid-turn keeps the slot until the turn finishes (reproduced: 409 after the disconnect,
    the slot is freed after, the turn ran once). aiohttp 3.12 does not cancel handlers on disconnect.
  - The keepalive loop can't leak. The task is always awaited to the end. `asyncio.wait` with a timeout doesn't
    cancel it. A failed write only stops writing.
- L6 fixed (brackets, and `::1` maps to localhost). L7 fixed (the `web-login` command exists and checks WEB_PORT=off).

## Desktop: what is correct (reproduced where marked)

- webPreferences: `contextIsolation`, `sandbox`, `nodeIntegration: false`, `webSecurity`. DevTools only when
  unpacked. No webviews (`will-attach-webview` is blocked for every webContents).
- Bridge: on the remote page `window.claudebot`, `require`, `process` and `electron` are all undefined (reproduced).
  The preload exposes `connect` only when `location.protocol === "file:"`. The IPC handler also checks
  `senderFrame.url` against the exact setup page URL. Subframes get no preload.
- Navigation (reproduced):
  - `location` to another origin: blocked, opened externally.
  - 302 to another origin: blocked by will-redirect, so the other server is never contacted.
  - 302 to the file:// setup page: Chromium refuses (ERR_UNSAFE_REDIRECT), and the app shows its own setup page with
    a fixed message.
  - `location` to the file:// setup page: refused.
  - iframe of file://: does not load.
  - Cross-origin iframe doing `top.location=`: blocked, and nothing opens.
  - `window.open` of file:, javascript:, the setup page or https: always returns null. Only https opens externally.
- Origins: comparison is exact on scheme, host and port, so an http downgrade or a different port counts as a
  different server.
  - `parseServerLink` rejects non-http(s) schemes, http to anything except localhost, 127.0.0.1 and [::1], and
    userinfo.
  - A tampered `config.json` goes through the same check, so file:, javascript: or LAN http are refused and the app
    shows setup.
  - The config is written 0600.
- Switching servers runs `clearStorageData()` before the new origin is set. That clears cookies, localStorage, the
  service worker and CacheStorage. API responses are `no-store`, so the HTTP cache holds no private data.
- Permissions:
  - Every request and every check is denied. Reproduced: geolocation, notifications, camera, microphone and
    clipboard-read all report `denied`.
  - There are no device-chooser handlers, so the default is cancel.
  - TLS errors use the default and are rejected.
- Setup page: CSP `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'`. There is no inline
  script, and the message is shown with `textContent` only.
- No deep-link protocol, no auto-updater, single-instance lock.
- Fuses: runAsNode off, NODE_OPTIONS off, `--inspect` off, cookie encryption on, ASAR integrity on, only-load-from-asar
  on. Checked in the built binary.

Score: 8.5/10
Verdict: ready. L1 (one line) and L2 (one check) are worth fixing next, but neither blocks.
