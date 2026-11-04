# Web app review, round 3 (b78ca4f outbox, 4a206ee attachments, 77135ca reminders/memories/search)

Reviewer: independent code + security review. Test suite: 422 passed. Repros:
`/tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/rev3/test_repro.py`
(run with `PYTHONPATH=tests .venv/bin/python -m pytest -q -s -o asyncio_mode=auto <file>`).

## Findings

### H1. 64 KB cap bypassed with a chunked body, including pre-auth on /api/login (reproduced)
`claudebot/web/__init__.py:88` raises `client_max_size` for the whole app from 64 KB to 11 MB, and
the replacement check at `:133` only looks at `Content-Length` (`request.content_length or 0`). A
request sent with `Transfer-Encoding: chunked` has no Content-Length, so it passes the check, and
`request.json()` then buffers up to 11 MB on every route.
- `/api/login` is open (no cookie or CSRF needed; a request with no Origin header passes `_same_origin`).
  Repro: a 5 MB body with Content-Length gets 413; the same body chunked is read and parsed (401).
  **30 parallel unauthenticated 10 MB chunked logins took process RSS from 197 MB to 854 MB.** The raw
  body stays cached on the request for the 0.3 s failure sleep, which makes it worse. On a small public
  host (WEB_PUBLIC_URL, e.g. a 256 MB Fly machine) anyone who can reach the URL can OOM-kill the whole
  bot, Telegram included. Before this commit aiohttp itself capped every body at 64 KB.
- Signed in, a 2 MB chunked `POST /api/memories` is accepted (200).
- The commit message ("everything else stays capped at 64 KB") and the test (`test_web.py`, the
  100 KB Content-Length case) don't hold for chunked bodies.

Fix: put `client_max_size` back to `MAX_BODY`. For `/api/chat`, read multipart with explicit limits
(see M1), which doesn't depend on `client_max_size` anyway. Alternatively, in `host_middleware`, refuse
a body with no Content-Length (411) outside `/api/chat`. Add a chunked-body test.

### M1. Multipart parts are read with no size limit (reproduced; needs a signed-in session)
`claudebot/web/api.py:188` (`part.text()`) and `:190` (`part.read()`) buffer the whole part before
any length check. aiohttp's `client_max_size` doesn't apply to `request.multipart()`. Repro with a spy
on `BodyPartReader.read`: a 40 MB file part is read in full (41,943,040 bytes) and only then refused
as "too big"; a 40 MB `text` part is read in full and then refused as "over 8,000 characters". Any
size works (GBs), and it all happens before the one-turn-per-session `chatting` check, so parallel
requests stack up. This needs the cookie and the CSRF token, so it's limited to the owner or a stolen
session, but it is still an unbounded allocation in the bot's process.

Fix: loop over `part.read_chunk()` with a running total and abort past `MAX_FILE_BYTES` (file) or
about `4 * MAX_CHAT_CHARS` bytes (text). Cap the total body and the number of parts (say 4), and
refuse unknown part names. Optionally take the busy slot before reading.

### M2. The outbox strip is re-rendered every 3 s: the body collapses and buttons shift under the finger
`claudebot/web/static/app.js:199` + `:303`: each poll calls `box.replaceChildren(...)` with brand-new
elements. (1) An opened `<details>` with the body closes, and its scroll position (`.body` max-height
220px) resets, every 3 s. The "full body is shown" guarantee for a **held** email (the one that needs
the owner's look before Send) is unusable for anything longer than a few lines. (2) Held emails are
listed above pending ones. If a held email arrives (from an unattended turn) while the owner is
reaching for **↩️ Undo** on a pending one, the strip shifts and the tap can land on the new email's
**✅ Send**, sending an email they never saw. That defeats the tap-to-approve protection. Found by
reading the code; the behaviour is deterministic.

Fix: diff by `id`: keep existing nodes, update only the countdown text, append or remove changed rows.
Keep held emails in a stable position (or put new rows at the end). Pause polling while a
`<details>` is open or the pointer is over the strip. Consider a 1 s "confirm" step (or disabling Send
for about 1 s after a row appears).

### L1. `/api/reminders` returns 500 for out-of-range dates (reproduced)
`api.py:291-297`: `"9999-12-31T23:59"` passes validation, and then `astimezone(timezone.utc)` in
`db.add_reminder` raises OverflowError, giving a 500. `"0001-01-01T00:00"` with a repeat is accepted
(stored as `-05:50:36` LMT) and fires within 5 s. Fix: require `now - 1 year < when < now + 10 years`
(or a year in 2000..2100), and catch OverflowError as a 400. The tool's `_schedule` has the same gap.

### L2. Search shows stale results from an out-of-order response
`app.js:531-541`: debounced, but responses aren't sequenced, so a slow response for "pa" can overwrite
the results for "passport". Fix: a request counter, or ignore a result whose query isn't the input's
current value.

### L3. An unsupported bot time zone breaks every page that shows dates
`fmtDate`/`fmtTime`/`botLocalInput` pass `timeZone: state.me.timezone`. A zone name the browser's ICU
doesn't know throws RangeError, so the Reminders, Bills, Activity and Settings pages fail to render.
Fix: check once at boot (`try { Intl.DateTimeFormat(undefined, {timeZone}) } catch { fallback }`).

### Info
- `_is_special_file` (`api.py:55-61`): a client file renamed `.txt` or saved as UTF-16 isn't caught.
  Telegram outside `/connect` doesn't catch these either, so the web is already stricter. The
  owner-chosen rename is acceptable; just noting it.
- Memory for a 10 MB upload is about 3-4x (bytearray, then a `bytes()` copy, then base64 for the
  inline fallback). Fine once M1 bounds it.
- A workbench (Office) file sent from the web shows in the history without the 📎 marker (the note is
  a text block, not a document block), which is cosmetic only.
- Outbox polling keeps running in background tabs (every 3 s). Consider `document.hidden`.

## What's correct
- Outbox: `approve` only moves `held -> pending` (a pending email can't skip its undo window, which
  returns 409); `undo` and `deliver` use atomic conditional UPDATEs, so web and Telegram taps can't
  double-send or resurrect an email. The web uses the same `Outbox` methods as `on_outbox_button`, and
  the Telegram card is edited on both cancel and send. The id the owner taps maps to immutable
  `email_json`, so nothing can be sent that isn't the listed email. to, cc, bcc and the full body
  (not the 3000-character Telegram preview) are returned and rendered with textContent. A polling
  timer can't leak across pages (`layout()` clears the single `state.timer`, and chatPage sets it
  synchronously after `layout`).
- Attachments: the same `to_block`/`store_raw`/`workbench_file_note` path as Telegram (Files API,
  `origin="owner"`, recorded for cleanup, magic-byte checks), the filename normalised to one line of 80
  characters and never used as a path, exports refused by name, and the `chatting` guard released in
  `finally`.
- Reminders: the same REPEAT_OPTIONS and the same past/repeat rule as `_schedule`; naive times read in
  the bot's zone, matching `botLocalInput`. `run_as_task` is forced to False, so the web can't create
  unattended agent tasks. The `owned` flag matches the server-side `_owned_reminder` refusal.
- Memories are trimmed to 500 characters with exact duplicates refused; search is a read-only
  substring match capped at 40 hits and 100 characters, with results rendered as text.

Score: 6/10
Verdict: not ready (H1 is a pre-auth memory DoS regression; fix H1, M1, M2 first)
