# Batch 8 review, round 1

Scope: 4e81409 (one-tap quick replies), 09116b0 (birthdays in /today, the brief, `list_birthdays`; tests/helpers
`quiet_hours=None`), 5168118 (triage requeue / snooze cap first; Resume clears focus). Not covered here:
4b6ac72, 7004aee, 9a277cc (another reviewer has them), and bc831a0 (export/restore, landed while I worked).

Repros: `/tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/b8/test_b8_repro.py`
(run from the repo with `PYTHONPATH=tests .venv/bin/python -m pytest -o asyncio_mode=auto -s <file>`; all 5 pass,
which means all 5 behaviours reproduce) and `.../b8/mut_quiet.py` (a pytest plugin, `MUT=<module>`, that turns one
module's `in_quiet_hours` off). Suite at HEAD: 376 passed.

## Findings

| ID | Sev | Where | Finding |
|----|-----|-------|---------|
| M-1 | Medium | claudebot/business.py:370 (MAX_QUICK_LEN at :43) | A tap can send text the button didn't show (reproduced, R1) |
| L-1 | Low | business.py:375-390 | A stale card sends against a newer message it never showed (reproduced, R3) |
| L-2 | Low | business.py:383-386 | After a refused send, the claim blocks the other replies with a false "Nobody is waiting there now." (reproduced, R2) |
| L-3 | Low | business.py:372 (also :313, :262, :449) | The other person's display name is shown without defanging (reproduced, R4) |
| L-4 | Low | tests/helpers.py:33; review.py:50,61; meeting_prep.py:58; heartbeat.py:151 | No test covers these quiet-hours checks (mutation-tested) |
| L-5 | Low/Info | business.py:314, :362 | ⚡ Quick shows for chats it can't send to, and chat 9+ gets a misleading answer (reproduced, R5) |
| I-1 | Info | triage.py:96-103 | An ambiguous Gmail failure on snooze drops the hold |
| I-2 | Info | triage.py:63-65 | Requeue can race a fresh /triage |

### M-1: the button label is cut at 60 characters, the send isn't
`InlineKeyboardButton(text[:60], ...)`, but `set_quick_replies` allows up to 100 characters (`MAX_QUICK_LEN`), and the
card body doesn't list the replies. Repro R1: with the reply "Yes I'll be there at 6, see you soon but NOT if it
rains, then cancel everything ok", the button reads "...but NOT if it rains, th" and the tap sends the whole
sentence from the owner's account. Telegram phone clients also shorten long button labels with an ellipsis well
before 60 characters, so even a reply of 60 characters or fewer can be partly hidden. The CRC tag protects against the list changing, but
not against the label differing from the payload.
Fix: put the full replies in the card body, numbered ("1. ...", "2. ...", with the buttons labelled "1 · On it 👍"),
and/or cap `MAX_QUICK_LEN` at the label length. Add a test that every label is exactly the text that gets sent, or
that the card body contains each full reply.

### L-1: stale cards aren't tied to the message they answer
The callback is `dmq:<chat>:<i>:<tag>`, and the claim is keyed on the chat's *current* `last_message_id`. A ⚡ Quick
card left untapped (or a second card for the same chat) works forever. Repro R3: a card opened for "running late?",
then the owner answers from the phone, then Alex writes "did you crash my car??". Tapping the morning card sends
"On it 👍". The card shows only the name, not what is being answered. Both are owner taps, so this is Low, but it is
exactly the "stale card" case.
Fix: put the message id in the data, `dmq:<chat>:<msg_id>:<i>:<tag>` (40 bytes or less), and refuse with "They wrote
again; tap ⚡ Quick again" when `chat.last_message_id != msg_id`. Key the claim on that id. Show their last message
(defanged, clipped) in the card.

### L-2: a failed send leaves the claim set, and the answer then misleads
Retry still works: `_deliver_dm` rewrites the card into the `dmsend:<id>` Send/Cancel retry (the row is `pending`),
and the TimedOut/"unknown" branch correctly offers no retry. But the `dmq_sent:` claim stays set. Repro R2: after
a BadRequest, the owner opens a new ⚡ Quick card (offered, because /dms still lists the chat) and taps "Thanks!".
The answer is "Nobody is waiting there now.", which is false.
Fix: when the claim exists, answer "A reply to this message is already in progress or failed: use the Send button
on that card." Optionally, clear the claim when `_deliver_dm` puts the row back to `pending` after a definite refusal.

### L-3: undefanged names in the quick card
`chat.name` comes from the other person's Telegram name, which they control and can set to something like
"Support https://evil.example/login". It is shown as is: "⚡ Quick reply to Support https://evil.example/login: one tap
sends it from your account". Previews are off globally (bot.py:266), but Telegram still makes the URL clickable.
The same happens in the /dms lines (:313), the check-in signal (:262) and the Sent/Cancelled edits. Those existed
before this batch, but the brief asked about names in cards.
Fix: `defang_urls(chat.name)` (and `c.name`, `reply['name']`) wherever a name is shown.

### L-4: the helpers change is right, but it shows a coverage gap
`quiet_hours=None` in `make_config` doesn't hide a bug. The old default made results depend on the wall clock, so
it never tested anything reliably, and the tests that care pass their own value. But a mutation run (`mut_quiet.py`)
shows that turning `in_quiet_hours` off in `review` (weekly review and digest), `meeting_prep` or `heartbeat` still
leaves all 376 tests passing. Only `checkins` and `inbox_watch` have tests for quiet hours.
Fix: add one test per job with `quiet_hours="00:00-23:59"` that asserts nothing is sent.

### L-5: small usability gaps in Quick
- /dms shows ⚡ Quick for chats past Telegram's 24-hour window. The card promises "one tap sends it", and the tap
  then says "Copy it and send it yourself". Only add the button when `c.can_reply`.
- `_waiting_chat` searches `unanswered()`, which is capped at `MAX_CHATS=8`. A card for a chat that drops to 9th
  says "Nobody is waiting there now." (R5). Look the chat up by id without the cap.

### I-1: snooze drops the hold on an ambiguous Gmail failure
If the archive call raises after Gmail already applied it (a timeout, for example), `done()` drops the hold. The
email is then archived with nothing bringing it back. This is no worse than before (the old order had the same
outcome). Safer: drop the hold only on a definite 4xx `HttpError`. Bringing back an email that never left is
harmless.

### I-2: requeue can race a fresh /triage
If /triage runs while an archive call is still waiting on Gmail and the archive then fails, `_requeue` puts the
failed email at the front of the new queue. The new card then answers "old". This is rare and gets fixed by sending
/triage again.

## What is correct
- **Only the owner's tap sends.** The callback pattern is anchored, and `_from_owner` runs before anything else.
  `/quickreplies` has the owner filter. No tool can change the list, the claims or the reply rows:
  `reply_telegram_dm` only proposes. `_deliver_dm`/`_send_as_owner` are reached only from `on_dm_button`.
- **Text is integrity-checked.** The index and CRC32 tag are re-checked against the current list, so editing,
  reordering or shortening the list refuses old buttons ("changed"). 32 bits is plenty against accidental equality,
  which is all this protects against: a forged callback from the owner's own client can only pick the owner's own
  texts.
- **No double send.** The claim is checked and set with no `await` in between, so a concurrent double tap sends
  once (the test uses gather). After a send, `record_sent` takes the chat off the waiting list. The claim is shared
  across cards for the same message. Pruning to 50 is harmless, because only the newest claims matter.
- **No wrong chat.** The chat id comes from the button data, and the chat must currently be waiting. Its name and
  id come from the store, not from the callback.
- **Failures are handled.** A refusal gives `pending` plus a retry button, so retry is possible. A timeout gives
  `unknown`, no button, and an ActionLog entry. No connection or no reply permission gives a retry. An expired
  window gives copy-it-yourself.
- **Callback data stays small:** at most about 34 bytes for `dmq:`, 28 for `dm:quick:`.
- **Birthdays:** names are owner-entered and defanged in /today. `list_birthdays` is read-only and safe in
  owner-absent turns. The brief line names the tool. Times use the owner's timezone.
- **Triage:** the claim-by-pop is kept. A failure requeues to the front so the same card works. The snooze cap is
  checked before the email leaves the inbox, and a failed archive undoes the hold. There's no Gmail call to "put it
  back" any more.
- **Quiet:** `_pause(None)` now clears `focus_until` for both the command and the button. There are no other
  callers, and `_focus_done` keeps its own checks.

Score: 7/10
Verdict: not ready (M-1 is a one-line fix plus a test. After that, ready. L-1 to L-3 are recommended.)
