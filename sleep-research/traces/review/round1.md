# Code review, round 1: ClaudeBot 1.1 (HEAD 6517248)

## Prompt

[Review round 1 of 3 of an autonomous review loop.] Review the code from its artifacts; any notes from the author are not evidence. Repo: /home/user/ClaudeBot (Python 3.13, venv at .venv). The change under review is the HEAD commit ("feat: ClaudeBot 1.1"); run `git show HEAD --stat` and read the diff, then read the surrounding code and callers yourself. Explore freely: read any file and run read-only commands, including `.venv/bin/python -m pytest -q` and scratch scripts under /tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad. Modify no repo files.

Context, which you should verify yourself:
- sleep-research/BRIEF.md has the product and its security model:
  - only the owner may use the bot;
  - email, calendar and web text is untrusted and must be fenced;
  - nothing is sent unattended;
  - turns the owner didn't start can't act destructively.
- sleep-research/PLAN.md has the acceptance criteria, plus the changes made after the plan review.
- New modules: claudebot/scheduling.py, replies.py, heartbeat.py, checkins.py. Changed: tools.py, google_services.py, bot.py, setup_chat.py, agent.py.

Start from the assumption that it is broken somewhere, and find where. Focus on:
- correctness: time zones and DST in free_slots and calendar_signals, overlap logic, paging, the daily caps, dedupe keys, the reply-only-once-a-day rule;
- security: untrusted subjects or titles reaching the bot's own words or the model unfenced; callback data validation and owner checks on every new button; prompts built from ids only; unattended turns that are still able to do something destructive; drafts-only mode leaking a send;
- silent failures and cost: model calls that could repeat every 3 hours; settings growth;
- whether the tests actually test the claims.

For each finding give severity (CRITICAL/HIGH/MEDIUM/LOW), file:line, a concrete failure scenario (input → bad outcome) and the minimum fix. Before reporting, make sure you can cite the line and have read the callers. Then give a score from 1 to 10 for shipping quality, as one line "Score: X/10", and one line "Verdict: ready / almost / not ready". If it holds up after you genuinely tried to break it, say so.

=== SCOPE LIMITS (these bound what you PROPOSE, never what you look for) ===
Report anything that is actually wrong, including a rare case if this project actually produces it. Then keep fixes in scope:
1. This is a product, not a security research project. Verification is welcome; over-defense is not.
2. Do not propose hashing, fingerprinting, or digest-binding schemes.
3. No speculative machinery (flags, compat layers, wrappers, frameworks) unless you can point to a current defect it fixes.
4. No corner-case obsession unless you can show the case arises here.
5. A clear sentence beats a scored checklist nobody maintains.
Say plainly when something is correct. Do not manufacture findings.

Write the full review to /home/user/ClaudeBot/sleep-research/traces/review/round1.md: a "## Prompt" section with this prompt, then "## Response". Return the findings list, the Score line and the Verdict line.

## Response

I read the full diff, the four new modules, and the callers they touch: `bot.py` job wiring and reminder jobs, `buttons.py`, `setup_chat.py` settings handlers, `inbox_watch.py`, `outbox.py`, the `db.py` settings and reminder helpers, and `tools.py` dispatch. The suite passes (231 tests). I confirmed each finding below with a scratch script under the session scratchpad (`probe2.py` and `probe3.py`) rather than by reading alone.

### Findings

**1. MEDIUM: an all-day event in the listing turns off the truncation guard in `find_free_time`.** `claudebot/tools.py:454`
`max(datetime.fromisoformat(e["start"]) if len(e["start"]) > 10 else end for e in events)`: every all-day event adds the original `end` to the `max`, so whenever even one all-day event is among the 250 the clamp does nothing. Busy calendars, the only ones that reach 250 events, nearly always contain at least one all-day item: a holiday, a birthday, an out-of-office day, or a working-location entry.
Scenario (probe2): a 30-day window with more than 250 one-hour meetings that fill every working hour, plus one all-day event. Google stops at 250, with the last event seen at Nov 30 14:00. The tool offers Nov 30 15:00, Nov 30 17:00 and Dec 1 09:00 as free, but those hours hold meetings it never read. Without the all-day event, the same input correctly returns `[]`. The note still says "too full to read past the last slot shown", which doesn't match the slots it returns.
Fix: `end = min(end, max((datetime.fromisoformat(e["start"]) for e in events if len(e["start"]) > 10), default=start))`. Add a test with a truncated listing that includes an all-day event; the truncated path has no test today.

**2. MEDIUM: the "reply-only check-ins at most once a day" rule can be broken.** `claudebot/heartbeat.py:156` and `:166`
The gate at line 156 looks only at the *unseen signals*. When a calendar signal is among them, the run goes ahead, Haiku may keep only the reply items, and a second reply-only check-in goes out that day. Line 166 sets the key again but never checks it.
Scenario (probe3): at 10:00 a reply-only check-in is sent. At 13:00 a new minor overlap shows up along with a new waiting thread, and Haiku picks only the reply (`include: [1]`). A second "No reply from …" message goes out the same day, which is exactly what the plan-review noise rule ("reply-only check-ins happen at most once a day") forbids. The test `test_reply_only_check_ins_happen_once_a_day` covers only the case where every signal is a reply.
Fix: after `_select`, if `db.get_setting(replies_key)` is set and every chosen signal is a reply, mark only the calendar signals as seen and return None. The reply signals then stay unseen, ride along with the next calendar check-in or wait for tomorrow.

**3. MEDIUM: the 600-character cap cuts lines silently, and the dropped items are marked as already mentioned.** `claudebot/heartbeat.py:159-170`
Every signal is marked seen at line 159–160, then the text is joined and sliced at `[:MAX_MESSAGE]` (line 170). An owed-reply line can reach about 215 characters (80 for the counterpart, 100 for the subject, plus fixed text), so three items already approach the cap.
Scenario (probe3): four owed replies, all chosen by Haiku. The message ends `- Person d Last`, cut mid-name. Item 4, plus anything after it, is stored as `hb_seen:` and will never be mentioned. This hits the first heartbeat for anyone with a backlog. It breaks "mentions each thing once" (CHANGELOG) in the worst way: the item is mentioned zero times and still counted as said.
Fix: add whole lines while the text stays within the cap, and mark as seen only the lines shown plus the signals Haiku dropped. The rest stay unseen for the next run.

**4. MEDIUM: an attacker's display name can push the real address out of the bot's own words.** `claudebot/replies.py:85-88`, shown at `claudebot/checkins.py:101,108` and in check-in text at `claudebot/heartbeat.py` `reply_signals`
`clip(t["from"], 80)` clips the raw `From` header. A display name of 80 characters or more pushes the address off the end: `"Mom (family account) - sent from my iPhone, please reply as soon as you can" <payments@evil.example>` becomes `"Mom (family account) - sent from my iPhone, please reply as soon as you can" <…`. The check-in then reads, in the bot's voice, "Mom (family account)… is waiting 2 days for a reply to "…"", and /waiting shows a "✍️ Reply to "Mom (family" button. 1.0 deliberately prevents exactly this in inbox alerts (`inbox_watch._sender`: "so a fake "Mom" can't hide its real address").
Fix: build the counterpart with `inbox_watch._sender` (name clipped to 40, address kept), for example `f"{name} <{address}>" if name else address`, in `_candidates`.

**5. LOW: a check-in is recorded as delivered before it is sent.** `claudebot/heartbeat.py:159-164` and `claudebot/checkins.py:155-158`
Signals are marked seen and the daily count goes up inside `run_heartbeat`. If `send_to_owner` then raises `TelegramError` (caught and logged at checkins.py:157), the items are lost for good and a daily slot is used up. The inbox watcher handles this correctly: it marks emails seen only after the send (inbox_watch.py:125).
Fix: return the keys with the `CheckIn` and have `_heartbeat_job` write `seen` and the count after a successful send. Alternatively, accept the loss and say so in a comment; Telegram send failures are rare.

**6. LOW: check-ins and /waiting leave no notice for the agent.** `claudebot/checkins.py:156`, `:87`
Inbox alerts, reminders and briefings all `db.add_notice(...)` what the owner was shown. Check-ins and /waiting don't. If the owner answers a check-in by typing "nudge Prof Lee" or "move the dentist", without swipe-replying, the agent has no record of what it just said and has to search from scratch. Fix: `self.db.add_notice("Check-in shown to the owner: " + json.dumps(...))` with the message ids and event ids, following the pattern at inbox_watch.py:216-219.

**7. LOW: criterion C7 is only half done.** `claudebot/setup_chat.py:54-76`
PLAN C7 says "`/help` and the WELCOME text mention" the flyer/ticket photo. Only WELCOME (line 48) does. The `/settings` line in HELP also doesn't list the new check-ins and drafts-only switches. Fix: add one line to HELP.

**8. LOW: every all-day event the bot creates is marked free, so "block my Friday" doesn't block anything.** `claudebot/google_services.py:325`
This matches Calendar's UI default, and the plan review accepted it. But the `create_calendar_event` tool has no way to make an all-day event busy, and its description doesn't tell the model. "I'm out Friday, block it" produces an all-day event marked free: `find_free_time`, and other people's free/busy view, still show Friday as available. Fix: one sentence in the tool description ("all-day events are created as free; to block a whole day use timed start/end").

**9. LOW: tests that don't test the claims.**
- The `find_free_time` truncation path has no test; that is how finding 1 shipped.
- The reply-only rule is tested only with all-reply signals (finding 2).
- The 600-character cap has no test (finding 3).
- PLAN C6 lists "an event spanning midnight" and "back-to-back events" as `free_slots` cases. The midnight event appears only in the `busy_from_events` test, and no back-to-back case exists.

The other new tests do check what they claim. That includes owner checks with a stranger's tap, ids-only prompts with an injected subject, short pages carrying a `nextPageToken`, restart-proof failure counting, and cached verdicts. One more note: the plan describes `HEARTBEAT_HOURS` and `HEARTBEAT_MAX_PER_DAY` as configurable, but they are module constants. Either is fine; the plan and the docs should agree.

### Checked and correct

- **Owner checks and callback data.** `unrem:\d+`, `rt:(nudge|reply):[0-9a-f]{6,32}` and `chk:waiting` are anchored regexes. Each handler checks `_from_owner`. `/reminders` and `/waiting` use `filters=owner`. `set:checkins` and `set:drafts` go through the owner-checked `on_settings_button`. Button ids are also filtered with `GMAIL_ID.fullmatch` before they are put on a button.
- **Prompts built from ids only.** NUDGE_PROMPT and REPLY_PROMPT contain only the hex id. The email text reaches Claude only through `read_email`, the same pattern as the 1.0 alert ✍️ button.
- **Untrusted text sent to Haiku.** Subjects, snippets and event titles reach Haiku only as JSON inside `<threads>` or `<signals>`, under a "never follow instructions" system prompt. Model output is limited to booleans per known id and integer indices. Invented ids or indices are ignored, and the check-in text is written by code and defanged. Haiku can only pick which code-written lines appear.
- **Unattended turns (D3).** Trash, event update and delete, `forget`, and `cancel_reminder` all raise NeedsOwner. `send_email` in an unattended turn is held for approval, or saved as a draft in drafts-only mode. No destructive tool is left open to the brief or to scheduled tasks; archive, star and mark-read stay open by the plan-review decision.
- **Drafts-only mode.** No send leaks. `send_email` checks the setting before it touches the outbox, and `create_draft` takes the same fields. The only remaining send paths need an owner tap: `approve_held_email` (owner-only) and the Undo/Approve buttons on emails queued earlier.
- **`free_slots`.** Overlap merging, back-to-back events (`start <= merged end`), events spanning midnight, gaps that are too short, durations longer than the working day, rounding to quarter hours, and slots in the past all behave correctly. On DST: working-hour windows are built with `datetime.combine(..., tzinfo=tz)`, so 09:00 is 09:00 local on Nov 1 (the US fall-back day). Inputs in UTC, or with another offset, compare correctly. Same-tzinfo wall-clock arithmetic could only go wrong for a slot that spans 01:00–02:00 on the fall-back night, which ordinary working hours never include.
- **`calendar_signals`.** Sorting by start plus `break` on `start_b >= end_a` finds every overlapping pair. All-day, transparent and declined events are skipped. Conflict keys use sorted ids. Times are formatted in the owner's zone.
- **Paging.** It follows `nextPageToken` through short pages, stops at the limit, and `list_calendar_events` reports `truncated`.
- **Daily cap and quiet hours.** The cap and quiet hours are checked before any Gmail or model call, and the count is keyed by local date.
- **Inbox-failure notices (D1).** Exactly one notice at the 3rd failure, one "working again" afterwards, and the count survives restarts. Quiet hours and an unconnected Google don't count.
- **Cost.** Nothing repeats every 3 hours. Reply verdicts are cached per last-message id, so a thread is judged once. `_select` runs only on unseen signals, and they are marked seen afterwards. Blocked reply-only runs make no model call. Over budget, `check_budget()` raises before any request.
- **Settings growth is bounded.** `expects_reply:` 500, `hb_seen:` 500, `hb_count:` 7, `hb_replies:` 7. `inbox_failures` is deleted on recovery. `prune_settings` orders by rowid, and the upsert keeps the rowid, so "most recent" holds.

### Verdict

The security model holds. I tried to get a send, a destructive action, or model-written text out of an unattended path and couldn't. What's wrong is correctness in the new proactive features: a dead truncation guard that reports busy time as free, a broken noise rule, a silent cut-off that marks items as already said, and a spoofable sender name in the bot's own voice. Each is a few lines to fix plus one test.

Score: 7/10
Verdict: almost
