# Claims audit, round 2

## Prompt

Claims audit. Judge whether a product's public claims are backed by its code. You did not write any of it. Repo: /home/user/ClaudeBot (venv at .venv). Modify no repo files; scratch work goes in /tmp/claude-0/-home-user-ClaudeBot/5053fdda-36be-5727-b535-882cc1a31bbc/scratchpad.

Claims to audit:
- the "## 1.2.0" section of CHANGELOG.md, every bullet;
- the README sections on features, Telegram DMs, Commands, and Safety notes;
- the /help text (HELP) and WELCOME in claudebot/setup_chat.py;
- the landing page docs/index.html, especially the "New in 1.2" section and the safety rules.

For each claim:
1. Find the code that implements it (file:line) and a test that proves it (tests/...::name).
2. Rule it: supported yes / partial / no.
3. Numbers must match constants. Examples: 20:30 habits, 21:30 journal, 03:00 backup with 7 kept, 2-day /quiet cap, 3 check-ins a day, 4 meeting preps a day, 250 events, 30-75 minutes, Saturday 10:00 digest, Sunday 18:00 review, 120 days, 15-minute meeting-prep job.
4. Pay special attention to:
   - safety claims about what turns the owner didn't start can do;
   - "never sent on its own";
   - "drafting never sends";
   - "nothing is deleted";
   - "no AI cost";
   - "only you";
   - "summed exactly";
   - "Docker health check";
   - "Replies from your Telegram account need your tap".
5. Check that every command named in docs exists in claudebot/bot.py, and that every registered command is mentioned in /help.

Run `.venv/bin/python -m pytest -q` once and quote the summary line. Label anything only provable in production as "unverifiable offline", e.g. "Business Mode setup steps", "a few dollars a month", "Premium not required". Report what is actually wrong; don't invent problems.

Write the audit to /home/user/ClaudeBot/sleep-research/traces/claims/round2.md: a "## Prompt" section with this prompt, then "## Response". Return a table of the claims judged "no" or "partial", each with a suggested rewording or fix.

## Response

### Which code this audit covers

The repository changed while the audit ran. New commits landed every minute or two (another session was committing). To keep file:line references stable, the audit is pinned to **commit 4a3eaf1**, a `git archive` snapshot in the scratchpad (`scratchpad/snap`). All file:line references below are to that commit.

- When the audit started, HEAD was d4381d4. Then 099a149, 9f05d7f (email snooze) and 4a3eaf1 ("what's new" message) landed.
- By the time the audit was written, HEAD was **87c0d3e**: six more commits (restore from /export, /menu, "batch 4 review findings", /bills, /subscriptions). Those are **not** audited here.
- At 87c0d3e I re-read the code for the findings below. All are still present except the journal reply window, which d455207 fixed (see row 9 of the final table). That re-read was by eye only, with no test run.

No repo file was modified apart from this one.

### Test run

`.venv/bin/python -m pytest -q`, run once:

```
330 passed in 18.74s
```

From the collection counts, that run was against commit **099a149**: `pytest --collect-only` gives 329 tests at d4381d4, 330 at 099a149, 331 at 9f05d7f and 332 at 4a3eaf1. So the two tests added after it were collected but not run by me: `tests/test_triage.py::test_snoozed_email_comes_back` and `tests/test_shortcuts.py::test_whats_new_once_per_version_and_not_on_fresh_installs`.

Scratch checks were run from the scratchpad only, never added to the repo. They are cited as "scratch":

- `scratchpad/cmd_check.py` cross-checks commands.
- `scratchpad/checks/behaviour_checks.py` checks job schedules, /quiet against the brief, meeting prep in quiet hours, the Undo window at 0, the journal reply window, /privacy targets and the snooze time.

### How to read the rulings

- **yes**: code backs the claim and a repo test exercises its substance.
- **partial**: the claim says more than the code does, or a load-bearing part of it (a number, a time, a safety guarantee) has no repo test. Each partial says which.
- **no**: the code contradicts the claim, or nothing implements it.
- **unverifiable offline**: depends on Telegram, Google, Fly, Railway, Anthropic billing or model behaviour.

### Constants against the copy

| Claim in copy | Constant | Matches | Test that pins it |
|---|---|---|---|
| Habits asked at 20:30 | `CHECK_TIME = time(20, 30)` habits.py:12, scheduled bot.py:422 | yes | none for the schedule (scratch: `habits 20:30` daily) |
| Journal at 21:30 | `ASK_TIME = time(21, 30)` journal.py:13, bot.py:420 | yes | none for the schedule (scratch) |
| Backup 03:00, 7 kept | `BACKUP_TIME = time(3, 0)`, `KEEP = 7` backup.py:10-11, bot.py:418 | yes | 7 kept: test_export.py::test_nightly_backup_is_a_consistent_copy_and_rotates; 03:00: none (scratch) |
| /quiet capped at 2 days | `MAX_PAUSE = timedelta(days=2)` quiet.py:14 | yes | test_quiet.py::test_parse_pause ("99 days" -> 2 days) |
| 3 check-ins a day | `MAX_PER_DAY = 3` heartbeat.py:32 | yes | test_release_11.py::test_heartbeat_respects_quiet_hours_the_daily_cap_and_the_off_switch |
| 4 meeting preps a day | `MAX_PER_DAY = 4` meeting_prep.py:27 | yes | test_meeting_prep.py::test_prep_is_capped_and_can_be_turned_off |
| 250 events (1.1 copy) | `MAX_EVENTS = 250` google_services.py:26 | yes | test_release_11.py::test_list_events_pages_up_to_the_limit |
| 30-75 minutes before a meeting ("about an hour") | `EARLIEST`/`LATEST` meeting_prep.py:24-25 | yes | test_meeting_prep.py::test_only_upcoming_meetings_with_other_people (60 min in, 10 min and 4 h out; no boundary test) |
| 15-minute meeting-prep job | `JOB_MINUTES = 15` meeting_prep.py:26, bot.py:432 | yes | none (scratch: `meeting-prep: 900`) |
| Saturday 10:00 digest | `DIGEST_TIME = time(10)`, `DIGEST_DAYS = (6,)` review.py:31-32 | yes: python-telegram-bot 22.8 counts 0-6 from Sunday, so 6 is Saturday | none for the schedule (scratch) |
| Sunday 18:00 review | `REVIEW_TIME = time(18)`, `REVIEW_DAYS = (0,)` review.py:16-17 | yes | test_review.py::test_review_is_scheduled_for_sunday_evening |
| 120-day window for alert due dates | `MAX_DUE_AHEAD = timedelta(days=120)` inbox_watch.py:29 | yes (the copy says "the morning before"; 120 days isn't in the copy) | test_life_admin.py::test_due_dates_must_be_real_and_soon |
| Undo 20 s; inbox checked every 10 min | config.py:44,47,94,97 | yes | test_features.py::test_outbox_queues_then_sends_after_delay; test_release_11.py::test_background_jobs_run_on_the_advertised_schedule |
| Follow up "three days later" | `NO_REPLY_DAYS = 3` checkins.py:29 (09:00 on day 3) | yes | test_reminder_extras.py::test_follow_up_if_no_reply (doesn't check the date) |
| DMs kept 7 days; 24-hour reply window; check-ins after 2+ hours | business.py:35-37 | yes | test_business.py::test_old_messages_are_pruned_and_deletions_honored, ::test_cancel_and_expired_window, ::test_dm_signals_for_check_ins_wait_two_hours |
| /log covers 60 days (/export) | `RETENTION = timedelta(days=60)` actions.py:9 | yes | test_actions.py::test_log_keeps_what_happened_in_order_and_prunes |
| Health: touched every minute | alive job `interval=60` bot.py:438; `HEALTH_MAX_AGE = 300` \_\_main\_\_.py:41 | yes | test_shortcuts.py::test_health_check_follows_the_alive_file |

Every number in the copy matches its constant. The gap is coverage: of the daily jobs, only the Sunday review's time is asserted by a repo test.

### Commands (point 5)

From `scratchpad/cmd_check.py`, run on 4a3eaf1:

- **Registered** in bot.py: brief, briefings, catchup, connect, disable, dms, enable, export, focus, followups, habit, habits, help, journal, lists, log, memory, mode, new, note, owed, privacy, quiet, reminders, research, role, rules, settings, setup, spent, start, status, style, sweep, think, today, triage, trips, usage, waiting.
- **Every command named in the docs exists.** That holds for the CHANGELOG 1.2.0 section, docs/index.html, HELP, WELCOME and the whatsnew notes. The README's only unregistered "/" words are `/data`, `/docs` (paths) and `/newbot` (a BotFather command).
- **Registered but not in /help:** `/start` (fine; Telegram sends it) and `/habits`, an alias of `/habit`. tests/test_release_11.py::test_help_mentions_every_private_command explicitly excludes both.
- **Missing from the README:** `/owed`, a 1.2 feature that HELP and the CHANGELOG list, appears nowhere in the README. `/habits` is also absent.

### Safety: what turns the owner didn't start can do

All of these turns pass `owner_present=False`:

- daily brief: bot.py:951
- scheduled tasks: bot.py:882
- weekly review: review.py:51
- newsletter digest: review.py:61
- meeting prep: meeting_prep.py:77
- draft buttons: the alert ✍️ / 📅 Times / 📅 add buttons (buttons.py:91, 100, 134), /waiting Nudge and Reply (checkins.py:264), /triage Reply (triage.py:111) and /dms Reply (business.py:314)

With `owner_present=False`, `_require_owner` (tools.py:69-72) refuses these tools:

- archive, trash or mark email: tools.py:642
- invites: tools.py:655
- changing or deleting events: tools.py:673, 677
- deep research: tools.py:681
- saving or deleting memories: tools.py:689, 694
- the workbench: tools.py:698
- briefings: tools.py:716
- reminders and tasks: tools.py:737
- lists, expenses and IOUs: tools.py:755, 759, 763
- alert rules: tools.py:766
- cancelling reminders: tools.py:781
- releasing a held email: tools.py:635

`send_email` turns into a held email that needs ✅ Send (tools.py:633, outbox.py:62-69). Telegram replies can only be proposed: `reply_telegram_dm` just queues a card (tools.py:590-597). The only code that sends from the owner's account is the `dmsend` button (business.py:302-377).

I checked every button handler: all 26 verify the owner (`_from_owner` or `owner_id`).

Tests:

- test_release_11.py::test_destructive_tools_need_the_owner
- test_release_11.py::test_unattended_turns_cant_change_email_or_plant_reminders
- test_features.py::test_unattended_turns_cannot_invite_save_memories_or_plan_tasks
- test_features.py::test_unattended_turn_holds_email_for_a_send_tap
- test_features.py::test_owner_can_release_a_held_email_by_saying_so
- test_review.py::test_weekly_review_runs_unattended_and_can_be_turned_off
- test_meeting_prep.py::test_prep_job_briefs_once_per_meeting_with_ids_only
- test_life_admin.py (Times and 📅 add buttons assert `owner_present is False`)
- test_triage.py::test_triage_cards_and_actions
- test_business.py::test_dms_view_and_draft_button
- test_business.py::test_send_as_me_needs_the_owners_tap_and_works_once
- test_lists.py::test_list_tools
- test_expenses.py::test_expense_tools
- test_ious.py::test_iou_tools_and_command
- test_alert_rules.py::test_rule_tool_needs_the_owner

The one gap: no test asserts that the **daily brief** and **scheduled-task** jobs themselves pass `owner_present=False`. test_review.py::test_brief_has_feedback_buttons_and_feedback_becomes_a_memory records the flag but never checks it. The code is right; the wiring is what's untested.

---

### 1. CHANGELOG.md, "## 1.2.0" (line numbers at 4a3eaf1)

| Line | Claim | Code | Test | Ruling |
|---|---|---|---|---|
| 6 | Turns you didn't start can't set reminders or archive, trash or mark email; an email read while you're away can't plant a reminder | see the safety section | see the safety section | **partial** (claim true; brief and task wiring untested) |
| 7 | Brief feedback and journal entries only count as a reply to the question | setup_chat.py `_expect(reply_to=)` / `_answers_question`; review.py:80; journal.py:75 | test_review.py::test_brief_has_feedback_buttons_and_feedback_becomes_a_memory; test_journal.py::test_evening_prompt_and_answer | yes |
| 8 | `/sweep` never touches starred or important mail | sweep.py:16-20 (`-is:starred -is:important` in every query) | none: the fake in test_sweep.py ignores the query | **partial** (untested) |
| 11 | Nightly backup at 03:00 into `data/backups/`, last 7 kept, safe while running | backup.py:10-23 (SQLite online backup API, chmod 600); bot.py:418 | test_export.py::test_nightly_backup_is_a_consistent_copy_and_rotates | **partial** (03:00 untested; correct by scratch) |
| 12 | Docker health check: a file touched every minute, `python -m claudebot health` checks it, "so Docker (and Fly/Railway) can see a stuck bot" | bot.py:438, 963-966; \_\_main\_\_.py:40-64; Dockerfile:16 | test_shortcuts.py::test_health_check_follows_the_alive_file | **partial**: the Docker part is yes. Fly and Railway don't run a Dockerfile `HEALTHCHECK`, and fly.toml has no `[checks]`; nothing in the repo makes Fly or Railway watch the file. The platforms' behaviour is unverifiable offline, but the repo config supports Docker only. |
| 15 | `/catchup`: what you missed "since you last asked"; `/trips` with anything missing | shortcuts.py:44 (the window is clamped to 1-72 h, 12 h the first time); prompts shortcuts.py:13-22 | test_shortcuts.py::test_catchup_covers_the_time_since_last_time | **partial**: after more than 3 days away it covers 72 h only. The /trips gap-spotting is model behaviour (unverifiable offline). |
| 16 | `/status` shows check-ins sent and tapped this week | setup_chat.py:579-580; checkins.py:271, 311 | test_shortcuts.py::test_counters_sum_the_last_days (counters only) | **partial** (the /status line is untested; "this week" is the last 7 days) |
| 17 | `/today`: calendar, reminders due, Telegram chats waiting, open list items; no AI call | today.py:37-69 | test_today.py::test_today_shows_calendar_reminders_and_lists_without_a_model_call (the DM line isn't checked) | yes |
| 20 | `/usage` by feature | usage.py:20-26, 109-127; every `tracker.record` passes a source | test_today.py::test_usage_breaks_spend_down_by_feature | yes |
| 23 | 💤 snooze archives and brings the email back unread "at 8:00 tomorrow", with a ping | triage.py:82-92; snooze.py:40-50; google_services `"inbox"` adds INBOX+UNREAD; job every 5 min bot.py:439 | test_triage.py::test_snoozed_email_comes_back (added after my run; not run) | **partial**: a tap between 00:00 and 04:00 returns at 08:00 the *same* day (scratch: tapped 02:00 -> 08:00 that morning), which is sensible but isn't "tomorrow". |
| 24 | `/triage` one card at a time; Reply is a draft you check; listing and archiving use no AI | triage.py:44-111 (plain Gmail calls; Reply runs `owner_present=False`) | test_triage.py::test_triage_cards_and_actions | yes |
| 25 | Optional Saturday newsletter digest: the 5 things worth knowing, "then `/sweep` clears them out" | review.py:30-38, 57-64; bot.py:424 | test_review.py::test_newsletter_digest_is_opt_in (opt-in, unattended; not the schedule) | **partial**: Saturday 10:00 is untested (correct by scratch). /sweep only archives Promotions/Social older than 3 days and Updates older than 7 days (sweep.py:18-20). The digest also reads `list:*` mail, which can sit in Primary, and this week's Updates aren't swept for another week. |
| 26 | `/sweep` archives a category in one tap; out of the inbox but still in All Mail, nothing is deleted; no AI | google_services.py:138-142 (`removeLabelIds: ["INBOX"]` only); sweep.py | test_sweep.py::test_message_ids_and_archive_many, ::test_sweep_counts_then_archives_on_tap | yes |
| 29 | Repeating events, including "every weekday until Dec 19" | scheduling `rrule`; tools.py create_calendar_event | test_release_11.py::test_recurrence_rules_are_built_from_known_tokens, ::test_repeating_events_reach_google | yes |
| 30 | Every event ClaudeBot adds gets a ↩️ Remove card, including from tasks and the 📅 button | tools.py `event_created` after create_event; checkins.py `event_created`, `on_event_undo` | test_reminder_extras.py::test_added_events_get_a_remove_card (unattended) | yes |
| 33 | "Every sent email's confirmation" has ⏰ Follow up if no reply; 3 days later it checks; the nudge is drafted for you to send | outbox.py:135 (button added only when a queued email is delivered); checkins.py:128-158 (task at 09:00 on day 3; it runs as an unattended task, so any send is held) | test_reminder_extras.py::test_follow_up_if_no_reply | **partial**: with the Undo window at 0 ("Instant" in /settings, UNDO_SEND_SECONDS=0), outbox.py:70-74 sends straight away with a plain "📤 Sent" notice and no button (scratch). Held emails released by ✅ Send do get it. |
| 36 | `/privacy` shows what's kept "(conversation history, DMs, journal, action log, memories) and clears any of them" after a confirmation | privacy.py:10-15 (clearable: chat, dms, journal, log); bot.py callback pattern `priv:(ask|do|no):(chat|dms|journal|log)` | test_privacy.py::test_privacy_clears_only_after_confirming (asserts memories survive) | **partial**: memories are shown but can't be cleared there (one at a time in /memory). Cleared data also stays in the nightly backups for up to 7 days (backup.py), although the confirmation says "This can't be undone". |
| 37 | `/export`: one JSON with memories, reminders, lists, alert rules, style, settings, 60 days of /log; sign-in details left out | export.py (allow-listed settings) | test_export.py::test_export_has_the_owners_data_and_no_secrets, ::test_export_command_sends_a_file_to_the_owner | yes |
| 40 | Fired reminders: ✅ Done, ⏰ 1h, ⏰ Tomorrow; snoozing moves the same reminder | checkins.py:47-50, 92-122 | test_reminder_extras.py::test_fired_reminders_have_done_and_snooze | yes |
| 41 | Monthly and yearly repeats; Jan 31 -> Feb 28 -> Mar 31 | reminders.py `next_occurrence` with anchor | test_reminder_extras.py::test_monthly_and_yearly_repeats (`seen == [28, 31, 30]`) | yes |
| 44 | Sunday 18:00 weekly review (from /log, what's open, the week ahead); off in /settings | review.py:15-29, 46-55 | test_review.py::test_weekly_review_runs_unattended_and_can_be_turned_off, ::test_review_is_scheduled_for_sunday_evening | yes |
| 45 | 👍 / ✏️ on the brief; feedback remembered | review.py:39-85 | test_review.py::test_brief_has_feedback_buttons_and_feedback_becomes_a_memory | yes |
| 48 | `/rules`; the classifier follows them first; remove buttons; "Only you can add rules: an email can't hide the next one" | alert_rules.py; inbox_watch.py:191; tools.py:765-771 | test_alert_rules.py (4 tests) | **partial**: unattended turns can't add rules. But in a turn you start ("what's in my inbox?"), Claude can call `add_alert_rule` after reading an email. That rule takes effect at once; the only safeguard is the "📏 New alert rule" card the bot posts (tools.py:767-769). |
| 51 | Hourly digest option (/settings → Instant / hourly) | inbox_watch.py:253-260; checkins.py:340-347; setup_chat.py:374 | test_life_admin.py::test_hourly_digest_holds_alerts_and_sends_them_together | yes |
| 52 | `/focus 25` (alerts and check-ins held, ping at the end); `/note` | quiet.py:84-104 | test_quiet.py::test_focus_session_and_note | yes |
| 53 | `/quiet 2h` / 30m / `morning` pauses inbox alerts, check-ins and meeting prep; reminders still fire; held email alerts catch up | quiet.py; checkins.py:320; heartbeat.py:151; meeting_prep.py:58; the reminder job has no DnD check; catch-up = still-unread Primary mail from the last 2 days, newest 20 (inbox_watch.py:22-23) | test_quiet.py::test_parse_pause, ::test_paused_bot_stays_quiet | **partial**: the meeting-prep part of test_paused_bot_stays_quiet proves nothing. It stubs `_ask_agent`, the job calls `_run_agent`, and the calendar is empty. The code does skip prep during /quiet. |
| 56 | 📅 Times: real free slots, three proposed, "shown to you and never sent on its own" | inbox_watch.py:244-245; buttons.py:84-91 (`owner_present=False`, so any send is held by tools.py:633) | test_life_admin.py::test_meeting_requests_get_a_propose_times_button | yes |
| 57 | Trip or deadline alerts get 📅; event added, no invites | inbox_watch.py:246-247; buttons.py:92-100; tools.py:654-655 | test_life_admin.py::test_trips_and_deadlines_get_an_add_to_calendar_button | yes |
| 58 | Alerts also cover bills, renewals, travel changes, deliveries; dated alerts' ⏰ reminds the morning before ("⏰ Nov 14") | classifier prompt inbox_watch.py:43-44; button inbox_watch.py:241; buttons.py:101-115 | test_life_admin.py::test_dated_alerts_get_a_reminder_button_instead_of_later, ::test_tapping_due_reminds_the_morning_before | yes for the button; what counts as a bill or renewal is classifier behaviour (unverifiable offline) |
| 61 | `/journal on`: asks at 21:30 and saves your answer; one entry per day; `/journal` shows the week | journal.py:13-78; setup_chat.py:42, 177 | test_journal.py::test_one_entry_per_day_that_grows, ::test_evening_prompt_and_answer | **partial** at 4a3eaf1: the answer is saved only if you reply within 15 minutes (`AWAIT_SECONDS`). Later it goes to Claude as a normal message (scratch: a reply after 16 min is not saved). A /settings question asked in the meantime also displaces it. **Fixed at HEAD** by d455207 (`ask_by_reply`, "no time limit"); not run by me. 21:30 is untested. |
| 62 | `/habit workout`, asked each evening at 20:30, tap to mark done, streak; `/habits` shows them | habits.py; bot.py:346 alias | test_habits.py::test_streaks, ::test_habit_command_buttons_and_evening_job | yes (20:30 untested; correct by scratch) |
| 65 | IOUs netted per person, ✅ Settled | ious.py | test_ious.py::test_balances_net_out_and_settle, ::test_iou_tools_and_command | yes |
| 66 | Spending "summed exactly from what you logged, never estimated", chartable; `/spent` by category; every-2-weeks reminders | expenses.py (integer cents, SQL `SUM`); tools.py REPEAT_OPTIONS "biweekly" | test_expenses.py::test_ledger_sums_exactly_by_category_and_currency; test_reminder_extras.py::test_monthly_and_yearly_repeats (biweekly) | yes |
| 69 | Lists; turns you didn't start can read but not change them | lists.py; tools.py:753-756 | test_lists.py::test_list_tools | yes |
| 72 | Meeting prep about an hour before; once per meeting, at most 4 a day, not in quiet hours, off in /settings; Claude gets only the event id | meeting_prep.py:24-82 | test_meeting_prep.py (6 tests) | **partial**: "not in quiet hours" (meeting_prep.py:58) and the 15-minute cadence have no repo test (scratch: skipped in quiet hours, runs outside them; interval 900 s). The rest is tested. |
| 75 | `/style` learns from your sent mail (quotes stripped), used only after ✅ Use this; or set by hand | style.py; style_handlers.py:46-96 | test_style.py (6 tests) | yes |
| 78 | `/log`: emails delivered, drafts, events, reminders, Telegram replies, recorded when they happened; Claude checks it before saying something was sent | actions.py:51-85; tools.py run_tool; outbox.py:133; business.py:372 | test_actions.py (4 tests) | yes for the log. "Claude checks this log" is a system-prompt instruction (agent.py:56-57): unverifiable offline. |
| 81 | Connect your Telegram account; `/dms` shows who's waiting | business.py:242-291 | test_business.py::test_dms_view_and_draft_button | yes (Business Mode setup unverifiable offline) |
| 82 | Replies go out only on ✅ Send as me; a double tap sends once; outside the 24-hour window they're handed back | business.py:293-377 | test_business.py::test_send_as_me_needs_the_owners_tap_and_works_once, ::test_cancel_and_expired_window, ::test_reply_tool_never_sends_it_queues_a_card | yes (Telegram's 24 h rule itself is unverifiable offline) |
| 83 | Check-ins mention people waiting 2+ hours, "and the daily brief mentions them too" | business.py:227-239; bot.py:149-150 (brief prompt) | test_business.py::test_dm_signals_for_check_ins_wait_two_hours; the brief part is untested (test_roles.py::test_brief_focuses_on_the_job never sets `dms_connected`) | **partial** (brief part untested, and prompt-level) |
| 84 | Only your own account can connect; messages stored as data, never obeyed; kept 7 days | business.py:90-103, 128-150, 171-175 | test_business.py::test_only_the_owners_connection_counts, ::test_business_messages_are_stored_never_obeyed, ::test_old_messages_are_pruned_and_deletions_honored, ::test_a_new_owner_cant_use_the_previous_owners_connection | yes |

### 2. README.md

**Features** (intro list, "ClaudeBot also comes to you", "Feels fast and easy", "Only-on-Claude features", plus the briefings, charts, modes and roles sections):

| Claim | Code / test | Ruling |
|---|---|---|
| "reply to Sam…" sends with a 20-second Undo | config.py:47; outbox.py:75-84; test_features.py::test_outbox_queues_then_sends_after_delay | yes |
| "tell Alex 6 works" is sent when you tap | see CHANGELOG line 82 | yes |
| Monthly/yearly reminders with Done/Snooze; lists; exact free time; scheduled tasks; live web search; links; forwards fact-checked; /research; charts; briefings; real files; spreadsheet maths; /think; photos/PDFs; attachments | tools.py (each tool); tests in test_grok_features.py, test_claude_features.py, test_charts_briefings.py, test_file_uploads.py, test_release_11.py (e.g. ::test_find_free_time_tool, test_claude_features.py::test_think_streams_at_max_effort, test_charts_briefings.py::test_briefing_request_is_web_only_and_covers_only_whats_new) | yes (output quality unverifiable offline) |
| Check-ins: never in quiet hours, at most 3 a day, off in /settings | heartbeat.py:31-32, 151; round-1 tests | yes |
| Meeting prep about an hour before | CHANGELOG line 72 | yes (see line 72 for the test gaps) |
| `/waiting`: "Drafting never sends: if Claude tries, the email waits for your ✅ Send tap" | checkins.py:264 (`owner_present=False`); tools.py:633; test_release_11.py `make_bot` asserts draft turns are unattended (line 408) | yes (round 1's "no" is fixed) |
| Inbox alerts: real people, bills, travel; promos skipped (`category:primary`); quiet overnight; "tell her that works" resolves | inbox_watch.py:22, 37-54, 94-102, 270-276; test_features.py::test_alerts_only_for_new_important_email_and_records_notice | yes |
| Dated email ⏰ the morning before; trip 📅; `/rules` | CHANGELOG lines 57-58, 48 | yes |
| Daily brief with 👍/✏️; Sunday review; Telegram DMs | CHANGELOG lines 44-45, 81-84 | yes |
| "`/quiet 2h` pauses **all of it**" (it = everything in that list, including the daily brief and weekly review) | quiet.py; bot.py:945-952 (`_brief_job` has no DnD check); the reminder job also ignores it | **partial**: the daily brief still arrives during /quiet (scratch: brief ran while paused; the weekly review was skipped). So do scheduled tasks and briefings. |
| "Every alert has 🗄 Archive, ✍️ Reply (shows you a draft first) and ⏰ Later (reminds you in 3 hours)" | inbox_watch.py:34, 226-251 | **partial**: only the first 3 emails of an alert get buttons. The middle button is 📅 Times or 📅 calendar for meeting requests, trips and deadlines. ⏰ becomes "⏰ Nov 14" (the morning before) for dated mail. Labels carry the sender's name ("🗄 Lee"), not "Archive". |
| Follow-up buttons by Claude Haiku; `/followups off` | followups.py:68-70 (`config.fast_model`); test_cool_features.py::test_followups_are_short_distinct_and_capped | yes |
| `/style`, `/memory`, location and weather | test_style.py; test_cool_features.py::test_memory_view_lists_facts_with_delete_buttons, ::test_web_search_knows_where_the_owner_lives | yes |
| Answers with receipts; Agent Skills; `/think` | citations.py, workbench.py; test_claude_features.py | yes |
| "The sandbox has no internet access, so nothing in your files can be sent anywhere" | Anthropic's code-execution environment | unverifiable offline |
| Briefings: web only, never see email; up to 10 | web_agent.py; tools.py:31; test_charts_briefings.py::test_briefings_need_the_owner_and_are_capped | yes |

**Your Telegram DMs:** every bullet is yes (see CHANGELOG lines 81-84), except "the daily brief mentions them", which is **partial** as at line 83.

The two "To set it up" steps (BotFather Business Mode; Settings → Telegram Business → Chatbots) are **unverifiable offline**, and so is whether the owner needs Telegram Premium. The README says nothing about Premium. I believe Telegram documents Business features as part of Premium; worth confirming and stating.

"Kept for 7 days, on your server only" is yes for storage. Contents still reach the Claude API when you draft a reply or the brief reads DMs, as the README intro says.

**Commands:**

| Claim | Ruling |
|---|---|
| Every command named exists in bot.py | yes (see "Commands" above) |
| `/today` "instant, no AI cost" | yes (today.py, no model call; test above) |
| `/sweep` "(nothing is deleted)" | yes |
| "`/export` sends you **everything** ClaudeBot keeps about you" | **partial**: chat history and Telegram DMs are excluded (the file's own caption says so, export.py:59). Expenses come as one year of category totals and IOUs as net balances, not the entries. |
| `/quiet 2h` pauses alerts and check-ins; `/log`; `/waiting`; `/reminders`; `/usage` today and this month by feature | yes |
| Completeness | **partial**: `/owed` (1.2) is missing from the README entirely; `/habits` too |

**Safety notes:**

| Note | Code / test | Ruling |
|---|---|---|
| Sends without asking but waits `UNDO_SEND_SECONDS` with Undo; after a mid-send restart it tells you to check Sent | outbox.py:59-84, 137-165; test_features.py::test_send_interrupted_by_a_crash_is_flagged_not_resent, ::test_overdue_email_after_restart_is_held_not_sent | yes |
| Links: only ones you paste; never links that only appear in emails; deep research opens only its own search results and only you can start it | tools.py:496-503 (`url_sources.client_tool_results: none`), 681; agent.py:156-174 (background events defanged); test_grok_features.py::test_main_web_fetch_ignores_urls_from_client_tool_results, ::test_background_events_and_memories_cannot_carry_live_links, ::test_research_can_only_fetch_what_its_own_searches_found, ::test_deep_research_needs_the_owner_and_runs_once_per_turn | yes |
| Drafts-only mode | tools.py:627-632; test_release_11.py::test_drafts_only_mode_saves_instead_of_sending | yes |
| Turns you didn't start: email waits with ✅ Send / ✖️ Cancel showing every recipient (cc and bcc); no invites, memories, reminders or tasks, email changes or event changes | see the safety section; test_features.py::test_held_email_needs_send_tap_and_can_be_cancelled (cc/bcc on the card) | **partial** (true; brief and task wiring untested) |
| Email is data; alerts show the real address | inbox_watch.py:120-123; test_release_11.py::test_long_display_names_cant_hide_the_address; test_features.py::test_hostile_email_fields_are_quoted_clipped_and_fenced | yes ("ClaudeBot will flag it" is model behaviour) |
| Uploaded files deleted after the conversation, checked every 6 hours | bot.py:107, 441-443, 968-985; test_file_uploads.py::test_cleanup_deletes_files_from_finished_conversations_only | yes |
| Only the owner; 5 wrong pairing codes and that account is ignored; after 50 wrong guesses in total the code changes | bot.py:135-136, 573-597; test_launch.py::test_pairing_needs_the_code_from_the_log (covers the 5) | **partial**: the 50-guess rotation has no test |
| Google sign-in codes and the OAuth client file never shown to Claude; messages deleted | test_launch.py::test_pasted_sign_in_codes_never_reach_claude, ::test_client_files_only_when_asked_and_never_from_a_forward | yes |
| `.env`, `credentials.json`, `data/` are in `.gitignore` | .gitignore | yes |

### 3. claudebot/setup_chat.py: HELP and WELCOME

- Every command in HELP is registered, and every registered private command is in HELP except `/start` and the alias `/habits`.
- "/export – download **everything** I keep about you" is **partial**, as in the README.
- "/catchup – what you missed since last time" has the same 72-hour cap as CHANGELOG line 15. It's minor, and folded into that row.
- "/journal – a private evening journal" is yes: entries never reach Claude. They are saved by `handle_answer` and `/journal <text>`, and no tool reads them.
- "/quiet – pause alerts and check-ins" and "/focus" are yes.
- "Send a photo of a flyer or a ticket and I'll add it to your calendar" is model behaviour (unverifiable offline).
- WELCOME: the examples map to existing tools. "Once Gmail is connected, I'll ping you when important email arrives" is yes (`INBOX_ALERTS` defaults to true).

### 4. docs/index.html

| Claim | Ruling |
|---|---|
| Hero: "Runs on your own server", "Only you can use it", "Free, source on GitHub" | yes: owner filter bot.py:300-310, and all 26 button handlers check the owner |
| Chat mock: the Undo card shows the email body ("Sending to Prof. Lee: "Friday works for me…"") and buttons labelled 🗄 Archive / ✍️ Reply / ⏰ Later | **partial**: the real pending card says only "📤 Sending to {to}: {subject} in 20s" with no body (outbox.py:77). Buttons carry the sender's name ("🗄 Lee"). |
| "every 10 minutes" inbox alerts; check-ins "each thing once, at most three a day" | yes |
| **New in 1.2**: Telegram DMs "never on their own"; Sounds like you; Ready for meetings "you've accepted" (meeting_prep.py:37-48, test_meeting_prep.py::test_only_upcoming_meetings_with_other_people); Proof, not promises ("sent" always means sent: test_actions.py::test_delivered_emails_are_logged_failed_ones_are_not); Life admin; Calm by design; Money ("expenses summed exactly"); Meetings, sorted | yes |
| **"Undo for everything"**: "Every email waits with Undo. Every event added gets a Remove card. Replies from your Telegram account need your tap." | **partial**: Remove cards and the Telegram tap are yes. "Every email waits with Undo" is false when the Undo window is set to Instant (0), which /settings offers. Held emails wait for ✅ Send rather than Undo. /sweep and /triage archives have no undo. |
| Safety: "Undo every send": 20 seconds, change the window or use drafts only | yes |
| Safety: "Nothing sends while you're away": brief or task emails wait for your tap | **partial** (true; brief and task wiring untested; same row as CHANGELOG line 6) |
| Safety: "Emails are data, not orders": can't send, trash or delete while you're away; links in emails never opened | yes |
| Safety: "Only you can use it"; groups get web answers only | yes (test_grok_features.py::test_group_requests_have_no_personal_tools_and_fence_the_replied_message, ::test_owner_handlers_only_fire_in_private_chat) |
| Safety: "Runs on your machine… No ClaudeBot company in the middle" | yes by architecture; nothing to test |
| Safety: "A spending cap… stops calling Claude" | yes: `check_budget` runs before every model call (agent.py:231, 313; followups, heartbeat, inbox, replies, settings, style, web_agent, workbench); test_features.py::test_budget_is_checked_before_every_step |
| "Five minutes", "Usually a few dollars a month", "Fly.io a few dollars a month", "billed separately from Pro/Max" | unverifiable offline |
| Cost table models | yes: config.py:82, 92 (Opus 5.5, Haiku 5.5) |

### Not wrong, but worth knowing

- The "what's new" message added in 4a3eaf1 is sent from `_post_init` (bot.py:451-452). Any test that calls `_post_init` on an onboarded bot without stubbing `send_to_owner` would now try a real Telegram call. The current tests stub it; my scratch script hit this and needed the stub.
- `/focus` replaces any longer `/quiet` pause already running (quiet.py:95). Nothing claims otherwise.

---

### Claims judged "no" or "partial"

No claim is a flat "no". Even the Fly/Railway half of the health-check bullet only partly fails, because the Docker half holds. Rows 1-10 are wording problems, where the copy says more than the code does. Rows 11-16 are true, but a load-bearing part has no repo test.

| # | Where | Claim | Problem | Suggested rewording or fix |
|---|---|---|---|---|
| 1 | CHANGELOG 1.2.0 line 12 | "so Docker (and Fly/Railway) can see a stuck bot" | Only Docker reads the Dockerfile `HEALTHCHECK`. fly.toml has no `[checks]`, and Railway has no file-based check. | "…so Docker can see a stuck bot." Or add a Fly machine check to fly.toml and drop Railway. |
| 2 | README features | "`/quiet 2h` pauses all of it" | The daily brief, scheduled tasks and briefings still arrive during /quiet (bot.py:945-952). | "`/quiet 2h` pauses inbox alerts, check-ins and meeting prep (reminders and your daily brief still come)." Or add a `dnd_active` check to `_brief_job`. |
| 3 | README "Feels fast and easy" | "Every alert has 🗄 Archive, ✍️ Reply… and ⏰ Later (reminds you in 3 hours)" | Buttons cover only the first 3 emails. The middle one is 📅 for meetings, trips and deadlines. ⏰ is the morning before for dated mail. | "Alerts come with buttons: 🗄 Archive, ✍️ Reply (a draft first) or 📅 for meetings and trips, and ⏰ Later (3 hours, or the morning before a due date)." |
| 4 | CHANGELOG 1.2.0 line 33 | "Every sent email's confirmation has a ⏰ Follow up if no reply button" | With Undo set to Instant (0), the email goes out with a plain notice and no button (outbox.py:70-74). | "Sent-email cards have a ⏰ Follow up if no reply button (not with Instant sending)." Or pass a follow-up button on the instant path too. |
| 5 | CHANGELOG 1.2.0 line 36 | `/privacy` "…memories) and clears any of them after a confirmation" | Memories can't be cleared in /privacy (privacy.py:10-15), and cleared data survives in the nightly backups for up to 7 days. | "`/privacy` shows what ClaudeBot keeps and clears conversation history, DMs, journal or the action log after a confirmation (memories: /memory). Nightly backups keep a copy for up to 7 days." Or add memories to `WHAT` and prune backups on clear. |
| 6 | README Commands; HELP | "`/export` sends you everything ClaudeBot keeps about you" / "download everything I keep about you" | Chat history and DMs are excluded; expenses and IOUs are summaries. | "`/export` sends your memories, reminders, lists, rules, style, settings, journal, habits, spending totals, IOUs and 60 days of /log as a JSON file (not chat history or DMs)." HELP: "/export – download your data (JSON)". |
| 7 | CHANGELOG 1.2.0 line 48 | "Only you can add rules: an email can't hide the next one" | Only enforced in turns you didn't start. In your own turns, Claude can add a rule after reading an email; you get a "📏 New alert rule" card. | "Rules can't be added while you're away, and every new rule is announced with a link to /rules, so an email can't quietly hide the next one." |
| 8 | docs/index.html "New in 1.2" | "Undo for everything… Every email waits with Undo." | Not with Instant sending; held emails wait for ✅ Send; archives have no undo. | Heading "Undo for email and events"; body "Every email waits with Undo (unless you choose Instant). Every event added gets a Remove card. Replies from your Telegram account need your tap." |
| 9 | CHANGELOG 1.2.0 line 61 | `/journal on` "saves your answer" | At 4a3eaf1 only a reply within 15 minutes is saved (setup_chat.py:42, 177). **Fixed at HEAD** (d455207, `ask_by_reply`). | Keep the fix and add a test that replies an hour later. |
| 10 | CHANGELOG 1.2.0 lines 15, 23, 25; docs mock | "since you last asked"; snooze "at 8:00 tomorrow"; digest "then /sweep clears them out"; mock Undo card shows the body | /catchup is capped at 72 h. A snooze tapped before 04:00 returns at 08:00 that morning. /sweep doesn't touch Primary newsletters or Updates younger than 7 days. The real pending card shows recipient and subject only. | "what you missed since you last asked (up to 3 days)"; "back… at 8:00 the next morning"; "then `/sweep` clears the older ones out"; make the mock card match outbox.py:77, or add a body preview to the pending card. |
| 11 | README Commands | (completeness) | `/owed` (1.2) and `/habits` aren't in the README. | Add "`/owed` shows who owes whom, with ✅ Settled buttons" and "/habits lists them". |
| 12 | CHANGELOG line 6; README safety note; docs "Nothing sends while you're away" | Brief and scheduled tasks run unattended | True in code (bot.py:882, 951), but no test asserts the jobs pass `owner_present=False`. | In test_review.py::test_brief_has_feedback_buttons_and_feedback_becomes_a_memory assert `asked[-1][1] is False`; add a `_reminder_job` test for a `run_as_task` row. |
| 13 | CHANGELOG lines 11, 25, 61, 62, 72 | 03:00 backup, Saturday 10:00 digest, 21:30 journal, 20:30 habits, 15-minute meeting-prep job | Constants are right and scheduled (scratch), but only Sunday 18:00 is asserted. | Extend test_review.py::test_review_is_scheduled_for_sunday_evening to assert every `run_daily` time and day, and the meeting-prep interval of 900 s. |
| 14 | CHANGELOG line 8 | `/sweep` never touches starred or important mail | No test checks the queries. | Assert that each `SWEEPS` query contains `-is:starred -is:important`. |
| 15 | CHANGELOG lines 53, 72 | /quiet and quiet hours skip meeting prep | test_paused_bot_stays_quiet stubs the wrong method with an empty calendar, so its meeting-prep check is vacuous; quiet hours are untested. | Stub `_run_agent`, return one accepted meeting 45 minutes out, and assert no prep is run while paused or in quiet hours. |
| 16 | CHANGELOG lines 16, 83; README safety note on pairing | /status check-in line; the brief mentions waiting DMs; the code changes after 50 wrong guesses | The code exists, but none of these is tested. | Test `on_status` text; test `brief_prompt(..., dms_connected=True)`; test that 50 wrong codes rotate `pairing_code`. |

Unverifiable offline: Business Mode setup steps and whether Telegram Premium is needed (the README doesn't say), Telegram's 24-hour reply window, Fly/Railway health behaviour, "five minutes", "a few dollars a month", "billed separately from Pro/Max", the sandbox having no internet, and model-dependent behaviour: what the classifier counts as a bill or renewal, /trips spotting gaps, Claude checking `action_log`, photo -> calendar, and phishing flags.
