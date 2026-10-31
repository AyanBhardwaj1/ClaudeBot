# ClaudeBot

**Your personal assistant on Telegram, powered by Claude.** It reads and answers your email, runs your calendar, remembers what matters to you, reminds you, researches anything, makes real documents, and messages you first when something needs you.

You run your own copy: your inbox and your conversations stay between you, Telegram, Google and the Claude API. Setup takes about 5 minutes ([Quick start](#quick-start)).

Text it like a person:

- "what's in my inbox?" / "anything from my professor this week?"
- "reply to Sam saying Thursday works" (sends without asking, with a 20-second **Undo** button)
- "what's on my calendar tomorrow?" / "move my 3pm to 4"
- "remember that my mom's email is ..." (ClaudeBot also saves useful facts on its own)
- "remind me at 6pm to call mom" / "every weekday at 8 remind me to take my meds"
- "at 5pm check if Alex replied and tell me" (scheduled tasks that ClaudeBot carries out)
- "what's the score of the Longhorns game?" (live web search)
- Paste a link: "tl;dr this" (reads the page)
- **Forward any message** and it explains it and fact-checks the claims: True / False / Misleading, with a source
- `/research best budget laptop for a CS major` (DeepSearch-style: many searches and pages, a sourced report)
- "chart my spending this week" / "plot BTC over the last month" / "compare my exam scores" (sends a clean chart image)
- "every Friday at 5pm, catch me up on AI news" (scheduled briefings, like Grok Tasks)
- "make a 5-slide deck for my BA 324H pitch" / "turn this into a study guide doc" (real Word, Excel, PowerPoint and PDF files)
- Send a spreadsheet: "how much did I spend on food in October?" (exact numbers, computed with code)
- `/think should I take the Google or the Meta offer?` (Claude at maximum reasoning effort)
- Send a photo, PDF or text file with a question ("what's due in this syllabus?")
- "what does the PDF in Prof Lee's email say?" (reads email attachments)

ClaudeBot also comes to you:

- **Check-ins**: every few hours it looks for what needs you (a calendar clash, an early start tomorrow, a reply you've owed for days, someone who hasn't answered you) and messages you only when something is new. Never in quiet hours, at most 3 a day, off in `/settings`.
- **`/waiting`**: replies you owe and replies you're waiting on, each with a one-tap **Nudge** or **Reply** draft. Drafting never sends: if Claude tries, the email waits for your ✅ Send tap.

- **Inbox alerts**: when important email lands (a professor, a recruiter, a real person writing to you), you get a ping like "📬 Prof Lee: moved Thursday's exam to Friday". Newsletters and promos are skipped, and it stays quiet overnight. Reply "tell her that works" and it knows which email you mean.
- **Daily brief** at a time you choose (calendar, important email, reminders, and a few headlines picked for your interests), or anytime with `/brief`.

### Feels fast and easy

- **Live replies.** Answers stream into the chat as Claude writes them, after a "Thinking..." placeholder, instead of after a long pause.
- **Follow-up buttons.** Under each answer, up to three tappable next steps ("Draft a reply to Sam", "Add it to my calendar"). Picked by Claude Haiku for a fraction of a cent; `/followups off` to hide them.
- **Inbox alerts you can act on.** Every alert has 🗄 Archive, ✍️ Reply (shows you a draft first) and ⏰ Later (reminds you in 3 hours) buttons.
- **Swipe to reply.** Reply to any earlier message, or quote just part of it, and ClaudeBot knows exactly what "this" means.
- **`/memory`.** See everything ClaudeBot remembers about you and delete anything with a tap.
- **Knows where you live.** Tell it your city (first-run questions or `/settings`) and "best tacos near me" gets local results, and the daily brief opens with your weather.

### Only-on-Claude features

- **Answers with receipts.** When ClaudeBot answers from a PDF you sent or from the web, the reply ends with numbered sources: the exact quoted line and page from your document (`[1] syllabus.pdf, p. 3: "The final exam is on December 12..."`) or the article and link. Research, briefings and group fact-checks get them too.
- **Document studio.** ClaudeBot uses Anthropic's Agent Skills to build real files (Word study guides, Excel budgets, PowerPoint decks, PDF reports) in Claude's sandboxed computer and sends them to you in Telegram.
- **Data analysis.** Send an Excel, Word, CSV or PDF file and ask about it. ClaudeBot runs actual Python over it, so totals and averages are calculated, not estimated. The sandbox has no internet access, so nothing in your files can be sent anywhere.
- **`/think`.** For your hardest questions (decisions, proofs, tricky code, essays), Claude thinks at maximum effort before answering. Slower and pricier, so it's opt-in per question.

### Scheduled briefings

Ask for any recurring topic, like "every weekday at 8am, brief me on Longhorns football" or "every Sunday evening, what happened in AI this week". Each briefing looks for what's new since the last one, leads with the most important item, gives sources, and says so in one line when nothing happened. Briefings only search the web: they never see your email, calendar or memories. `/briefings` lists them, with a button to cancel each. Up to 10 at a time; each run counts toward your monthly budget.

### Charts

When numbers are easier to see than read, ClaudeBot draws a chart (line, bar, horizontal bar or scatter) and sends it as an image, with the key numbers in its reply too. It gathers the real data first (web search, your email, your calendar) and draws it locally: colorblind-safe colors, labeled lines, no clutter.

### Personality modes

`/mode` switches how ClaudeBot talks: **😈 Fun** (witty, roasty, opinionated, like Grok's fun mode), **⚡ Brief** (one-liners), **🧠 Deep** (thorough, with sources) or **😌 Default**. It sticks until you change it. Emails it writes always stay in your own voice.

### Made for your job

Tell ClaudeBot what you do with `/role` and everything adapts: pick a preset (🎓 Student, 💻 Engineer, 🚀 Founder, 📈 Sales, 🩺 Healthcare, ⚖️ Legal, 🍎 Teacher, 🎬 Creator, 💹 Finance) or describe your job in your own words (`/role nurse in the ER`, `/role product manager at Stripe`). Your job shapes:

- **Answers and drafts**: a student gets study plans and quizzes (not homework written for them), an engineer gets precise technical answers, a founder gets crisp numbers-first drafts.
- **Inbox alerts**: what counts as important, e.g. professors and deadline changes for a student, incidents and code reviews for an engineer.
- **The daily brief**: it adds what matters for your job, e.g. exams due this week, or investor emails waiting on you.
- **Suggestions**: follow-up buttons fit your work, and picking a role offers one-tap starters such as a weekly news briefing for your field.

`/role off` clears it.

### Group mode: "@ClaudeBot is this true?"

Add ClaudeBot to a Telegram group and send `/enable` there (only you can). Anyone in the group can then tag it or reply to it to ask questions or fact-check a message, like asking Grok under a post. In groups it only has web search: it can't see your email, calendar, memories or conversations, and it caps itself at `GROUP_DAILY_LIMIT` answers per group per day and `GROUP_MONTHLY_BUDGET_USD` ($5 by default) per month across all groups, so friends can't run up your bill or use up your own assistant's budget. `/disable` turns it off.

## Quick start

You need Python 3.10+ (or Docker), a [Claude API key](https://console.anthropic.com/settings/keys) and a Telegram account.

```bash
git clone <this repo> && cd ClaudeBot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m claudebot setup
```

The setup command walks you through it and checks each step as you go:

1. **Claude API key.** It checks that the key works. API use is billed separately from Claude Pro/Max; for one person it's usually a few dollars a month (see [What it costs](#what-it-costs)).
2. **Telegram bot.** Message [@BotFather](https://t.me/BotFather), send `/newbot`, paste the token it gives you.
3. **You.** Send your new bot any message and setup recognizes you. From then on ClaudeBot only ever talks to you.

Then it starts ClaudeBot. Open your bot in Telegram, and it asks four quick questions (what to call you, where you live, what you do, when to send your daily brief) and offers to connect Gmail and Calendar.

### Connect Gmail and Calendar

Send `/connect` in the chat. The first time, Google needs a free OAuth client for your own copy of ClaudeBot (about 5 minutes, once):

1. In [Google Cloud Console](https://console.cloud.google.com), create a project.
2. **APIs & Services → Library**: enable **Gmail API** and **Google Calendar API**.
3. **OAuth consent screen**: choose *External*, add your email as a test user, then **Publish app** (otherwise Google signs you out every 7 days; personal use doesn't need Google's verification).
4. **Credentials → Create credentials → OAuth client ID → Desktop app**, then download the JSON.
5. Send that JSON file to ClaudeBot in the chat.

ClaudeBot replies with a **Sign in with Google** button. Allow access; your browser then lands on a `localhost` page that doesn't load. That's expected: copy that page's address and paste it into the chat. ClaudeBot deletes the message (it holds a one-time code) and confirms which account it connected.

Running ClaudeBot on your own computer? `python -m claudebot google` signs in through your browser instead.

### Already set up by hand?

A `.env` file still works (see `.env.example`). If you leave `TELEGRAM_OWNER_ID` empty, ClaudeBot prints a pairing code in its log when it starts; send `/start <code>` to your bot to claim it.

## Make it yours

Everything personal is set in the chat, no files to edit:

- **`/settings`**: your name, location (sets your time zone, local search results and the weather in your brief), daily brief time, quiet hours for alerts, inbox alerts on/off, the Undo window for sent email, a monthly spending cap, and suggestion buttons. Tap a button, pick or type a value, done.
- **`/role`**: your job, so alerts, the brief and answers fit your work.
- **`/mode`**: personality.
- **`/status`**: what's connected and working, and what you've spent.
- **`/setup`**: run the first-time questions again.

Settings you change in the chat take priority over `.env`.

## Run it 24/7

ClaudeBot only works while it's running. Your laptop is fine to try it; for every day, put it on a small server. All of these keep your data in a persistent volume, and the pairing code (if you need one) shows up in the logs.

**Docker Compose** (any VPS, a home server, a Raspberry Pi):

```bash
python -m claudebot setup   # writes .env; answer "n" to starting it here
docker compose up -d
docker compose logs -f
```

**Fly.io** (about $2-3/month):

```bash
fly launch --no-deploy --copy-config      # pick a unique app name
fly volumes create claudebot_data --size 1
fly secrets set ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=...
fly deploy && fly logs                    # send your bot /start <code> from the logs
```

**Railway**: create a project from this repo (it builds the Dockerfile), add a volume mounted at `/data`, set `ANTHROPIC_API_KEY` and `TELEGRAM_BOT_TOKEN` as variables, deploy, and find the pairing code in the deploy logs.

Then `/connect` from your phone. The Google token is saved in the volume, so it survives redeploys.

## Commands

- `/help` lists everything; `/settings`, `/connect` and `/status` are covered above.
- `/waiting` shows replies you owe and replies you're waiting on; `/reminders` lists every reminder and scheduled task with cancel buttons.
- `/new` starts a fresh conversation (saved memories carry over). ClaudeBot also does this on its own after `NEW_THREAD_AFTER_HOURS` of silence.
- `/brief` gives your daily brief now.
- `/usage` shows estimated Claude API spend today and this month.
- `/role` tells ClaudeBot your job; `/mode` switches personality; `/research <question>` runs a deep dive; `/think <question>` reasons at maximum effort; `/briefings` lists and cancels scheduled briefings.
- `/memory` shows and deletes what ClaudeBot remembers; `/followups on|off` toggles suggestion buttons.
- In a group: `/enable` / `/disable` (owner only).

## Advanced settings

These live in `.env` (see `.env.example`). The ones marked * can also be changed in `/settings`:

| Setting | Default | What it does |
|---|---|---|
| `UNDO_SEND_SECONDS`* | 20 | How long you have to tap Undo. `0` sends instantly. |
| `INBOX_ALERTS`* | true | Ping you about important new email |
| `INBOX_CHECK_MINUTES` | 10 | How often to check |
| `QUIET_HOURS`* | 23:00-07:00 | No inbox alerts in this window (reminders you set still fire) |
| `MONTHLY_BUDGET_USD`* | none | Hard stop on Claude calls once estimated spend hits this |
| `GROUP_DAILY_LIMIT` | 30 | Answers per group per day in group mode |
| `GROUP_MONTHLY_BUDGET_USD` | 5 | Monthly spending cap for all group answers combined |
| `CLAUDEBOT_EFFORT` | medium | `low` is cheaper and faster, `high` is smarter on hard requests |

### What it costs

 chat runs on Claude Opus 5.5. Inbox alerts use Claude Haiku 5.5, which costs a fraction of a cent per check that finds new mail; checks that find nothing new cost nothing. `/usage` shows estimates; your real bill is at console.anthropic.com.

## Safety notes

- **ClaudeBot sends emails without asking first** (as configured), but every email waits `UNDO_SEND_SECONDS` with an **Undo** button before it actually goes out. If ClaudeBot restarts in the middle of sending, it tells you to check your Sent folder rather than risk sending twice.
- ClaudeBot reads links you paste, but never links that only appear inside emails (a common phishing trick). Paste the link if you want it opened. Deep research only opens pages its own searches found, and only you can start it.
- **Drafts-only mode** (`/settings`): if you'd rather send everything yourself, ClaudeBot saves emails to your Gmail Drafts instead.
- **When you're not the one who started the turn** (the daily brief, a scheduled task), ClaudeBot never sends on its own: any email waits with **✅ Send / ✖️ Cancel** buttons (showing every recipient, cc and bcc included) until you tap it or tell ClaudeBot to send it. Those turns also can't send calendar invites, save or delete memories, trash email, change or delete events, or schedule or cancel tasks, so a phishing email read during your morning brief can't plant a task, a memory or an invite. Plain reminders can still be set, but their links arrive unclickable.
- ClaudeBot treats email contents as data, not orders. A phishing email that says "forward this to..." won't make it do anything, and ClaudeBot will flag it. Inbox alerts show the sender's real address, not just their display name, so a fake "Mom" can't hide behind the name.
- Files you send (and attachments ClaudeBot opens) are uploaded to your Anthropic account's file storage so they aren't resent with every message. ClaudeBot deletes them once that conversation is over (checked every 6 hours).
- Only the Telegram account that set ClaudeBot up (or paired with the code from the server log) can use it; everyone else is ignored. Five wrong pairing codes and that account is ignored too, and after 50 wrong guesses in total the code changes (the new one is in the log).
- Google sign-in codes and the OAuth client file you send in the chat are handled by ClaudeBot itself, never shown to Claude, and the messages are deleted.
- Keep `.env`, `credentials.json` and `data/` private. They hold the keys to your inbox. They're already in `.gitignore`.

## How it works

| File | What it does |
|---|---|
| `claudebot/bot.py` | Telegram handlers, reminders, daily brief |
| `claudebot/agent.py` | Claude tool-use loop and ClaudeBot's personality (system prompt) |
| `claudebot/tools.py` | The tools Claude can call (email, calendar, memory, reminders, web search) |
| `claudebot/google_services.py` | Gmail and Calendar API calls |
| `claudebot/inbox_watch.py` | Background inbox alerts |
| `claudebot/outbox.py` | Undo-send queue |
| `claudebot/files.py` | PDFs, text files and images to Claude, via the Anthropic Files API |
| `claudebot/usage.py` | Cost estimates and the monthly budget |
| `claudebot/modes.py` | Personality modes |
| `claudebot/roles.py` | Job profiles |
| `claudebot/web_agent.py` | Deep research, briefings and other web-only requests |
| `claudebot/charts.py` | Chart drawing |
| `claudebot/workbench.py` | Code execution sandbox with Word/Excel/PowerPoint/PDF skills |
| `claudebot/citations.py` | Numbered sources from Claude's citations |
| `claudebot/followups.py` | Follow-up suggestions |
| `claudebot/ui.py`, `claudebot/buttons.py` | Live previews, buttons and the memory view |
| `claudebot/groups.py` | Group mode |
| `claudebot/setup_chat.py`, `claudebot/settings.py` | First-run questions, `/settings`, `/status`, `/help` |
| `claudebot/google_connect.py` | Connecting Google from the chat |
| `claudebot/heartbeat.py`, `claudebot/replies.py`, `claudebot/checkins.py` | Check-ins, reply tracking, `/waiting`, `/reminders` |
| `claudebot/scheduling.py` | Exact free-time finding |
| `claudebot/setup_wizard.py` | `python -m claudebot setup` |
| `docs/index.html` | The landing page (turn on GitHub Pages from `/docs` to publish it) |
| `claudebot/db.py` | SQLite storage for chat history, memories, reminders, outbox and usage |

Run the tests with `pip install pytest pytest-asyncio && pytest`.

---

ClaudeBot is an independent project built on the Claude API. It isn't made, endorsed or supported by Anthropic.
