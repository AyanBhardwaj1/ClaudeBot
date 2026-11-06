# Web/desktop review, round 4 (7a1693a DM replies from the web, dd35ab7 desktop tray)

Repros: /tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/rev4/
(test_rev4_dms.py: 4 passing repro tests; tray_close.js: Electron under xvfb-run with Playwright). Full suite: 426 passed.

## Findings

### M1 (Medium, reproduced): every non-"sent" outcome reaches the owner as "Something went wrong (409)."
claudebot/web/api.py:507 returns `{"status", "message"}` with 409 and no `error` key. app.js:42 (`api()`) throws
`data.error || "Something went wrong (409)."`, so `act()` toasts that generic text, and dmsPage (app.js:556-558) is not refreshed.
Repro: `_send_as_owner` raises TimedOut after the text went out. The server returns 409
`{"status":"unknown","message":"⚠️ The connection dropped ... It may have gone out: check the chat before sending again."}`, and the
UI never shows it. "Telegram refused that (reason)" and "outside 24 hours, copy it yourself" are lost in the same way.
Fix: on the web, return the message as `error` for non-sent statuses, or have dmsPage read `status`/`message` itself. Show
the "unknown" warning so it stays on screen (not a 3.2 s toast) and reload the page after every outcome.

### M2 (Medium, reproduced): "one reply per message" holds only within each kind of reply. A typed reply and a quick reply can both go out.
The typed reply claims `dmweb_sent:` (api.py:521) and the quick reply claims `dmq_sent:` (business.py:487). Neither checks the other.
- After an "unknown" send, record_sent is not called, so the chat still shows as waiting with live quick buttons. A web or Telegram ⚡ then
  sends a second message from the owner's account (repro: delivered == ['Yes 10 min', 'On it 👍']). Combined with M1, the owner sees only
  "Something went wrong", so they are likely to click again.
- Two tabs (or web plus Telegram ⚡) running at once: a typed reply and a quick reply to the same message both send (repro: 200/200, two
  deliveries). A Telegram AI draft (`dmsend:`) also has no claim or freshness check (pre-existing).
Each send is still an explicit owner click on exact text, so this is not an unauthorised send. It does break the stated invariant and
leaves a real double-send after "unknown". Fix: use one per-message claim (`dm_sent:{chat}:{msg}`) shared by the typed web reply, the
web quick reply and the Telegram quick reply, and record an "unknown" marker so every path refuses until the owner confirms.

### M3 (Medium, reproduced on Linux): hide-to-tray happens even when no tray is visible, so the app keeps running invisibly
desktop/src/main.js:33-38, 87-92. On Linux, `new Tray()` does not throw when there is no tray host (GNOME without the AppIndicator
extension, xvfb). The try/catch fallback ("no tray: closing quits as before") therefore never runs. Repro (tray_close.js): close the
only window; the main process stays alive with one hidden window. The app then holds the signed-in session and the global shortcut with
no visible UI. The only ways back are a relaunch or Ctrl+Shift+Space; Quit is reachable only through them. SIGTERM still quits, so
logout is fine. Fix: hide-to-tray on win32 only, or make it an opt-in setting on Linux.

### L1 (Low): the global shortcut and the tray's "Chat"/"Today"/"Week" always reload the page
main.js:27: `show(view)` calls `loadURL` even when the window already shows that view. Pressing Ctrl/Cmd+Shift+Space while typing in
chat throws away the draft and drops any reply that is still streaming. Fix: skip `showApp` when `getURL()` already equals the target,
or only bring the window forward.

### L2 (Low, pre-existing, now easy to fix): on macOS, menu items crash once the window is closed
main.js:124, 138-140: after `closed`, `win` is null, so Reload and View → Chat/Today/Week call `win.loadURL` / `win.webContents` on null
(a main-process exception dialog). Before this commit they hit a destroyed window and failed the same way. Fix: route them through `show(view)`.

### L3 (Low, unverified, Windows): a prevented `close` can hold up OS shutdown or logoff
Fix (defensive): `win.on("query-session-end"/"session-end", () => { quitting = true; })`.

### Nits
- api.py:518: `message_id: true` is accepted as 1 (Python `True == 1`). This is harmless because only the owner can send it. Require `type(...) is int`.
- api.py:512: `[:4000]` silently truncates instead of refusing. It cannot happen from the UI (maxlength 4000), but refusing is safer for "exact text".
- A web quick-reply conflict says "waiting on a retry above", which is Telegram wording.

## Correct
- Only the owner can send. All three POSTs go through the auth middleware (session cookie, CSRF header, Origin/Host). Nothing reaches
  deliver_dm except an owner click or tap, and no LLM tool calls deliver_dm, claim_quick_reply or _send_as_owner.
- Recipient: the chat id comes from the URL, `_waiting_chat` must match it, and `message_id` must equal that chat's last incoming id.
  The reply goes to `chat.chat_id`. A stale screen gets 409.
- Double click on the same kind of reply: the claim is checked and set with no await in between, so the second click gets 409.
- Claim handling: freed on pending/expired (status set to cancelled/expired, so no stale retry card can resend). Kept on sent and on
  unknown. Kept on an unexpected exception (status stays "sending"), which fails safe.
- Telegram behaviour after the refactor matches the previous version: same messages, retry markup only for pending, none for expired
  or unknown. Negative quick-reply indexes are now refused (they used to wrap around). The notice is now recorded even if editing the
  message fails.
- Untrusted text: names and messages are put on the page through text nodes or setAttribute (placeholder, aria-label). Toasts are textContent.
- Desktop: `show(view)` only uses hard-coded views on the validated origin. will-navigate, will-redirect, setWindowOpenHandler, the
  permission handler and the IPC sender check are unchanged and run for every new window. `closed` nulls `win` and show() recreates it, so
  no destroyed window is reused and only one window exists. Quit from the menu or tray sets `quitting`. The shortcut is unregistered in will-quit.

Score: 7/10
Verdict: not ready (fix M1 and M2: the owner must see "it may have gone out", and a second message must not go out after it; M3 before shipping Linux builds)
