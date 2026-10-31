# Plan review, round 1

## Prompt

Review a build plan for a product you did not write. Read the files yourself:
- /home/user/ClaudeBot/sleep-research/PLAN.md (the plan)
- /home/user/ClaudeBot/sleep-research/BRIEF.md (product, security model, constraints)
- /home/user/ClaudeBot/sleep-research/traces/triage/round1.md (why these features were picked)
- The code it changes: /home/user/ClaudeBot/claudebot/tools.py, google_services.py, inbox_watch.py, bot.py, buttons.py, setup_chat.py

Answer:
1. Which acceptance criteria can the planned tests NOT actually verify offline, and what would?
2. Gmail and Calendar API facts the plan gets wrong, for example:
   - the SENT label on the last message of a thread;
   - threads.get with format=metadata;
   - all-day events and transparency in events.list;
   - paging events.list with pageToken.
   Check against the installed google-api-python-client discovery docs under /home/user/ClaudeBot/.venv if needed.
3. Security holes in the plan relative to the security model: untrusted email or calendar text reaching the model or the owner unfenced, any unattended action, and whether callback data stays inside 64 bytes.
4. Will the heartbeat be noisy or duplicate existing inbox alerts and the daily brief? What single rule would most reduce noise?
5. What is the single most important thing to build first?
Do not add components; risks choose tests, they don't grow the plan.

=== SCOPE LIMITS (these bound what you PROPOSE, never what you look for) ===
Report anything that is actually wrong, including a rare case if this project actually produces it. Then keep fixes in scope:
1. This is a product, not a security research project. Verification is welcome; over-defense is not.
2. Do not propose hashing, fingerprinting, or digest-binding schemes.
3. No speculative machinery (flags, compat layers, wrappers, frameworks) unless you can point to a current defect it fixes.
4. No corner-case obsession unless you can show the case arises here.
5. A clear sentence beats a scored checklist nobody maintains.
Say plainly when something is correct. Do not manufacture findings.

Write your review to /home/user/ClaudeBot/sleep-research/traces/plan/round1.md: a "## Prompt" section with this prompt, then "## Response". Modify no other files. Return a 250-word summary with concrete changes to the plan.

## Response

**Note on what I reviewed.** Implementation started while I was reviewing. `heartbeat.py`, `replies.py`, `checkins.py` and `scheduling.py` exist (untracked), `tools.py`, `google_services.py` and `bot.py` have changes, and `tests/test_release_11.py` passes (25 tests). I reviewed the plan and checked each finding against that code. Where the code already does better than the plan's text, I say so, so the plan can be brought in line with it.

### Verdict

The plan is mostly sound. The picks follow the triage. The callback, owner-check and fencing patterns are copied from the right places. No new path sends email without a tap. It has five real problems:
- An all-day rule that contradicts the Calendar API.
- An inbox-failure notice that will fire falsely every night and repeat after every restart.
- A heartbeat that turns untrusted subjects and event titles into free text in the bot's own voice.
- A heartbeat that pushes *unfiltered* reply items when Haiku fails.
- A noise budget that matches the triage's failure threshold.

All five are fixed by changing rules, not by adding parts.

### 1. Criteria the offline tests can't verify, and what would

| Criterion | Why the planned test doesn't prove it | What would |
|---|---|---|
| D2 paging | `FakeEvents` always returns full pages. The real API "may return fewer events than maxResults, or none at all, even if there are more" (discovery doc, `events.list.maxResults`). The test also pins the call count (`len(events.calls) == 2`), which pins the page size instead of the behaviour. | Offline: one fake page that is short or empty but still carries `nextPageToken`. Assert all events come back, not how many calls were made. The current loop is correct here, because it continues on the token, not on page length. |
| C6 all-day / transparency | `test_busy_comes_from_timed_opaque_events_only` uses hand-written dicts, including `"transparency": "opaque"`. The API doesn't return that field for opaque events (see §2). The test verifies a shape the API doesn't send. | Offline: feed raw, API-shaped items through `Google.list_events` and then `busy_from_events`, so the field mapping is tested too. Once, live: save one real `events.list` response as a fixture. It should include an all-day event shown as Free, one shown as Busy, a declined invite and a timed event. |
| C2 `last_is_mine` | A fake thread can't show how Gmail labels drafts, sent-to-self mail, or the order of messages in a thread. | Once, live: save one `threads.get(format="metadata")` response for a thread with a draft reply in it, and use it as the fixture. |
| C2 "a reply is actually expected" | The quality of Haiku's judgement can't be tested offline. Tests can only show fencing, that invented ids are dropped, and the fallback. | The triage's 14-day dogfood numbers (tap rate, owner keeps it on). Say so in the plan, so a green test run isn't read as "C2 works". |
| C1 "not noisy" | Offline tests can show dedupe, the cap and quiet hours. They can't show the pings are wanted. | The same dogfood: at most 3 a day, at least 40% tapped, zero repeats of that day's alert or brief. |
| D1 "exactly one notice", "ten failures still one notice" | It holds only within one process. Every `/settings` change calls `request_restart()` (`setup_chat.py:381`), and Fly and Railway restart the process too. The planned test never restarts. | Offline: build a second bot (or watcher) on the same database and assert that no second notice is sent. Real exception types: raise `google.auth.exceptions.RefreshError` in the fake, which is what an expired or revoked refresh token raises. Once, live: revoke the app in Google account settings and watch for the notice. |

C12, C13, C7, D3 and D5 can all be verified offline as planned. C12's "second tap says Already cancelled" works, because `db.get_reminder` only returns active rows.

### 2. Gmail and Calendar facts

- **SENT on the last message: correct, with one gap the plan leaves out.** A thread from `threads.get` includes draft messages, which carry the `DRAFT` label. ClaudeBot creates those itself: `create_draft` with a `threadId`, and from now on C13 drafts-only mode on every "send". If the owner saves a reply as a draft, the last message is the owner's own draft, so a waiting thread moves to "owed" with the owner listed as the person waiting. Rule: ignore `DRAFT` messages when picking the last message. `replies.py`/`thread_states` already does this. Add it to the plan and give it a test.
- **Age from `internalDate`, not the `Date` header.** The plan says "date". The discovery doc says `internalDate` "is more reliable than the Date header", and the sender writes the Date header. The code already uses `internalDate`. Write that into the plan.
- **`threads.get` with `format=metadata`: correct.** The method takes `format` (`full`, `metadata` or `minimal`) and `metadataHeaders`. Message `labelIds` and headers are documented as returned. The doc doesn't list `snippet` and `internalDate` for metadata format, but they are returned in practice, and `search_emails` already relies on `snippet` from `messages.get(format="metadata")`. The saved fixture from §1 settles this.
- **All-day events and transparency: wrong.**
  - The discovery doc says `transparency` defaults to `"opaque"`, which means Busy. In practice the field is only present when it is `"transparent"`.
  - The Calendar UI saves new all-day events as "Available", which is `transparent`.
  - So "all-day events don't block unless marked busy" can't be implemented as written. A Busy all-day event (for example a vacation day) comes back with no field, and `scheduling.py:28` (`if all_day and transparency != "opaque": continue`) treats it as free.
  - Use one rule for all events: `transparent` means free, anything else is busy. This matches Google's own free/busy.
  - ClaudeBot's own `create_event` sends no transparency for all-day events, so the API stores them as Busy. Set `"transparency": "transparent"` for date-only events in `create_event`, as the UI does. Otherwise a "Paper due Friday" all-day event blocks the whole day.
  - Keep ignoring all-day events when looking for conflicts. That is a noise rule, and it is fine.
- **Declined invites are missing from both rules.** `events.list` returns events the owner declined. Their `attendees[]` entry with `self: true` has `responseStatus: "declined"`. `list_events` keeps only attendee emails, so a declined meeting counts as busy in find_free_time and shows up as a heartbeat clash. Anyone who gets invites hits this. Fix: add `"declined": bool` to `list_events` output, and skip declined events in `busy_from_events` and in conflict detection.
- **Paging with `pageToken`: mostly correct.** `nextPageToken` is absent on the last page, where `nextSyncToken` appears instead. Pages can be short or empty. Every page request must repeat the same query parameters. The page size can be up to 2500 (default 250), so the per-page clamp of 100 is fine but not required. What the plan gets wrong is D2's real defect, *silent* truncation. Paging to 250 moves the limit but keeps it silent, and `find_free_time` allows 31-day windows, where 250 events is reachable for a busy calendar. Ordered by start time, the cut drops the end of the window, and free time gets proposed over meetings that were cut off. Fix: when the listing reaches the cap, return `truncated: true` from `list_calendar_events`, and limit find_free_time's search to the last event it received.

### 3. Security against the model in BRIEF.md

- **Untrusted text becomes bot-voiced prose (the real hole).** C1's Haiku call writes `{notify, message}` from signals that include email subjects, sender names and calendar event titles. Anyone can put a title on the owner's calendar by sending an invite. Up to 600 characters of free text then go to the owner as ClaudeBot speaking. Defanging and the length cap don't stop "Your Google sign-in expired, reply with…". Inbox alerts are safer: code shows the sender address, and the model's line is clipped to 200 characters. Fix with less code: render the heartbeat message from the signal lines code already builds (`Signal.text` is clipped). Either drop the compose call, or let Haiku return only `notify` and the signal keys to include, never text. The judgement C1 needs is already made by C2's reply filter and the code-found calendar signals. Swipe-replies to bot messages are already fenced as data (`ui.reply_context`), so that path is fine.
- **The reply-judge fallback feeds the heartbeat.** When Haiku fails, `find_reply_gaps` returns unfiltered lists, which may be notifications from senders not on the noreply list. `run_heartbeat` pings them and marks them seen. Rule: the heartbeat uses only items Haiku judged; the fallback is for `/waiting`, which the owner asked for.
- **Fencing: correct as planned.** The C2 judge sends clipped subjects and snippets inside a tag, the system prompt calls them untrusted data, and invented ids are ignored (`verdicts.get(g.thread_id, False)`). Nudge and Reply send only a message id, and Claude reads the email itself with `read_email`. This mirrors `mail:draft`. Small point: `json.dumps` inside `<threads>` doesn't escape `<` or `>`. `fence_external` does, and it already exists. The same applies to inbox_watch, so this is not new.
- **Unattended actions: none added.** The heartbeat has no tools, and its only button (`chk:waiting`) is a fixed view. Nudge and Reply are owner taps into owner-present turns, so sends keep the Undo window. Drafts-only in an unattended turn creates a draft, which `create_draft` can already do. D3 is right to gate `update_calendar_event`, `delete_calendar_event`, `forget` and `cancel_reminder`.
  - D3 overreaches on one tool: it gates *all* of `modify_email` (`_require_owner(ctx, "change emails")`). Archive, star and mark-read are reversible, nobody else sees them, and a task the owner scheduled ("every evening, archive LinkedIn mail") needs them. Gate only `trash`, which is what the triage said and what the test checks.
  - Gating `cancel_reminder` means a repeating task can't cancel itself. That's acceptable now that `/reminders` gives one-tap cancel.
- **Callback data: all inside 64 bytes.** `rt:nudge:` plus a Gmail id of at most 32 hex characters is 41 bytes at most. `unrem:<int>` and `chk:waiting` are tiny. The handler patterns re-check the id format (`^rt:(nudge|reply):[0-9a-f]{6,32}$`). The planned "calendar view" button was rightly left out of the code. Drop it from the plan too.

### 4. Heartbeat noise and duplication

Yes, as specified it will be noisy, for these reasons:
- The cap of 3 a day equals the triage's *failure* threshold ("median ≤3/day"), so the cap is reached rather than kept under.
- Owed threads cross the 2-day mark every day for anyone with personal mail. Most of them were already sent as inbox alerts, so each one is pushed twice: as an alert, then as a nudge.
- Clashes in today's calendar repeat what the morning brief listed.
- The key `conflict:<idA>:<idB>` depends on the order the events come back in. Two meetings at the same time, the most common clash, come back in an order the API doesn't promise to keep, so the same clash can be pinged twice. Sort the two ids in the key.

Separately, the D1 notice will be noisy. `checkins._inbox_job` counts the quiet-hours `check()` (which returns `[]` without calling Google) as a success, so a broken token gives "paused" by day and "working again" at 23:00, every day. Its counter lives in memory, so every restart re-arms it. It also counts `GoogleNotConnected`, so an owner who tapped "Later" on Google gets "Inbox alerts are paused" about 30 minutes after setup, and again after each `/settings` change. Fixes:
- Count a check as a success only when it actually reached Gmail.
- Keep the "notice sent" flag in the settings table.
- Don't count `GoogleNotConnected`: that is setup not done, not something broken, and `/status` already shows it.

**The single rule that would cut the most noise: ping only for what can't wait until the next daily brief.**
- Calendar clashes and early starts that come before the next brief get pinged.
- Reply items (owed and waiting) never trigger a ping on their own. They are added to a ping that is going out anyway, and otherwise wait in `/waiting`.

This also stops the alert-then-nudge double push. With the brief turned off, treat the end of quiet hours as "the next brief".

### 5. Build first

**D3, with `modify_email` narrowed to `trash`.** It is the only finding that is a live hole in the shipped 1.0: the daily brief runs unattended, reads untrusted email, and can trash mail and delete events today. It takes about 15 minutes, and its tests already exist. After that, `thread_states`, because C2 and C1 both stand on it and it carries the most API-fact risk.

### Changes to the plan

1. C6: "`transparent` = free, everything else busy, all-day included". `create_event` sets `transparent` on date-only events. Skip declined events in free time and in clashes. Fix the test that uses an explicit `"opaque"`.
2. D2: return `truncated: true` when the cap is hit, and limit find_free_time to the events it received. Add a fake page that is short but has a token. Assert results, not call count.
3. C2: write down the rules the code already follows (ignore drafts, age from `internalDate`, cache verdicts per message id), and add a test fixture with a draft in the thread.
4. C1: render the message from code-built lines (Haiku returns at most notify and keys). Use judged items only, never the fallback. Sort ids in conflict keys. Adopt the "can't wait for the next brief" rule. Drop the calendar-view button.
5. D1: a check counts as a success only if it reached Gmail. Store the notice flag in the database. Don't count `GoogleNotConnected`. Add a restart test and a quiet-hours test.
6. D3: gate `trash` only, not every `modify_email` action.
7. Acceptance: say that C1 and C2 quality are judged by the triage's 14-day dogfood numbers, not by the offline tests.

What is correct and should stay as it is: C12 (deterministic, no model call, owner check, "Already cancelled"), C13 (the tool result says "not sent"), C7 as copy only, D5, the 25-thread cap, the `heartbeat`/`replies` usage sources, the per-day count and seen keys kept in the database, quiet hours and the off switch.
