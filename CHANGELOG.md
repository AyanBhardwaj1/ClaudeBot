# Changelog

## 1.1.0

Based on market research into what people want from AI assistants and where they give up on them (`sleep-research/`).

**Tells you first**
- **Check-ins**: every few hours (never in quiet hours, at most 3 a day), ClaudeBot looks for things that need you: a calendar clash, an early start tomorrow, a reply you've owed for days, someone who hasn't answered you. It messages you only when something is new, and mentions each thing once. Turn it off in /settings.
- **/waiting**: replies you owe, and replies you're waiting on, with one-tap **Nudge** and **Reply** drafts (shown to you first, never sent on their own). Claude Haiku filters out threads that don't need an answer.

**You can check it**
- **/reminders**: everything ClaudeBot will remind you of or do later, with cancel buttons. Works even when the monthly budget is used up.
- **Drafts-only mode** (/settings): emails go to your Gmail Drafts and you send them yourself.
- ClaudeBot tells you when inbox alerts stop working (Google signed out, access revoked) and when they're back.

**Better answers**
- **Exact free time**: "when am I free for an hour Thursday?" is computed from your calendar, not estimated. Busy weeks are read in full (up to 250 events, not 25).

**Safer**
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
