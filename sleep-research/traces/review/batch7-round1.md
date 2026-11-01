# Review: batch 7, round 1

Commits reviewed:
- `4b6ac72`: urgent email can wake you during quiet time (opt-in). Files: inbox_watch.py, checkins.py `_inbox_job`, setup_chat.py.
- `7004aee`: "fix: batch 6 review findings in restore and bills", checked against `batch6-round1.md`.
- `9a277cc`: /birthdays (birthdays.py, bot.py wiring).

**Line numbers refer to the commit named.** Another session kept committing while this ran (`5168118` triage/focus, `09116b0` birthdays in /today). It also left uncommitted edits to bot.py, today.py and tools.py. I didn't review any of those.

**Tests:** on a clean export of `9a277cc`, `.venv/bin/python -m pytest -q` gave 362 passed and 3 failed. The failures are `test_review.py::test_weekly_review_runs_unattended_and_can_be_turned_off`, `test_newsletter_digest_is_opt_in` and `test_meeting_prep_stays_quiet_during_a_pause`. They aren't caused by these commits. The tests read the wall clock and the default `QUIET_HOURS` is 23:00-07:00, so they fail whenever the suite runs between 23:00 and 07:00 Chicago time (this run was at 04:00 UTC). See the nit at the end.

**Repros:** `/tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/b7/repros/repro_b7.py`. Run it as `python repro_b7.py <tree>`, where the tree is `.../scratchpad/b7/tree`, a clean export of `9a277cc`. The output is saved in `repro_b7.out` next to the script.

## What is correct

**Urgent email during quiet time (4b6ac72)**
- **Opt-in:** `urgent_wakes` is off by default. Off means fully quiet: `_inbox_job` returns before Gmail is asked (test covers it).
- **Covers /quiet too:** `quiet` includes DND as well as quiet hours. `check()` gets `urgent_only=quiet`, so a /quiet pause is handled like quiet hours.
- **No non-urgent alert leaks out.** In `_send`, `_urgent_only` sends everything not marked urgent to the queue. Only `urgent is True` goes out, under the 🚨 title.
  - When the classifier fails, the plain-list fallback has no `urgent` key, so everything is held. Repro A2: a "URGENT!!" subject with a broken classifier sends nothing during quiet time.
  - `urgent` is set only from `verdict.get("urgent") is True`.
- **Held alerts are delivered.** `_alert_digest_job` runs every hour whatever the alert mode, skips quiet and DND, and flushes the queue in pages. Turning hourly mode on or off doesn't strand anything: instant mode still gets the flush once quiet time ends.
- **No stale state.** `_urgent_only` is set again on every `check()`. `flush_digest` uses a different title, so it is never re-held.
- The /settings toggle and status line are wired correctly and owner-gated like the other `set:` buttons.
- **The urgent flag and untrusted email:** an email can easily get itself marked urgent ("URGENT: flight cancelled today"). A single wake-up for that is acceptable, because the owner opted in and the result is only a notification:
  - the alert shows the real sender address;
  - link previews are off globally;
  - the Reply button runs a draft turn that can't send by itself.

  What is not acceptable is that the number of wake-ups has no limit (N-12).

**Batch-6 fixes (7004aee)**
- **N-1 fixed.** `preview()` shows every stored memory, reminder, rule and the style in full, defanged, plus every list item (cut at 200 and stored at 200).
  - Habits and journal still show only as counts. I checked that neither reaches a model prompt, so that's fine.
  - Rules are now de-duplicated in `plan` (the batch-6 residual).
- **N-3 / N-4 fixed.** Each bill stores `reminder_id`. Replacing or deleting cancels exactly that id.
  - Legacy bills without an id fall back to the exact old text, never a prefix. Repro C2: replacing a legacy "Gas" cancels "Gas (40.00 USD) is due in 2 days" and keeps the owner's "Gas (check the meter reading)".
  - The bill is validated before any reminder exists.
- **N-5 addressed** with the minimum fix: "due on the 31st (or the month's last day)" is accurate even on the drifting days. The drift itself remains, which was the documented fallback.
- **N-6:** a same-day double tap logs once. But see N-11.
- **N-8 fixed.** `bills_next_id` takes the max of the counter and the existing ids, so ids are never reused, including for bills saved before the counter.
- **N-9 fixed.** `add_bill` sends "🧾 New bill …" from the bot itself after the owner-gated tool call.
- **Nit fixed:** "message is not modified" from an unchanged bill card is now caught.

**Birthdays (9a277cc)**
- `/birthday(s)` is `filters=owner`. `on_birthday_button` calls `_from_owner` first.
- The callback pattern `^bday:del:\d+$` is anchored, and the data is at most 17 bytes.
- `reply_markup` is passed by keyword everywhere.
- **Feb 29:** it is accepted (validated against 2024), Feb 30 is refused, and `next_birthday` maps Feb 29 to Feb 28 in other years.
- **The first reminder is never in the past.** If the day before at 09:00 has already passed, the reminder rolls to next year. The anchor is the first reminder date, and `next_occurrence` "yearly" keeps it.
- **Replace and remove cancel exactly their own reminder** by `reminder_id`. The test checks that an unrelated reminder survives.
- The reminder is a plain reminder (`run_as_task=False`), and its text is defanged when it fires (bot.py:910).

## Batch-6 findings: status

| Finding | Status | Evidence |
|---|---|---|
| N-1 restore preview clips | **Fixed** | Full text is shown and lists are shown. Side effect: a large export makes a 39-message card (N-13). |
| N-2 same text, two reminders | **Partly fixed** | Two reminders at different times now both restore. But the key is `(text, repeat, UTC HH:MM)` (restore.py:128-129), so weekly reminders on different weekdays and monthly reminders on the 1st and 15th still collapse into one (N-10). |
| N-3 replace keeps old reminder | **Fixed** | Repro C2, and the new tests. |
| N-4 delete by prefix | **Fixed** | Exact id, or exact legacy text. |
| N-5 drift / "in 2 days" | **Mitigated** | The text names the due day. The drift remains, as allowed. The tool note still says "monthly reminder 2 days before" (tools.py, nit). |
| N-6 Paid twice | **Partly fixed** | A same-month double tap is caught. A second tap for the same cycle in a different calendar month is not (N-11). |
| N-8 id reuse | **Fixed** | |
| N-9 no bot message | **Fixed** | |

## Findings

### N-10 Medium: restore still merges reminders that differ only by weekday or day of month (N-2 regression remains)
**Where:** restore.py:128-129 (`7004aee`). For repeating reminders the key is `(text, repeat, due in UTC as HH:MM)`.

**Scenario** (repro B1): the export has
- "Gym", weekly, Tuesday 14:00 UTC, and "Gym", weekly, Friday 14:00 UTC;
- "Pay rent", monthly, on the 6th and on the 20th, at the same hour.

The card says "⏰ 4 reminders", the result says "Restored: 2 reminders", and only one of each survives. Nothing says the others were dropped. The "Pay rent" case is the exact example batch 6 gave for N-2.

There is a second problem. The UTC hour moves when DST changes. An export made before a DST switch and restored on the same server after it no longer matches the existing reminder, so restoring twice stacks a duplicate.

**Fix:** for repeating reminders, key on local wall time plus the field that defines the cycle, in the owner's timezone:
- weekly and biweekly: the weekday;
- monthly: the day of the month;
- yearly: the month and day.

Or key on the exact `due` instant, as one-off reminders already do, accepting duplicates only when a reminder has advanced since the export.

### N-11 Low: ✅ Paid is tracked by the month of the tap, not the bill's cycle
**Where:** bills.py:163 `mark_paid(bill["id"], f"{today:%Y-%m}")`, and the same key in `bills_view` at :104.

**Scenario** (repro C1): Rent is due on the 1st.
1. The owner pays early on Oct 30 and taps ✅ Paid, which logs 1,200 and sets `paid = 2026-10`.
2. On Nov 2 they tap the card again for the same Nov 1 rent. The months differ, so it logs a second 1,200 (`expenses: [120000, 120000]`).

The opposite happens too: a bill due on the 31st that is paid late on Nov 1 sets `paid = 2026-11`. On Nov 30 the real November payment is refused: "already logged as paid this month".

**Fix:** key on the due date being paid. That is `next_due(day, today - grace)`, or simply the next due date shown on the card, which is what batch 6 suggested ("the due month"). Show "✅ paid" when `paid` equals the upcoming cycle.

### N-12 Low: urgent wake-ups have no limit, so any sender can ping the owner every 10 minutes all night
**Where:** inbox_watch.py:266-277 together with checkins.py:331 (`4b6ac72`).

With "Urgent email can wake me" on, every inbox check (default `INBOX_CHECK_MINUTES=10`) can send a 🚨 message. Whether a message is urgent is decided by a model reading text the sender wrote.

**Scenario:** a stranger sends "URGENT – your flight today is cancelled, call now" every 10 minutes from 23:00 to 07:00. That is up to 48 wake-ups a night. The owner's only defence is to find /settings → 🚨 and turn it off.

It is notification-only, there's no data exposure, and the owner opted in, so the severity is Low. The rate, though, is controlled entirely by the attacker.

**Fix** (any one of these):
- Cap urgent wake-ups per quiet window, say 2. After the cap, hold the rest and add "(N more urgent ones are waiting)".
- Let only senders the owner has written to, or who are in their memories or contacts, break through quiet time.
- Add a "🔕 No more tonight" button to the 🚨 message.

### N-13 Low: a maximum-size legitimate export makes a 39-message restore card, which probably hits Telegram flood control before the buttons
**Where:** restore.py:87-109 (full text, no overall cap) and :191-196 (each chunk sent in a loop). bot.py has no `AIORateLimiter` and nothing handles `RetryAfter`.

**Scenario** (repro B3): within the current caps, an export has 100 × 500-character memories, 50 × 300-character reminders, 20 rules and 300 list items. That is 126,185 characters, sent as 39 messages in a tight loop.

Telegram allows roughly 1 message per second per chat after a short burst, so a `RetryAfter` partway through is likely. When that happens, the last chunk with ✅ Restore is never sent, and the owner's own backup can't be restored. (I didn't test this against a live Telegram; the risk is inferred from the documented limits.)

Even when the sends succeed, 39 messages are a wall nobody reads, which brings back the H-1 "one blind tap" problem.

**Fix:**
- Above roughly 3 chunks, attach the full preview as a `.txt` document with a short summary card and the buttons, or
- send through `AIORateLimiter` and catch `RetryAfter`.

### N-14 Low: /birthdays breaks once the list passes about 4 KB; birthdays past the first 20 can't be removed
**Where:** birthdays.py:151 `reply_text(text, …)` and :167 `edit_message_text`, which send the whole list as one message. `MAX_BIRTHDAYS = 200`. `MAX_BUTTONS = 20` (:101).

**Scenario** (repro D2): 120 birthdays with ordinary names make 6,051 characters. Telegram answers 400 "Message is too long", so `/birthdays` and the 🗑 refresh both fail with an unhandled exception. With short names the limit is reached at about 140 entries, and the code allows 200.

Separately, only the 20 soonest get a 🗑 button, and there is no remove command. A wrongly entered birthday that is months away can't be deleted. The only way is to "replace" it under the same name, which keeps it.

**Fix:**
- Send through `split_message`, with the buttons on the last chunk, or show only the next 30 days plus "and N more".
- Add `/birthday remove <name>`, or page the buttons.
- Catch `BadRequest` on the edit, as bills.py now does. The "Already removed." double tap also re-renders an identical card and raises "not modified".

### N-15 Low: the "day before" heads-up drifts around leap years and is silently skipped for a birthday tomorrow
**Where:** birthdays.py:118-126. The yearly reminder is anchored on the reminder date, not on the birthday.

**Scenario** (repro D1):
- **Feb 29 birthday added in a leap year** (Jan 10, 2028): the reminder is anchored on Feb 28. In 2029-2031 it fires on Feb 28, which is the day the birthday is observed (0 days ahead), and says "is on Feb 29".
- **Feb 29 birthday added now:** the reminder is anchored on Feb 27, so in 2028 it fires 2 days early.
- **Mar 1 birthday:** the reminder is anchored on Feb 28, so in leap years it fires 2 days early.

Repro D4: a Nov 2 birthday added on Nov 1 at 10:00 gets its first reminder on 2027-11-01. Nothing is said this year, but the reply still says "I'll remind you the day before".

**Fix:**
- Anchor on the birthday and schedule a one-off reminder each year. When it fires, schedule `next_birthday(...) - 1 day` at 09:00, or let `_reminder_job` recognise a `bday:` reminder.
- At the least, for a Feb 29 birthday in a non-leap year, the text should say "Feb 28 (Feb 29 this year)".
- For the day-before case, send the heads-up now ("Sam's birthday is tomorrow"), or say "next reminder: Nov 1, 2027".

### N-16 Low: a failed urgent send duplicates the held non-urgent alerts
**Where:** inbox_watch.py:273-277. The queue is written before `notify()`. If `notify` raises, `check()` never reaches `mark_emails_seen`, so the next check classifies the same emails again and appends them again.

**Scenario** (repro A1):
1. During quiet time, urgent "flight cancelled" and non-urgent "Sam lunch" arrive.
2. The 🚨 send fails with a Telegram `NetworkError`.
3. The next check succeeds.

The queue is `['abc222', 'abc222']`, and the morning digest says "📬 2 important emails" with "Sam lunch" twice. Hourly mode had the same behaviour before this commit, but quiet time makes it more likely: a whole night of retries piles up.

**Fix:** when appending, skip ids already in `held`: `ids = {h["id"] for h in held}`.

### Nits
- **Digest title** (inbox_watch.py:231): "📬 N important emails this hour" is wrong for a batch held all night. Say "while you were away" when the queue is older than an hour.
- **Silent drop** (:274): `held[-MAX_DIGEST:]` still drops anything past 100 without a word. That is now more reachable over an 8-hour night (batch-6 M-4 residual).
- **Ordering in instant mode:** once quiet time ends, a fresh email can go out at the next inbox check, up to 59 minutes before the night's held digest, so alerts arrive out of order. Flushing the queue on the first non-quiet `_inbox_job` would fix it.
- **Instance state:** `_urgent_only` is stored on the instance and read with `getattr`. Passing it to `_send` as a parameter would be safer.
- **Restore drops past reminders silently** (restore.py:65, pre-existing): repeating reminders whose `next_run` has passed are left out. Repro B2: an export 2 days old restores 0 of 2 daily or weekly reminders, and the card says nothing. A 7-day backup loses every daily reminder. Roll repeating reminders forward with `next_occurrence` instead.
- **Restore and invisible characters:** memories, reminders and style keep newlines and bidi or zero-width characters (only lists and rules are collapsed). Nothing is hidden by length any more, but a run of blank lines can push an instruction into a separate-looking chunk. Collapse whitespace and strip `Cf` characters for all three.
- **Not exported:** birthdays (like bills) aren't in the export, but their reminders are. Moving to a new server gives "🎂 …" reminders with no birthday in /birthdays, and re-adding one makes a duplicate.
- **Parser:** `parse_birthday("Mom on Mar 14")` saves the name "Mom on". "Mom 3/14" and "14.03." are refused (fine, but the hint could mention `3-14`). A year on a Feb 29 is accepted even when it isn't a leap year ("1962-02-29").
- **Bill names:** the bill notice and /bills show the name undefanged. A 40-character name taken from an email could hold a bare domain, which Telegram makes clickable (with no preview). Defang it like the reminder text.
- **Clock-dependent tests:** the three test_review.py tests rely on the wall clock being outside quiet hours. Pass `quiet_hours=None` in their `make_config`.

## Verdict
**Urgent wake-ups:** done carefully. Nothing non-urgent leaks during quiet time, held alerts are flushed whatever the mode, and the toggle is opt-in. The remaining issues are the unlimited rate (N-12) and a duplicate when a send fails (N-16).

**Batch-6 fixes:** they close N-1, N-3, N-4, N-8 and N-9 properly, with sound handling of legacy bills.

**Birthdays:** the feature is owner-gated and cancels exactly its own reminder.

What keeps it from ready:
- **N-10:** restore still silently merges real, distinct reminders: weekly on different days, and monthly on the 1st and 15th. This is the case batch 6 named.
- **N-11:** the Paid fix can still double-log a cycle.
- Small robustness gaps: the restore card's size (N-13), the length of /birthdays (N-14), and the leap-year heads-up (N-15).

None of these is a security hole.

Score: 7/10
Verdict: not ready
