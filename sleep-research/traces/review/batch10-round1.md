# Batch 10 review, round 1

Scope: 9657f38 (fixes for the batch 8 quick-reply findings) and 5a434fe (the ⏰ 3h button in /dms). Both live in
claudebot/business.py, with the callback pattern in claudebot/bot.py:381.

Repros: `/tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/b10/test_b10_repro.py`
(run from the repo with `PYTHONPATH=tests .venv/bin/python -m pytest -o asyncio_mode=auto -s <file>`). All 5 pass,
which means each behaviour below reproduces. Suite at HEAD: 384 passed.

## Findings

| ID | Sev | Where | Finding |
|----|-----|-------|---------|
| L-1 | Low | business.py:48 (`quick_replies`) | A quick reply saved under the old 100-char cap gets cut at 60 mid-word, with no notice (R1) |
| L-2 | Low | business.py:367, :482, :494 | The batch 8 L-3 fix is partial: the Sent, Cancelled and connection-dropped edits still show the raw name (R4) |
| L-3 | Low | business.py:392 | The contact's name in the reminder text keeps phone numbers and /commands tappable when the reminder fires (R2) |
| I-1 | Info | business.py:384-396 | The reminder still fires after you have replied (R3), and it can land in quiet hours |
| I-2 | Info | business.py:392, tools.py:772-783 | The untrusted name reaches the model unfenced through `list_reminders` |
| I-3 | Info | business.py:271 | The check-in signal still uses the raw `c.name` (it existed before this batch) |

No High or Medium findings.

### L-1: legacy quick replies are cut, not dropped
`quick_replies()` returns `t[:MAX_QUICK_LEN]` for saved entries. A reply saved under the old cap, like "Yes I'll be
there at 6, see you soon but NOT if it rains, then cancel everything ok", becomes "...but NOT if it rains, th". The
card body, the button, the CRC tag and the text sent all agree, so the security property holds: you only send what
you saw. But the cut changes the meaning, and neither the card nor `/quickreplies` says anything was cut. R1 shows
the cut text going out after one tap.
Acceptable as is? It is safe, but rough to use. Fix: drop over-long saved entries, falling back to the defaults if
none are left, or keep them and add "(cut to 60 characters: set them again with /quickreplies)" to the card and to
`/quickreplies`. A one-off migration that rewrites the setting would also work.

### L-2: names still raw in three reply-card edits
The commit says names are "defanged in /dms and reply cards". The first card is defanged, but these edits are not:
`✖️ Cancelled reply to {reply['name']}` (:367), `The connection dropped while sending to {reply['name']}` (:482) and
`✅ Sent to {reply['name']}` (:494). R4: with the name "Support https://evil.example/login", the Sent edit shows a
live link. Previews are off, but Telegram still makes the link clickable.
Fix: `defang_urls(reply['name'])` in all three.

### L-3: the reminder text can pose as something else
The reminder is `💬 Reply to {defang_urls(clip(chat.name, 40))} on Telegram (/dms)`. Its URLs are defanged, and
`clip` collapses whitespace, so a name can't add new lines. But the name is still free text. R2: with the name
"Bank: card frozen call 18005551234 /new", the reminder fires 3 hours later in the bot's own voice as
`⏰ 💬 Reply to Bank: card frozen call 18005551234 /new on Telegram (/dms)`. Telegram makes the number tappable, and
`/new` too: one tap sends /new and wipes your conversation thread. It is bounded: the reminder only exists because
you tapped ⏰ next to that same name in /dms, the name is capped at 40 characters, and the same name already shows
in /dms. Still, the reminder fires out of context, which is the case tools.py:766 warns about.
Fix: quote the name and neutralise commands, for example `“{name}”` with `/` replaced by `∕` (or a zero-width
joiner after it). Better still, show "Reply to your Telegram chat (/dms)" and keep the name out of the bot's voice.

### I-1: the reminder doesn't know you replied
R3: you tap ⏰, then answer from your phone. The chat leaves /dms, but the reminder still fires. When the
reminder fires, check `_waiting_chat(chat_id)` and skip it if nobody is waiting. That needs the reminder to carry
the chat id, or a small separate job. A reminder set at 23:00 also pings at 02:00. The tap answer shows the time,
so you know, but deferring to the end of quiet hours would be kinder.

### I-2: the untrusted name reaches the model through list_reminders
`list_reminders` returns the raw reminder text in a tool result, so 40 characters of the contact's name reach the
model without a fence. Tools that send are owner-gated, and 40 characters leave little room for an attack, so this
stays Info. It is one more path for untrusted text into the model, though, which the dm:draft prompt deliberately
avoids.

## Verified correct
- **M-1:** `MAX_QUICK_LEN` is 60. The card body lists every reply in full, numbered, and each button reads
  `N. <text>`. Even when a phone client shortens a label, the body shows exactly what each number sends, and `set_quick_replies`
  enforces the cap at write time.
- **L-1 (batch 8):** the callback is `dmq:<chat>:<msg_id>:<i>:<tag>`. `_quick_send` refuses when
  `chat.last_message_id != msg_id`, and the claim is keyed on that id. The card shows what is being answered,
  defanged and clipped. The test covers the "they wrote again" case.
- **L-2 (batch 8):** an existing claim now gives "already went (or is waiting on a retry above)". That is accurate
  for a refused send (the row is `pending`, the retry card is there) and for a timeout.
- **L-3 (batch 8):** names are defanged in the /dms lines, the proposal card and the quick card. Button labels
  aren't clickable, so `c.name[:24]` there is fine. For the remaining edits, see L-2 above.
- **L-5 (batch 8):** ⚡ Quick shows only when `c.can_reply`. `_waiting_chat` uses `unanswered(limit=None)`, and /dms
  and the check-ins still use the default cap of 8.
- **Pattern:** anchored, with `\d+` for the message id. The worst case is 42 bytes for `dmq:` and 25 for
  `dm:later:` (R5), both within 64.
- **⏰ 3h:** `_from_owner` runs before the `later:` branch (strangers get a silent answer, and a test covers it).
  The chat must currently be waiting. One reminder per `chat:last_message_id`, claimed before any await, so a
  double tap sets one. A new message allows a new reminder, which matches "one per incoming message". Nothing goes
  to the contact: there's no `_send_as_owner` or `propose` on this path, and the test asserts `delivered == []`.
  It is a plain reminder (`run_as_task=False`), so the name is never run as a task prompt. When it fires,
  bot.py:912 defangs it again and gives it Snooze/Done. The notice is fenced and defanged in `_background_block`.
  The ActionLog keeps the raw name, but /log defangs it on display.

Score: 8/10
Verdict: ready (L-1 to L-3 are small follow-ups; none blocks shipping)
