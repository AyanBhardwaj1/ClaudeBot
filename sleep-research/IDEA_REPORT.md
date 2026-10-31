# Idea Report: ClaudeBot market research and feature selection
Run: claudebot-market-20261031 · Reviewer route: same-family (provisional). No cross-family model (Codex or Gemini CLI) was available, so a fresh Claude subagent that sees only the files does the triage.

## Executive summary
(Filled in after triage.)

## Market landscape
Full sourced reports:
- `traces/literature/competitors.md`: 29 searches, 13+ products, a 25-row feature matrix.
- `traces/literature/user_needs.md`: 25 searches; 15 needs, 10 delight features, 5 trust concerns.
- `traces/literature/platform.md`: Telegram, Claude and Google API capabilities.

Caveat that applies to all three: the researchers' page fetches were blocked by the network policy. Claims rest on search-result snippets with source URLs, and mirrored Reddit posts can't be matched to exact comments. Treat frequencies as directional.

**Who ClaudeBot competes with:**
- **Poke** (iMessage/SMS/WhatsApp): the breakout proactive assistant, but criticized for weak triage.
- **OpenClaw/Clawdbot**: the closest self-hosted Telegram analogue. It has heartbeat proactivity, but heavy security and cost problems.
- **Lindy and Martin**: paid agents.
- **ChatGPT Pulse/Tasks and Gemini AI Inbox/Agent**: platform gravity, gated behind $20-$200 plans.
- **Superhuman, Shortwave, Fyxer and Inbox Zero**: AI email clients with triage, auto-drafts, voice matching and reply tracking.

**What winners share (competitors.md §c):**
1. They live in a messenger people already use.
2. Proactivity that feels like judgment, not cron.
3. Triage accuracy with confirm-before-acting.
4. Security is now a differentiator; OpenClaw's weakness is ClaudeBot's strength.
5. Cost: per-token pricing with a cap is a counter-position to $49-$199 plans.

**Top user pain points (user_needs.md §a, ranked):**
1. Reliability: silent failures, false "done", broken reminders.
2. Fear of wrong or autonomous sends.
3. Runaway cost from background polling on expensive models.
4. Setup friction.
5. Drafts that don't sound like me.
6. Memory that forgets or over-recalls.
7. Follow-up tracking.
8. Verbosity.
9. Notification overload.
10. Student deadline check-ins.
11. Hallucinated summaries.
12. Fits existing channels.
13. Meeting prep.
14. Life-admin extraction (bills, packages, travel).
15. Birthdays and a personal CRM.

**Where ClaudeBot already leads:**
- Messenger channel, email, calendar, reminders, scheduled tasks, brief, memory, research. (Not voice notes: there is no speech-to-text API in scope; see C27.)
- Human-in-the-loop sends (undo, tap-to-send when unattended).
- Untrusted-text fencing.
- Budget cap.
- Five-minute setup.
- Fact-checking, a code sandbox with office files, job profiles.

## Candidate pool
Lenses: **CT** competitor-transfer · **PP** user pain point · **UA** untested assumption · **PC** platform capability · **DG** diagnostic/trust.

Each idea carries `prior_work` (who has it), `so_what` and `effort_note`. No idea has been dropped for taste. Feasibility drops apply only on an objective constraint from BRIEF.md (offline-testable; Claude, Telegram and Google APIs only; security model intact).

| # | Idea | Lens | prior_work | so_what | effort_note |
|---|---|---|---|---|---|
| C1 | **Heartbeat**: a judgment-based proactive check every few waking hours (calendar conflicts, deadlines mentioned in email, important unanswered threads, tomorrow's early event). Runs on Haiku, says nothing when there's nothing to say, capped at N pings a day, actions behind buttons | CT, PP | Poke, OpenClaw heartbeat, Gemini Spark, ChatGPT Pulse | #1 ranked competitor gap; "proactive vs alarm clock" is the main praise | M. New job plus Haiku structured output over calendar and inbox snapshots; must not reproduce OpenClaw's cost blowup (skip when nothing changed) |
| C2 | **Reply tracking**: "waiting on" (you emailed, no reply in N days) and "you owe" (important email you haven't answered), with a one-tap **Nudge** that drafts a follow-up (tap to send) | CT, PP | Inbox Zero Reply Zero, Superhuman, Fyxer, Lindy | Pain #7, delight #8; every major email tool ships it | M. Gmail thread queries (`in:sent`, thread last-sender), a `/waiting` command, a heartbeat hook |
| C3 | **Meeting prep briefs**: N minutes before a meeting with other people, send who they are (from past email and memory), the last thread with them, and the agenda | PP, CT | Brief My Meeting, Fireflies prep, Littlebird | Pain #13, delight #9; strong fit for founders, sales and students (office hours) | M. Calendar scan job plus agent-style summary with only read tools; must stay read-only when unattended |
| C4 | **Writes in your voice**: learn a style guide from ~30 sent emails (Haiku), store it, and inject it into email drafting; `/style` shows and resets it | CT, PP | Fyxer, Shortwave Ghostwriter, Superhuman, Lindy | Pain #5, delight #5 | S-M. One-off analysis; style text goes in as a mid-conversation system message (keeps prompt cache) |
| C5 | **Plain-English inbox rules and Gmail labels** ("anything from my landlord is urgent", "label receipts as Receipts") applied by the inbox watcher | CT | Shortwave AI Filters, Inbox Zero, Superhuman Auto Labels, Notion Mail | Most common email feature (9 products); also improves alert accuracy | M. Rules table plus classifier output field plus Gmail labels API; label creation is a write, so owner-confirmed |
| C6 | **Find-a-time**: a deterministic free-slot finder over Calendar, proposing 3 slots in a reply draft | CT | Gemini Help me schedule, Lindy, Martin, Claude connector | Pain: scheduling back-and-forth; delight #6 | S. A `find_free_time` tool over events (or freebusy); drafting already exists |
| C7 | **Snap-to-calendar**: forward a flyer, email or PDF and get a proposed event with an Add button | CT | Alexa+, HelloAria, Toki, Shortwave | Life-admin capture | S. Agent can already create events; needs a confirm-card flow |
| C8 | **Lists**: shopping, packing and to-do lists with check-off buttons (`/lists`) | CT | Coco, Yaya, Martin, Gemini/Google Tasks | Core to WhatsApp bots; daily-use stickiness | S-M. SQLite tables plus tools plus an inline keyboard |
| C9 | **Brief feedback**: 👍/👎 on the daily brief and briefings tunes topics via memory | CT | ChatGPT Pulse | Improves relevance over time | S |
| C10 | **One-tap unsubscribe** via List-Unsubscribe (RFC 8058 one-click POST / mailto) | CT | Inbox Zero, Spark Gatekeeper | Inbox cleanup motivation | M. Making an HTTP POST to a URL taken from an untrusted email is a request-forgery and confirmation risk; mailto variant is safer |
| C11 | **Action log and verified receipts**: every outbound action (email sent, event created, reminder set) recorded from the tool result; `/log` shows what ClaudeBot actually did today; replies say "done" only from a successful tool result | PP, DG | Weak in competitors; OpenClaw criticised for false "done" | Pain #1 (reliability), trust concern #3 | S-M. One table written by tool runners; command plus brief line |
| C12 | **Reminders view**: `/reminders` lists every active reminder and scheduled task with next fire time and cancel buttons | PP | ChatGPT Tasks has a tasks page; users asked for one | Pain #1 visibility; today only briefings have a list | S |
| C13 | **Drafts-only mode**: a /settings switch that saves emails as Gmail drafts instead of sending | PP, UA | Fyxer, Superhuman "AI drafts, you send" | Pain #2 (fear of sends); lowers the trust bar for new users | S. Outbox path calls create_draft |
| C14 | **Life-admin radar**: the classifier flags bills with due dates, renewals, deliveries and travel changes, and offers a "remind me" button | PP, CT | Edison, EasilyDo, Poke (flight changes) | Pain #14 (demand thinly evidenced) | M. Classifier schema fields plus reminder creation behind a tap |
| C15 | **Birthdays and keep-in-touch**: reminders from Google Contacts birthdays or remembered dates | PP | Dex, Mob, OpenClaw CRM skill | Pain #15 (thin evidence) | M. Contacts needs a new OAuth scope and re-consent; memory-based variant needs none |
| C16 | **Security self-check in /status**: file permissions of .env, token and DB; OAuth scopes; owner pinned; budget set | DG | None found | Trust concern #2 (exposed self-hosted instances); markets the security lead | S |
| C17 | **Reactions as quick actions**: react 👍 to an alert to archive it, ✅ to a reminder to mark it done | PC, PP | Poke understands reactions (delight #4) | Native-feeling; fewer taps | S-M. `message_reaction` updates; needs a mapping from message to item |
| C18 | **Weekly "what I did for you"** recap: emails handled, reminders kept, time saved | DG | Lindy and OpenClaw dashboards (weak) | Retention and trust | S, builds on C11 |
| C19 | **Owner-configured MCP connectors** (Todoist, Notion, ...) via the Claude API MCP connector | CT, PC | Poke, OpenClaw, Lindy, ChatGPT/Claude connectors | Extensibility; but OpenClaw's marketplace is a security cautionary tale | M. Untrusted tool output must be fenced; no marketplace |
| C20 | **Concise by default**: shorter default answers and no preamble, tuned in the system prompt | PP | Claude praised as already concise | Pain #8 | XS. Prompt change; risk of losing helpful detail |

Platform-derived candidates (from `traces/literature/platform.md`):

| # | Idea | Lens | prior_work | so_what | effort_note |
|---|---|---|---|---|---|
| C21 | **Telegram Business: DM triage and reply-as-me.** The owner connects ClaudeBot to their personal Telegram account (Settings → Business → Chatbots). ClaudeBot summarizes incoming DMs and drafts replies, which go out from the owner's account only after a tap. | PC | Poke and Martin text on your behalf; OpenClaw runs in your chats | Delivers the owner's very first ask ("text people for me") on a channel with an API; Telegram Premium no longer required (Bot API 10.0) | M-L. `business_connection`/`business_message` handlers (PTB 22.8 supports them); every incoming DM is untrusted and must be fenced; the owner's own outgoing messages must never be read as commands; 24h reply window |
| C22 | **Incremental inbox checks with Gmail `history.list`.** Fetch only what changed since the last check instead of searching the last 2 days every 10 minutes. | PC, PP | Standard Gmail sync pattern | Cuts API calls; could allow faster checks at the same cost | S-M. Store historyId; fall back to search when it's too old |
| C23 | **Google Tasks sync** for lists and reminders | PC | Gemini, Google Assistant | Reminders show up in Google apps | M. New `tasks` scope means the owner must re-consent |
| C24 | **Message Batches for scheduled briefings** (half price) | PC, PP | none found | Cost (pain #3) | M. Batches are asynchronous (minutes to hours), which clashes with timed delivery; would need pre-generation |
| C25 | **Guest mode**: summon ClaudeBot in any chat | PC | Grok-style tagging | Reach | M. Replies are visible to everyone in that chat; must be web-only like group mode |
| C26 | **Stop button on streaming replies** (Bot API 10.3) | PC | ChatGPT/Claude apps | Control over long answers | S-M. PTB lacks it; would need raw `do_api_request` calls against an API the SDK can't type-check |
| C27 | **Voice notes** (speech-to-text) | PP | Poke, Meta AI | Delight #4 | **Dropped (objective):** neither the Claude API nor the Bot API offers speech-to-text, and BRIEF.md forbids other paid services. Misleading "voice notes" copy was removed from /help and the landing page. |
| C28 | **Calendar free/busy** (`freebusy.query`) | PC | | Merged into C6 (find-a-time) | |

## Triage (reviewer)
(pending)

## Chosen features
(pending)

## Backups and eliminated
(pending)
