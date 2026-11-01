# Changelog

## 1.2.0

**Safer**
- Turns you didn't start (the daily brief, weekly review, scheduled tasks, meeting prep, draft buttons) can no longer set reminders or archive, trash or mark email. An email read while you're away can't plant a reminder that later speaks in ClaudeBot's voice.
- Brief feedback and journal entries only count when you reply to the question, so your next normal message isn't swallowed.
- `/sweep` never touches starred or important mail.

**Runs itself**
- Nightly database backup at 03:00 into `data/backups/` (the last 7 are kept), taken safely while the bot runs.
- Docker health check: the bot touches a file every minute and `python -m claudebot health` checks it, so Docker (and Fly/Railway) can see a stuck bot.

**Today at a glance**
- `/menu` puts a button keyboard under the chat box: 📆 Today, 📰 Catch up, 📥 Triage, ⏳ Waiting, 🗒 Lists, 🔕 Quiet 1h.
- `/catchup`: what you missed since you last asked (important email, DMs, what ClaudeBot did). `/trips`: upcoming travel from your email and calendar, with anything that looks missing.
- `/status` shows how many check-ins you got this week and how many you tapped, so you can tell whether they earn their place.
- `/today`: today's calendar, reminders due, Telegram chats waiting and open list items in one message. No AI call, so it's instant and free.

**Where the money goes**
- `/usage` breaks this month's spend down by feature: conversations, inbox alerts, check-ins, reply tracking and so on.

**Inbox cleanup**
- Email snooze: 💤 on a `/triage` card archives the email and brings it back to your inbox, unread, at 8:00 tomorrow, with a ping.
- `/triage`: go through unread important email one card at a time: 🗄 Archive, ✍️ Reply (a draft you check), ⏰ Later, ⏭ Next. Listing and archiving use no AI.
- Optional Saturday newsletter digest (`/settings`): ClaudeBot reads the week's newsletters and sends the 5 things worth knowing, then `/sweep` clears them out.
- `/sweep` counts old promotions, social and update emails and archives a whole category in one tap. Archived means out of the inbox but still in All Mail: nothing is deleted. No AI involved, so it's free.

**Undo for your calendar too**
- Repeating events: "gym every Monday and Wednesday 7-8am" or "block 9-11 every weekday until Dec 19" become real recurring events.
- Every event ClaudeBot adds shows up as a card with ↩️ Remove, including events added by scheduled tasks or the 📅 alert button.

**Never lose a thread**
- Every sent email's confirmation has a ⏰ Follow up if no reply button. Three days later ClaudeBot checks whether they answered. If they did, you get one line; if not, it drafts a polite nudge for you to send.

**Your data, yours**
- Restore: send an export file back (on a new server, say) and tap ✅ Restore. Memories, lists, upcoming reminders, rules, style, habits and journal come back; nothing you have is deleted.
- `/privacy` shows what ClaudeBot keeps (conversation history, DMs, journal, action log, memories) and clears any of them after a confirmation.
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
- Inbox alerts can come as one hourly digest instead of one ping per email (`/settings` → Instant / hourly).
- `/focus 25`: a 25-minute focus session (alerts and check-ins held), with a ping when time's up. `/note <text>` jots something into your Notes list.
- `/quiet 2h` (or 30m, or `morning`) pauses inbox alerts, check-ins and meeting prep. Reminders you set still fire, and held email alerts catch up afterwards. `/quiet off` resumes.

**Life-admin radar**
- When an email asks to meet, its alert gets a 📅 Times button. ClaudeBot finds real free slots on your calendar and drafts a reply proposing three, shown to you and never sent on its own.
- Alerts about a trip or a deadline get a 📅 button: ClaudeBot reads the email and puts it on your calendar (no invites go out).
- Inbox alerts now also cover bills with a due date, renewals about to charge, travel changes and deliveries that need you. When an alert has a date, its ⏰ button reminds you the morning before ("⏰ Nov 14") instead of in 3 hours.

**Habits**
- `/journal on`: ClaudeBot asks how your day went at 21:30 and saves your answer (one entry per day, on your server). `/journal` shows the week; `/journal <text>` writes one now.
- `/habit workout` and ClaudeBot asks each evening at 20:30, with a tap to mark it done and a running streak. `/habits` shows them all.

**Spending**
- `/subscriptions` finds recurring charges in 90 days of receipts, flags forgotten ones and duplicates, gives the monthly total, and offers to track them as bills.
- Bills: "rent is $1200 on the 1st" saves it with a monthly reminder 2 days before. `/bills` shows what's due and your monthly total; ✅ Paid logs it as spending.
- IOUs: "Alex owes me $20 for dinner", "I owe Sam $15". `/owed` nets it out per person, with a ✅ Settled button.
- "Spent $12 on lunch" logs it. "How much did I spend on food this month?" is summed exactly from what you logged, never estimated, and can be charted. `/spent` shows the month by category. Reminders can also repeat every 2 weeks.

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
