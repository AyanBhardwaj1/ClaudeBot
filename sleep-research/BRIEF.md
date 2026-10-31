# Brief: ClaudeBot market research

**Product:** ClaudeBot 1.0, a self-hosted, single-owner personal assistant on Telegram, built on the Claude API (Opus 5.5 for chat, Haiku 5.5 for cheap triage). Python, python-telegram-bot 22.8, SQLite.

**What it already does:**
- Gmail: search, read, send with an Undo window, drafts, archive, attachments.
- Google Calendar.
- Memory (/memory to view and delete), reminders and scheduled tasks.
- Daily brief, plus scheduled news briefings.
- Inbox alerts with Archive / Reply / Later buttons.
- Web search and fetch with citations, /research (deep research), /think (max effort).
- Fact-checking forwarded messages.
- Charts.
- Code-execution sandbox with docx/xlsx/pptx/pdf skills; reads photos, PDFs and files through the Files API (voice notes are NOT supported: no speech-to-text API).
- Personality modes (/mode), job profiles (/role).
- Group mode (tag the bot; web search only).
- Live streaming replies, follow-up suggestion buttons, swipe-reply context.
- Setup wizard, pairing code, in-chat onboarding, /settings, /connect (Google OAuth from a phone), /status, /help.
- Monthly budget cap and /usage.
- Docker, Fly.io and Railway deploys; landing page.

**Security model (non-negotiable):**
- Only the owner can use it.
- Email, web and forwarded text is untrusted and is fenced as data.
- No unattended sends: background turns need a tap to send.
- Link previews are off, and URLs from untrusted text are defanged.
- History is append-only.

**Goal of this run:** market research on personal AI assistants (late 2026). Find the features users want most and where ClaudeBot falls short, pick the highest-value improvements and new features, and implement them test-first.

**Constraints:**
- Self-hosted, one owner.
- Keep the security model.
- No paid third-party services beyond the Claude, Telegram and Google APIs.
- Features must be testable offline with fakes.

**Non-goals:**
- Hosted multi-tenant service (the user chose self-hosted).
- iMessage, or Instagram DMs on personal accounts (no API).
