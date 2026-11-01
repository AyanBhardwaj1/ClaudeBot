# Batch 9 review, round 1: 8ba4b5f (batch 7 fixes) and bc831a0 (export/restore of bills, birthdays, quick replies)

Reviewer: independent. Repros: `/tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/b9/r1..r4`.
Tests: 381 passed. The tree now also holds 200099f, which landed during this review; line numbers are from HEAD.

## Batch 7 status

| Finding | Status | Notes |
|---|---|---|
| N-10 restore merges weekly/monthly | **Fixed** | Key = text + repeat + local HH:MM + weekday / day of month / month-day. DST-proof. Residual for days 29-31 (P-3). |
| N-11 Paid by month of tap | **Fixed** | `paying_for` brute-forced over days 1-31 × 3 years (r3): always the nearest due date, never more than 15 days away, Feb and the 31st clamp correctly, and today == due returns today. Display nit in P-5. |
| N-12 unlimited wake-ups | **Fixed** | At most 3 per 12 h. A capped urgent alert falls through to the digest (r4). Counter nit in P-4. |
| N-13 39-message card | **Fixed, then regressed by bc831a0** | `.txt` plus a short card. The short card doesn't mention bills, birthdays or quick replies (P-1). |
| N-14 /birthdays length, removal | **Fixed** | `split_message`, buttons on the last chunk, `/birthday remove Name`, names defanged, `BadRequest` caught. |
| N-15 heads-up passed | **Mitigated** | The reply now says when this year's heads-up has passed. The Feb 29 / leap-year drift remains (accepted). |
| N-16 duplicate held mail | **Fixed** | `already` id set. |

## Findings

### P-1 Medium: restore silently replaces the owner's quick replies, and the big-export card doesn't mention them
**Where:** restore.py:195 (overwrite), :242-247 (summary card), :147 ("Nothing you have now is deleted"), :102 (cleaning).

**Repro r1.** The owner has the quick replies "On it | Running late". They receive an export with 40 ordinary memories, three quick replies ("Sure, I'll send the money now", "Yes, go ahead and wire it", "Approved"), a $9,000 bill and a birthday.
- The preview passes 3 chunks, so the owner gets `restore-preview.txt` plus a card that says only: "This export would add 40 memories, 0 alert rules, 0 reminders and 0 list items. Every one is in restore-preview.txt…". Quick replies, bills and birthdays aren't mentioned.
- After ✅ Restore, the result line says "40 memories, 1 birthdays, 1 bills". The owner's quick replies are now the three planted ones. Nothing says theirs were replaced.
- In the small-card case the quick replies are shown, but the card still says "would add… Nothing you have now is deleted". That is false for quick replies (and for the writing style, which was already like this).

These texts go out from the owner's own Telegram account on one tap of ⚡ Quick. Restore also keeps zero-width and bidi characters: `" ".join(str(t).split())` leaves out U+200B, U+202E and similar. A 100-character reply can therefore look like "On it 👍" on the 60-character button while it carries a hidden tail. The card does show the full text, though without making that tail visible.

**Fix:**
- Always print quick replies verbatim in the short card. They're at most 3 × 100 characters. Write it as "⚡ Replaces your quick replies (now: …) with: …".
- Add counts for bills and birthdays to the card.
- Add "quick replies replaced" to the result line.
- Strip `Cf` characters from quick replies (and from bill and birthday names) in `plan`.
- Drop "Nothing you have now is deleted", or make it true by keeping the existing replies.

### P-2 Low: a bill saved before reminder ids gets two reminders after export → restore
**Where:** export.py:33/42. `owned` collects `reminder_id`, which is `None` for bills made before 7004aee, so their reminders stay in the plain list. Restore then adds that plain reminder, and `add_bill` adds a second one.

**Repro r2(b):** the new server has 2 × "🧾 Rent (1,200.00 USD) is due on the 1st". Removing the bill later cancels only its own reminder, so the plain copy keeps firing for good.

The same happens if an old export (bill reminders in the plain list) is restored after a new one.

**Fix:**
- In export, also leave out monthly reminders whose text equals `reminder_text(bill)` for each bill, as `_cancel_bill_reminder` already does.
- In restore, skip plain reminders whose text matches a bill or birthday being added (`reminder_text(...)` / `"🎂 {name}'s birthday is on …"`).

### P-3 Low: a monthly reminder anchored on the 29th-31st still duplicates on a second restore
**Where:** restore.py:172, `"monthly": local.day`.

A reminder anchored on Jan 31 runs on Nov 30, then on Dec 31.

**Repro r2(a):** a snapshot taken when the next run was Nov 30 is restored on the same server after the reminder has moved on to Dec 31. Result: "1 reminders", and two "pay card" rows. The export doesn't carry `anchor`, so on a fresh server the copy is anchored on the 30th and drifts there for good. Yearly Feb 29 has the same issue.

**Fix:**
- Export `anchor` and restore with it.
- For monthly, key on `min(day, 28)` when the day is 28 or later, or on "is last day of month".

### P-4 Low: a failed urgent send still uses up a wake-up
**Where:** inbox_watch.py:268-276, 283. `_may_wake` records the slot before `notify`.

**Repro r4:** three checks during a Telegram outage use all 3 slots. A real urgent email afterwards goes silently to the digest. That digest also drops the urgent flag (the `fields` tuple), so it looks like any other email, and nothing says "N urgent ones are waiting".

**Fix:**
- Record the wake only after `notify` succeeds: check before, append after.
- Keep `urgent` in the held fields and mark those emails 🚨 in the digest.

### P-5 Low: the /bills card can say "✅ paid" next to a due date that isn't paid
**Where:** bills.py:122. Take a day-20 bill paid on Oct 20 and look at it on Nov 3. `paying_for` gives Oct 20, which is nearer than Nov 20, so the line reads "due Nov 20 ✅ paid".

Likewise, paying the November bill 17 days early is refused as "already logged as paid for Oct 20".

**Fix:** show the cycle the ✅ refers to ("✅ Oct 20 paid"), or show ✅ only when `paid == next_due(...)`.

### Nits
- Restore skips an incoming bill or birthday whose name already exists, even when the amount, day or date differs. The card listed it as "would add". Say "kept your existing Rent" in the result.
- "1 birthdays, 1 bills": plural.
- `/birthday remove Mom Mar 14` saves a birthday named "remove Mom", because `parse_birthday` succeeds. Refuse names that start with remove/delete.
- The 🗑 refresh edits the last message (the one with the buttons) to chunk 0 of a split list, so the header part shows twice. Use a short "Removed. /birthdays for the full list" edit instead.
- `"bills": null` in a crafted file makes `plan` raise TypeError, which shows as "damaged file". That's safe, but `payload.get(k) or []` is cleaner.

## Correct
- Restore validates amounts, days and months. NaN, inf, ≤0 and >1e9 amounts are rejected, and days outside 1-31 too. Unknown currency raises ValueError, which is caught. Non-dict entries are caught. Birthdays go through `parse_birthday`, which checks the day in month (Feb 29 allowed). Names are cleaned to 40 characters.
- Restoring twice doesn't double bills or birthdays (deduped by lowercased name) or new-format reminders. Bill and birthday reminders are excluded from the export and recreated by `add_bill` / `add_birthday`.
- Older exports with no `birthdays`, `bills` or `quick_replies` keys restore as before. The export's own `"quick_replies": null` is handled.
- Quick replies keep the normal-path caps (3 × 100 characters). The preview shows them in full and defanged. Stale ⚡ buttons are protected by `quick_tag`.
- The bill and birthday preview lists every entry, defanged. The restore button still checks the owner, and callback data is ≤64 bytes.
- `_may_wake` applies only in quiet time (`urgent_only`). Capped alerts are held, not dropped. The held queue is deduped by id.
- `/birthday remove` is owner-filtered, matches the exact lowercased name and cancels the reminder by id.

Score: 7/10
Verdict: not ready. P-1 is a small fix: put quick replies, bills and birthdays on the short card, and say "replaces" instead of "add". The rest can follow.
