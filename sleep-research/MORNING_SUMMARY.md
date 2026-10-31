# Morning summary: ClaudeBot market research → 1.1
Run claudebot-market-20261031 · reviewer route: same-family (**provisional**)

**Outcome:** ClaudeBot 1.1 is shipped to `main`. 241 tests pass. Code review: 7/10 "almost", and every finding from it is fixed.

**What the market says** (traces/literature/*; most evidence is search snippets and vendor pages, so it is directional):
- Users quit AI assistants over:
  1. unreliability;
  2. actions behind their back;
  3. runaway cost.
- Winners live in a messenger, message you first with judgment rather than on a timer, and keep you in the loop.
- OpenClaw, the closest self-hosted rival, is known for security and cost problems. That is ClaudeBot's opening.

**What shipped:**
- **Check-ins:**
  - code-found calendar clashes, early starts, and owed or awaited replies;
  - Haiku only picks which items to mention; the message is written by code;
  - each item once, at most 3 a day, reply-only check-ins once a day, quiet hours, an off switch.
- **/waiting** with Nudge and Reply drafts. Drafting can't send.
- **/reminders**, **drafts-only mode**, and exact **find_free_time**.
- **Inbox-failure notices.**
- **Security fix:** the unattended brief and tasks can no longer trash email, edit or delete events, or delete memories or reminders.

**Decided without asking:**
- Check-ins are ON by default.
- New all-day events are created as "free".
- Archive stays allowed in scheduled tasks.

**Waiting on you:**
1. Pick a **license**. The landing page no longer says "open source" because there isn't one.
2. Telegram Business (DM triage and reply-as-me) is the top backup: your original "text people for me" ask. It needs a decision on how much DM access you want.
3. Check-in quality can only be judged by using it for about 2 weeks. Targets: ≤3 a day, ≥40% acted on, spend under $0.50 a month (/usage, source "heartbeat").

**Next step:** use 1.1 for two weeks, then run a session on C21 Telegram Business or C4 "writes in your voice".
