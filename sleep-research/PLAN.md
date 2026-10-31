# Plan: ClaudeBot 1.1, "tells you first, and you can check it"

**Problem anchor:** The market's top pain is assistants that are unreliable or act behind your back (user_needs.md #1, #2). Its biggest gap versus competitors is proactivity that feels like judgment (competitors.md §b #1, #3). 1.1 makes ClaudeBot surface what needs you (replies you owe or are waiting on, real calendar problems), keeps every action visible and reversible, and fixes the defects triage found. The problem stays fixed; methods may change.

Source of picks: `traces/triage/round1.md`, from a same-family reviewer (provisional).

Assumptions (the user is away and said to proceed):
- Defaults are chosen to be quiet.
- Every new proactive message goes through the existing quiet hours and budget.
- Nothing new sends email or changes data without a tap.

## Acceptance criteria (each has an offline test)

### Defects first
- **D3, owner-only destructive tools.** In a turn the owner didn't start (owner_present=False), these return a NeedsOwner error and do nothing:
  - modify_email
  - update_calendar_event
  - delete_calendar_event
  - forget
  - cancel_reminder

  In owner turns they behave as before.
- **D1, inbox-failure notices.** After `INBOX_FAILURE_NOTICE` consecutive failed inbox checks (default 3), the owner gets exactly one message saying alerts are paused, and why: Google not connected, token revoked, or a network error. They get one "working again" message on the first success after that. Ten failures in a row still produce one notice.
- **D2, calendar listing.** `list_events` pages through results up to `max_results` (≤250), and the tool exposes `max_results`.
- **D5, prompt claim.** The system prompt no longer claims custom labels.

### C12: /reminders
- `/reminders` lists every active reminder, task and briefing, with its next run in local time and its repeat rule, plus one cancel button each (`unrem:<id>`).
- The cancel button deactivates and unschedules the reminder, is owner-only, and a second tap says "Already cancelled".
- Works with no Claude call (so also when over budget). When there are no reminders, it gives an example.

### C6: find_free_time tool
- A pure function `free_slots(busy, window_start, window_end, duration, day_start, day_end, tz, limit)` returns up to `limit` non-overlapping slots that:
  - are at least `duration` long;
  - sit inside working hours on each day;
  - don't overlap any busy interval;
  - start in the future.
- All-day events don't block time unless marked busy. Events marked `transparency: transparent` never block.
- Tested on:
  - overlapping and back-to-back events
  - an event spanning midnight
  - a window with no free time (empty list)
  - a duration longer than the working day
- The tool `find_free_time(start, end, duration_minutes, max_slots)` gets its busy intervals from a paged `list_events`.

### C2: reply tracking (/waiting, and Nudge)
- `Google.thread_states(query, max_threads)` returns, per thread:
  - the last message's id, from, to, subject and date;
  - `last_is_mine` (true when the last message has the SENT label);
  - the message count.
- `find_reply_gaps(google, client, tracker, config, now)` returns two lists, **waiting** and **owed**:
  - **waiting**: threads whose last message is mine, 3-14 days old.
  - **owed**: inbox threads whose last message isn't mine, 1-7 days old.
  - One Haiku structured call keeps only threads where a reply is actually expected. Subjects and snippets are fenced as untrusted data, and invented ids are ignored.
  - If Haiku fails, it falls back to the unfiltered lists, capped at 5 each.
- `/waiting` shows both lists, each item with a button:
  - **Nudge** for waiting items: drafts a follow-up and shows it, without sending.
  - **Reply** for owed items: same flow as the alert ✍️ button.
- Callback data carries only a Gmail id that matches the existing GMAIL_ID pattern.
- The prompt sent to Claude carries only ids. Claude reads the email itself through `read_email`.

### C1: heartbeat check-ins
- A job every `HEARTBEAT_HOURS` (default 3). It runs only outside quiet hours, only if Google is connected, and only if check-ins are on (`/settings` toggle, default on).
- **Signals are found by code, not the model:**
  - calendar conflicts in the next 24h (overlapping events, ignoring all-day and transparent ones)
  - the first event tomorrow before 09:00 (only after 18:00 today)
  - owed replies older than 2 days
  - waiting-on threads older than 5 days
- Each signal has a key, e.g. `conflict:<idA>:<idB>` or `owed:<threadId>`. A key that was already mentioned is never mentioned again (stored in the `heartbeat_seen` setting, pruned after 14 days).
- No new signals: no model call and no message.
- New signals: one Haiku call, no tools, structured output `{notify: bool, message: str}`. Signal text is fenced. The output is defanged and capped at 600 characters.
- At most `HEARTBEAT_MAX_PER_DAY` (default 3) messages per local day.
- The message carries buttons only from a fixed set (the /waiting view, the calendar view), never from model output.
- Cost per run is recorded under the `heartbeat` source.

### C13: drafts-only mode
- A `/settings` toggle "Email: send with Undo / save as drafts". With drafts on, `send_email` saves a Gmail draft and returns `{"status": "saved as draft (not sent)"}`. The outbox and the Undo button are not involved.
- `approve_held_email` is unaffected.

### C7
- `/help` and the WELCOME text mention "send a photo of a flyer or a ticket and I'll add it to your calendar".

## Files

| File | Action | Why |
|---|---|---|
| claudebot/tools.py | UPDATE | D3, D2, C6 tool, C13 |
| claudebot/google_services.py | UPDATE | list_events paging, thread_states |
| claudebot/scheduling.py | CREATE | pure free_slots |
| claudebot/replies.py | CREATE | reply-gap finding (C2) |
| claudebot/heartbeat.py | CREATE | signals and check-in composition (C1) |
| claudebot/checkins.py | CREATE | Telegram mixin: /reminders, /waiting, nudge/reply/unrem buttons, heartbeat job, inbox-failure notices |
| claudebot/bot.py | UPDATE | wire handlers and jobs, commands menu |
| claudebot/setup_chat.py, settings.py | UPDATE | /settings toggles for check-ins and drafts-only, help text |
| claudebot/agent.py | UPDATE | D5, new capabilities in the prompt |
| tests/test_release_11.py | CREATE | all of the above |
| README.md, CHANGELOG.md, docs/index.html | UPDATE | document 1.1 |

**Patterns to mirror:**
- Inbox classifier structured call and fencing: inbox_watch.py:148-185
- Callback handlers with an owner check: buttons.py:68-95
- List view with cancel buttons: bot.py:805-833
- Settings toggles: setup_chat.py `set:alerts`

## Not building
- C4 voice, C11 action log, C21 Telegram Business. These are backups for the next session.

## Risks
- **Heartbeat noise.** Mitigations: code-found signals, dedupe, a daily cap, quiet hours, and an off switch.
- **Gmail call volume for thread_states.** Capped at 25 threads per query.
- **Haiku misjudging "expects a reply".** It falls back to listing; the owner sees ids and decides.

## Changes after plan review (traces/plan/round1.md)

Every finding was accepted.

- **C6:**
  - Transparency defaults to busy and the API leaves the field out for busy events, so only `transparent` events and declined invites are free. All-day events count as busy.
  - `create_event` marks new all-day events as free, matching the Calendar UI default.
- **D2:**
  - Truncation is visible: `list_calendar_events` returns `truncated: true`.
  - `find_free_time` only trusts slots before the last event it saw, and says so.
  - Short pages that still carry a `nextPageToken` are tested.
- **C1:**
  - The model never writes the message. Haiku returns the numbers of the signals worth a ping; the code writes the lines (quoted, clipped, defanged).
  - Check-ins only use reply threads Haiku judged (`judged_only`); when judging fails, nothing unjudged is pinged.
  - Conflict keys use sorted ids.
  - **Noise rule from the review:** reply-only check-ins happen at most once a day. Other reply items ride along with calendar check-ins or wait in /waiting.
- **D1:**
  - Checks in quiet hours, or when Google isn't connected, don't count either way.
  - The failure count lives in the database, so restarts after /settings changes don't reset it.
- **D3:** Only `trash` needs the owner. Archive, star and mark-read are reversible and are legitimate scheduled tasks.
- **Acceptance:** whether C1 and C2 are actually useful can't be shown offline. It is judged by the triage's 14-day dogfood targets:
  - median ≤3 check-ins a day;
  - ≥40% tapped or answered within 2 hours;
  - not switched off;
  - no repeats of that day's alerts or brief;
  - heartbeat spend under $0.50 a month (`/usage` source "heartbeat").
