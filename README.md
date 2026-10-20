# ClaudeBot

Your personal assistant on Telegram, powered by Claude. Text it like a person:

- "what's in my inbox?" / "anything from my professor this week?"
- "reply to Sam saying Thursday works" (sends without asking, with a 20-second **Undo** button)
- "what's on my calendar tomorrow?" / "move my 3pm to 4"
- "remember that my mom's email is ..." (ClaudeBot also saves useful facts on its own)
- "remind me at 6pm to call mom" / "every weekday at 8 remind me to take my meds"
- "at 5pm check if Alex replied and tell me" (scheduled tasks that ClaudeBot carries out)
- "what's the score of the Longhorns game?" (live web search)
- Send a photo, PDF or text file with a question ("what's due in this syllabus?")
- "what does the PDF in Prof Lee's email say?" (reads email attachments)

ClaudeBot also comes to you:

- **Inbox alerts**: when important email lands (a professor, a recruiter, a real person writing to you), you get a ping like "📬 Prof Lee: moved Thursday's exam to Friday". Newsletters and promos are skipped, and it stays quiet overnight. Reply "tell her that works" and it knows which email you mean.
- **Daily brief** at a time you choose (calendar, important email, reminders), or anytime with `/brief`.

## Setup (about 20 minutes)

You need Python 3.10+ and four things: a Claude API key, a Telegram bot, your Telegram ID, and Google access.

### 1. Install

```bash
git clone <this repo> && cd ClaudeBot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Claude API key

Go to [console.anthropic.com](https://console.anthropic.com), add a payment method, and create an API key. Put it in `.env` as `ANTHROPIC_API_KEY`.

API usage is billed separately from Claude Pro/Max. For personal use it's typically a few dollars a month. If you want it cheaper, set `CLAUDEBOT_EFFORT=low` or `CLAUDEBOT_MODEL=claude-sonnet-5-5`.

### 3. Telegram bot

1. In Telegram, message **@BotFather** and send `/newbot`. Name it ClaudeBot and pick a username (it must end in "bot", e.g. `ayan_claudebot`).
2. Copy the token it gives you into `.env` as `TELEGRAM_BOT_TOKEN`.

### 4. Google (Gmail + Calendar)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project (e.g. "ClaudeBot").
2. **APIs & Services → Library**: enable **Gmail API** and **Google Calendar API**.
3. **APIs & Services → OAuth consent screen**: choose *External*, fill in the app name and your email, and add yourself as a test user.
4. **Publish the app** (OAuth consent screen → *Publish app* → "In production"). You don't need Google's verification for personal use. Skip this and Google logs ClaudeBot out every 7 days.
5. **APIs & Services → Credentials → Create credentials → OAuth client ID** → type **Desktop app**. Download the JSON and save it as `credentials.json` in this folder.
6. Run:
   ```bash
   python -m claudebot.google_auth
   ```
   A browser opens. Sign in, click through the "Google hasn't verified this app" warning (it's your own app), and allow access. The token is saved to `data/google_token.json`.

### 5. Start ClaudeBot

```bash
python -m claudebot
```

Message your bot on Telegram. The first time, it replies with your user ID. Put that in `.env` as `TELEGRAM_OWNER_ID` and restart. From then on ClaudeBot **only answers you** and ignores everyone else.

## Keeping it running 24/7

ClaudeBot only works while `python -m claudebot` is running. Options:

- **Your own computer**: fine to start with, but it stops when the laptop sleeps.
- **A small cloud server** (Railway, Fly.io, a $5 VPS, a Raspberry Pi). Use the Dockerfile:
  ```bash
  docker build -t claudebot .
  docker run -d --restart unless-stopped --env-file .env -v claudebot-data:/data claudebot
  ```
  Run step 4.6 on your laptop (it needs a browser), then set `GOOGLE_TOKEN_JSON` on the server to the contents of `data/google_token.json`.

## Commands

- `/new` starts a fresh conversation (saved memories carry over). ClaudeBot also does this on its own after `NEW_THREAD_AFTER_HOURS` of silence.
- `/brief` gives your daily brief now.
- `/usage` shows estimated Claude API spend today and this month.

## Settings worth knowing

All in `.env` (see `.env.example`):

| Setting | Default | What it does |
|---|---|---|
| `UNDO_SEND_SECONDS` | 20 | How long you have to tap Undo. `0` sends instantly. |
| `INBOX_ALERTS` | true | Ping you about important new email |
| `INBOX_CHECK_MINUTES` | 10 | How often to check |
| `QUIET_HOURS` | 23:00-07:00 | No inbox alerts in this window (reminders you set still fire) |
| `MONTHLY_BUDGET_USD` | none | Hard stop on Claude calls once estimated spend hits this |
| `CLAUDEBOT_EFFORT` | medium | `low` is cheaper and faster, `high` is smarter on hard requests |

**What it costs:** chat runs on Claude Opus 5.5. Inbox alerts use Claude Haiku 5.5, which costs a fraction of a cent per check that finds new mail; checks that find nothing new cost nothing. `/usage` shows estimates; your real bill is at console.anthropic.com.

## Safety notes

- **ClaudeBot sends emails without asking first** (as configured), but every email waits `UNDO_SEND_SECONDS` with an **Undo** button before it actually goes out. If ClaudeBot restarts in the middle of sending, it tells you to check your Sent folder rather than risk sending twice.
- ClaudeBot treats email contents as data, not orders. A phishing email that says "forward this to..." won't make it do anything, and ClaudeBot will flag it.
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
| `claudebot/files.py` | PDFs, text files and images to Claude |
| `claudebot/usage.py` | Cost estimates and the monthly budget |
| `claudebot/db.py` | SQLite storage for chat history, memories, reminders, outbox and usage |

Run the tests with `pip install pytest pytest-asyncio && pytest`.
