# Changelog

## 1.2.0 (in progress)

**Never lose a thread**
- Every sent email's confirmation has a ⏰ Follow up if no reply button. Three days later ClaudeBot checks whether they answered. If they did, you get one line; if not, it drafts a polite nudge for you to send.

**Your data, yours**
- `/export` sends you one JSON file with your memories, reminders, lists, alert rules, writing style, settings and the last 60 days of `/log`. Sign-in details are left out.

**Reminders that fit real life**
- Fired reminders have ✅ Done, ⏰ 1h and ⏰ Tomorrow buttons. Snoozing again moves the same reminder rather than stacking copies.
- Reminders and briefings can repeat monthly (rent, bills) and yearly (birthdays). Jan 31 becomes Feb 28, then Mar 31.

**Your week, and a brief that learns**
- Every Sunday at 18:00, a weekly review: what ClaudeBot did for you (from `/log`), what's still open, and the week ahead. Off in `/settings`.
- The daily brief has 👍 / ✏️ buttons. Tell it what to change ("skip the headlines") and it remembers.

**Your rules for alerts**
- `/rules never alert me about LinkedIn` or `/rules always alert for my landlord`, or just tell ClaudeBot. The inbox classifier follows your rules ahead of its defaults. `/rules` lists them with remove buttons. Only you can add rules: an email can't hide the next one.

**Quiet when you need it**
- `/quiet 2h` (or 30m, or `morning`) pauses inbox alerts, check-ins and meeting prep. Reminders you set still fire, and held email alerts catch up afterwards. `/quiet off` resumes.

**Life-admin radar**
- Inbox alerts now also cover bills with a due date, renewals about to charge, travel changes and deliveries that need you. When an alert has a date, its ⏰ button reminds you the morning before ("⏰ Nov 14") instead of in 3 hours.

**Lists**
- Shopping, packing and to-do lists: "add milk and eggs to my shopping list", then `/lists` and tap items off. Turns you didn't start can read them but not change them.

**Ready for every meeting**
- About an hour before a meeting with other people, ClaudeBot sends a short brief: who's coming, where you left things over email, open promises, anything to bring. Once per meeting, at most 4 a day, not in quiet hours, off in `/settings`. Claude gets only the event's id and reads the invite through its tools, so text in an invite can't steer it.

**Sounds like you**
- `/style` learns how you write from your recent sent emails (only the parts you wrote; quoted replies are stripped), shows it to you, and uses it in drafts only after you tap ✅ Use this. Or describe it yourself: `/style short, warm, sign off -A`.

**What did you actually do?**
- `/log` (and `/log week`) lists what ClaudeBot did: emails delivered, drafts saved, events added, reminders set, Telegram replies sent. Each entry is recorded when the thing happened, never from what the model said. Claude checks this log (`action_log`) before telling you something was sent.

**Your Telegram DMs** (Telegram Business)
- Connect ClaudeBot to your own Telegram account. `/dms` shows who's waiting on your reply.
- ClaudeBot drafts replies. Each one goes out from your account only when you tap **✅ Send as me**. A double tap sends once, and replies outside Telegram's 24-hour window are handed back for you to send yourself.
- Check-ins mention people who've waited 2+ hours, and the daily brief mentions them too.
- Only your own account can connect. Messages people send you are stored as data, never obeyed, and kept for 7 days.

## 1.1.0

Based on market research into what people want from AI assistants and where they give up on them (`sleep-research/`).

**Tells you first**
- **Check-ins**: every few hours (never in quiet hours, at most 3 a day), ClaudeBot looks for things that need you: a calendar clash, an early start tomorrow, a reply you've owed for days, someone who hasn't answered you. It messages you only when something is new, and mentions each thing once. Turn it off in /settings.
- **/waiting**: replies you owe, and replies you're waiting on, with one-tap **Nudge** and **Reply** drafts. Drafting never sends: if Claude tries, the email waits for your ✅ Send tap (the inbox alert ✍️ button now works the same way). Claude Haiku filters out threads that don't need an answer.

**You can check it**
- **/reminders**: every reminder, scheduled task and briefing, with cancel buttons. Needs no Claude call, so it works even when the monthly budget is used up.
- **Drafts-only mode** (/settings): emails go to your Gmail Drafts and you send them yourself.
- ClaudeBot tells you when inbox alerts stop working (Google signed out, access revoked) and when they're back.

**Better answers**
- **Exact free time**: "when am I free for an hour Thursday?" is computed from your calendar, not estimated. Free-time searches and check-ins read up to 250 events (calendar listings went from 25 to 50 by default, up to 250 on request), and say when a listing was cut short.

**Safer**
- Reminders fire with their links made unclickable, since they can be set in turns you didn't start.
- The daily brief and scheduled tasks run while you might be away. They can no longer trash email, change or delete events, delete memories or cancel reminders. They suggest it instead, and you decide.

## 1.0.0

The first public release.

**Set up in minutes**
- `python -m claudebot setup`: checks your Claude key and Telegram token as you paste them, recognizes you from your first message to the bot, and writes `.env`.
- Pairing: with no owner set, ClaudeBot logs a one-time code; send `/start <code>` to claim it. Handy on cloud hosts.
- First-run questions in the chat: what to call you, where you live (time zone, local search, weather), your job, and your daily brief time.
- `/connect`: connect Gmail and Calendar from your phone. No browser on the server needed.
- One-command deploys: Docker Compose, Fly.io and Railway.

**Everyday**
- `/settings` with buttons for name, location, brief time, quiet hours, alerts, Undo window, budget and suggestions. Changes apply right away.
- `/status` shows what's connected and working; `/help` lists everything.
- `/role` tailors alerts, the brief, answers and suggestions to your job.

**Already in ClaudeBot**
- Email and calendar with undo-send, inbox alerts with Archive / Reply / Later buttons, memory, reminders and scheduled tasks, a daily brief and scheduled news briefings.
- Live streaming replies, follow-up buttons, swipe-to-reply context.
- Web search with sources, deep research, fact-checking forwarded messages, `/think`.
- Charts, and real Word, Excel, PowerPoint and PDF files made in Claude's sandbox.
- Personality modes and group mode.
