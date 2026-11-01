# Batch 12 review, round 1 (e7a8275..HEAD: 5356fc7, ad597e4, d2da6d0)

Repro scripts: /tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad/b12/{r1.py,test_week_repro.py}
Suite: 392 passed.

## Medium

M1. `/week` can go over Telegram's 4096-char limit and fail outright. claudebot/today.py:99,113,130
Titles are `defang_urls(clip(title, 40))`: they are clipped *before* defanging, and every "." inside a URL-ish
match grows to "[.]". A title like "www." followed by dots grows to about 115 chars. 7 days x (6 items + "...and N more")
comes to 5312 chars (reproduced in test_week_repro.py::test_length), so `reply_text` raises BadRequest
"Message is too long" and the owner gets nothing. Calendar titles are untrusted: Google auto-adds invites from anyone.
Ordinary titles stay around 3K. Fix: defang first and clip after (`clip(defang_urls(t), 40)`), and/or cap the
final text (for example `text[:4000]`, or split by day).

M2. `clean_quick` regression: ZWJ is now dropped in real text that the old code kept. claudebot/business.py:75-79
- Emoji with a skin tone: "👩🏽‍💻" becomes "👩🏽💻" (two emoji). The skin-tone modifier U+1F3FB..1F3FF is category Sk, not So,
  so `is_emoji(before)` is False. "👨🏻‍🦰" breaks the same way.
- Indic scripts: Sinhala "ශ්‍රී" (Sri) and Malayalam chillu "ന്‍" lose their ZWJ, which changes how they render.
  ZWNJ (U+200C) is still dropped, as before, so Persian "می‌خواهم" is rewritten as "میخواهم".
Fix: also accept the Sk modifiers (and FE0F after them) as `before`; keep U+200C/U+200D between two letters or marks
(category L*/M*).

## Low
- L1 today.py:96-100: a multi-day or all-day event shows only on its start day. A vacation that began before today is
  missing from the whole week. Fix: add it to every day in [start, end).
- L2 today.py:104-111: within a day, items are not in time order (events first, then reminders, bills, birthdays).
  The repro printed "23:38 weekdays" before "23:33 monthly". It also lists briefing and scheduled-task reminders
  under ⏰ with their internal text.
- L3 today.py:107: a repeating reminder more than 7 steps overdue never reaches the week. Startup advances overdue
  rows (bot.py:435), so this is unlikely in practice.
- L4 business.py:84-87: a run of tag characters after 🏴 is kept without limit and without a terminating U+E007F,
  so hidden ASCII can ride along ("ok🏴"+tags spelling "hidden text" is kept). Only the owner sets quick replies.
  Fix: keep tags only when the sequence ends in E007F, at most 6 tags.
- L5 business.py:426-430: the quiet-hours end parse is fine. None or a malformed spec never gets there:
  `in_quiet_hours` returns False for None, and `parse_quiet_hours` already raises on a malformed spec
  (that raise predates this change). "22:00-06:00" gives 06:00 the next day. A tap at 02:00 gives 06:00 the same
  day. A daytime window "09:00-17:00" gives 17:00. The `except` fallback to 08:00 is unreachable but harmless.

## Correct
- No infinite loop in `/week`: the loop is bounded by `range(7)`; repeat "none" gives None and breaks; weekly,
  weekdays and monthly expand correctly; an ancient anchor (33 years) finishes fast.
- Telegram output has no parse_mode, so the text can't inject markup. Titles, reminder text, bill names and
  birthday names are defanged; bill and birthday names are already capped at 40 chars.
- `_anchor_fits`: Jan 31 -> Feb 28, Mar 31 and Apr 30 across the EST/EDT change are accepted, Mar 28 is rejected,
  and yearly Feb 29 -> Feb 28 is accepted. `plan()` now applies the anchor before advancing.
- `mark_paid` returns the settled date. The truthiness of the old bool callers and tests still holds, since a date
  is truthy.

Score: 7/10
Verdict: not ready (fix M1, M2; both are one- or two-line changes)
