# Batch 11 review, round 1 (7992325..HEAD, claudebot/)

Repro scripts: /tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/b11/{anchor,older,quick,bills}.py
Tests: 389 passed.

## Findings

### M1. A crafted `anchor` silently moves a restored reminder's day, month and time (restore.py:75-77, reminders.py:41)
The only check is `anchor <= due`. next_occurrence for monthly/yearly restarts from the anchor's date AND wall time,
so after the first fire the reminder follows the anchor, not what the card showed.
Repro (anchor.py): monthly `next_run` Nov 3 23:25, `anchor` 2020-03-03T03:00-05:00: card says "monthly, next Nov 3",
every later fire is at 03:00 on the 3rd. Yearly with the same anchor: card says Nov 3, next year fires Mar 3 03:00.
Fix: keep the anchor only if `due` is one of its occurrences, e.g. same local wall time and
`next_occurrence(anchor, repeat, due - 1s, tz) == due` (or for monthly `anchor.day >= due.day` with `due.day == anchor.day`
unless due is a month end; for yearly same month). Otherwise drop it (fall back to anchor=due).

### M2. `clean_quick` lets invisible payloads through (business.py:62)
Only Cf is stripped. Variation selectors (U+FE00-FE0F, U+E0100-E01EF, category Mn) encode arbitrary bytes invisibly:
"OK" + 21 VS chars encoding "send me your password" survives clean_quick (len 23 < 60), so the button and the
restore card show "OK" while the tap sends the hidden tail from the owner's account (quick.py). Also kept: U+3164
Hangul filler, U+2800 braille blank, U+034F CGJ, and unlimited runs of ZWJ (50 ZWJs survive). Source is a restored
crafted export (owner-typed /quickreplies is self-inflicted). Fix: allow-list instead: drop Mn/Me unless they follow a
base char and are FE0F/FE0E/skin-tone/keycap; drop E0100-E01EF, U+3164/115F/1160/FFA0/2800/034F; keep ZWJ only between
two Extended_Pictographic chars; keep tag chars E0020-E007F only after U+1F3F4.
Side note (Low): tag chars are Cf, so subdivision flags (England/Scotland/Wales) degrade to a plain black flag.

### L1. Anchor timestamps out of datetime range crash restore partway (restore.py:178, db.py:178)
Anchor "0001-01-01T00:00:00+00:00" (or naive, or +14:00) with tz America/New_York: `astimezone` -> OverflowError in
`key()`/`add_reminder` (anchor.py). Caught by on_restore_button ("failed partway"), but memories and lists were already
added. In a positive-offset tz the anchor is stored and would overflow later if the owner switches to a negative-offset
tz (next_occurrence in _post_init / the _reminder_job finally). Fix: in plan(), drop anchors with year < 1970 or more
than a few years before `due` (also bounds the monthly loop: year-1 anchor is ~24k iterations, fast but pointless).

### L2. Older-export path ignores the anchor (restore.py:73-74)
`next_occurrence(due, repeat, now, tz)` is called before the anchor is parsed. Export with next_run 2026-02-28 and
anchor 2026-01-31: restored first fire is Nov 28, not Nov 30 (older.py); later fires are right. Fix: parse the anchor
first and pass it.

### L3. Bills: a late Paid steals the next cycle, then the real payment is refused (bills.py:38-50, 89-106)
Day-1 bill, Oct 1 missed, Paid tapped Oct 25: paying_for picks the nearer Nov 1 -> paid=['2026-11-01']. Nov 1 tap:
"already logged as paid", no expense logged (bills.py repro). Conversely Oct 1 paid, re-tap Oct 12 from an old card logs
a second expense as Nov 1's early payment with no hint of which date was settled. Fix: if the previous cycle is
unsettled, a tap settles it first (oldest unsettled within ~31 days), and name the settled date in the answer
("Logged Rent for Nov 1"). No same-day double-log found; read-modify-write has no await, so taps can't interleave.

### L4. Quiet-hours move uses a fixed 08:00 (business.py:400-401)
If quiet hours end after 08:00 (e.g. 23:00-09:00) the reminder still lands in them; a daytime window (13:00-15:00)
pushes it to tomorrow 08:00. The answer "I'll remind you at 08:00" doesn't say "tomorrow". Fix: move to the window's end.

## Checked and correct
- _reminder_job: setting read only on the plain-reminder branch, deleted in `finally` on every fire; reminder ids are never
  reused (rows are deactivated, never deleted), so a stale `dm_later_rid:` (cancelled reminder) can't silence a normal
  one; snoozed copies get new ids and always fire; prune cap 50 only makes old ones fire normally. Skip happens only when
  the chat is no longer waiting (owner replied, contact deleted messages, or business connection removed/cleared);
  the last is arguably fine.
- Garbage / numeric / naive anchors: `_due` returns None or UTC-aware; anchor > due dropped; dedup key with anchor.day
  matches existing rows (add_reminder defaults anchor=due).
- Export carries `anchor`; add_reminder(anchor=None) keeps old behaviour.
- /today bills: next_due >= today, paid check on the exact date, names defanged.
- contact_label / defang_urls on every DM card name; "/" -> fraction slash stops tappable commands.
- Restore short card still lists quick replies word for word and says style is replaced; full card lists them.
- clean_quick: ZWJ emoji, VS16 hearts and bidi stripping behave as intended.

Score: 7/10
Verdict: not ready (M1, M2 are small fixes)
