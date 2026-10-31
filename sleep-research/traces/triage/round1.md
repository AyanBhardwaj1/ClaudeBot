# Triage, round 1

## Prompt

You are a skeptical senior product reviewer, triaging feature ideas for a product you did not build. Read these files yourself; they are your only context:
- /home/user/ClaudeBot/sleep-research/BRIEF.md (the product, its security model, constraints, non-goals)
- /home/user/ClaudeBot/sleep-research/IDEA_REPORT.md (the market landscape and the annotated candidate pool C1-C28)
- The evidence: /home/user/ClaudeBot/sleep-research/traces/literature/competitors.md, user_needs.md, platform.md
- Optionally skim the code in /home/user/ClaudeBot/claudebot/ (especially inbox_watch.py, tools.py, bot.py, setup_chat.py) to check what already exists and how hard each idea really is.

Task: for each candidate, make the strongest case both ways:
- the best case FOR it: what would make it the feature users talk about;
- the strongest objection;
- the most likely failure mode (cost blowup, noise, security, accuracy);
- whether the prior_work note is a real problem or just validation of demand.

Then rank by expected user value per unit of effort, within one implementation session (one engineer, about a day, test-first, offline fakes only). Name the 4-6 features you would build NOW, as a coherent release. At least one pick must be the highest-upside idea even if risky, with what would convince you it worked. Name 3-4 cheap quick wins worth bundling in too.

Check the evidence quality: the research reports flag that most claims rest on search snippets and vendor pages. Discount accordingly, and say where the evidence is thin.

Rank; do not rewrite ideas. Answer each objection or record it as a named risk; never absorb it by adding modules. Flag any pick that conflicts with the security model in BRIEF.md (owner-only, untrusted text fenced, no unattended sends, no new paid services) and say what minimal constraint would make it safe.

=== SCOPE LIMITS (these bound what you PROPOSE, never what you look for) ===
Report anything that is actually wrong, including a rare case if this project actually produces it. Then keep fixes in scope:
1. This is a product, not a security research project. Verification is welcome; over-defense is not.
2. Do not propose hashing, fingerprinting, or digest-binding schemes.
3. No speculative machinery (flags, compat layers, wrappers, frameworks) unless you can point to a current defect it fixes.
4. No corner-case obsession unless you can show the case arises here.
5. A clear sentence beats a scored checklist nobody maintains.
Say plainly when something is correct. Do not manufacture findings.

Write your full triage to /home/user/ClaudeBot/sleep-research/traces/triage/round1.md, starting with a copy of this prompt under a "## Prompt" heading, then "## Response". Do not modify any other file. Return: the ranked pick list (build now, quick wins, backups, do not build), with one line of reasoning each.

## Response

### 1. Verdict in one paragraph

Build a "tells you first, and you can check it" release: **C2 reply tracking**, **C1 heartbeat** (the high-upside, risky pick), **C6 find-a-time** and **C12 /reminders**, with **C13 drafts-only**, **C7 snap-to-calendar as copy only**, and a fix for **silent inbox-watcher failures** (defect D1) bundled as quick wins. **C21 Telegram Business** has the most upside in the pool. It is too large to do safely alongside the rest in one session, so it should headline the next one. Most of the pool's demand evidence is vendor positioning. The two best-evidenced user pains, reliability (#1) and drafts that don't sound like me (#5), are served here by C12, the D1 fix and (as backup) C4. Neither of those is the flashiest idea.

### 2. Evidence quality (discount applied throughout)

- **No page was read in full** for competitors.md or user_needs.md. Every quote is a search-snippet paraphrase. Reddit comes through a mirror whose post-to-claim mapping is unverified. Treat all "quotes" as near-verbatim at best.
- **Most "frequency" counts are supply, not demand.** The C5 note "9 products ship labels" counts vendors marketing a feature, not users asking for it. The same applies to C2 (follow-up tracking: vendor help pages only), C14 (life admin: demand explicitly UNVERIFIED), C15 (birthdays: UNVERIFIED) and C8 (lists: product positioning).
- **Strongest user-voice evidence:** reliability and false "done" (pain #1). It has several independent sources: Tom's Guide, the OpenAI forum and two dev.to reviews. Cost blowup (#3) has press figures (Notebookcheck, c't). Voice-matched drafts (#5) have direct Product Hunt and G2 user quotes. These are the claims I trust.
- **Proactivity (C1) is rated "#1 competitor gap" on thinner evidence than the label suggests.** It rests on one Product Hunt review thread of Poke, a mirrored Reddit "alarm clock" quote and vendor launches. The guidance that 3-5 pings a day is healthy comes from OpenClaw community docs. user_needs.md §9 says plainly that it found no user complaint about too many pings. I believe users like proactivity in principle. What they want it to say is unknown.
- **platform.md is the strongest file.** Claude docs and GitHub were fetched directly, and the PTB, anthropic and Google SDK surfaces were checked in the installed packages. Telegram and Google behaviour claims (Business without Premium, reaction delivery in private chats, Testing-mode token expiry) still come from snippets.
- **Factual error that ran through the pack (D4):** IDEA_REPORT's "Where ClaudeBot already leads" lists **voice**, and competitors.md (matrix row 22, "ClaudeBot strengths") and user_needs.md ("Already covered: Telegram-native voice notes") count voice notes as a strength. BRIEF.md says voice notes are NOT supported, and `bot.py:740-744` replies "I can't listen to voice notes yet". C27 is correctly dropped, but the landscape text should be fixed.
- **Some so_what claims are wrong when checked against the code.** C22's "cuts API calls / faster checks at the same cost" doesn't hold: Gmail API calls are free, and the Claude classifier already runs only on fresh, unseen mail (`inbox_watch.py:131-138`), so polling more often doesn't add Claude cost. C20 is already implemented: the system prompt says "Be brief", and `/mode brief` exists.

### 3. Defects found while checking the code (real today, in scope)

- **D1. Background inbox failures are silent to the owner.** `bot.py:869-877` `_inbox_job` catches every exception and only logs it. `GoogleNotConnected` is logged once. If the Google token stops refreshing (the owner skipped "Publish app" in `CLIENT_STEPS`, so the 7-day Testing expiry applies; or access was revoked), inbox alerts stop and nothing tells the owner. This is pain #1 ("silent failures") happening in this product. Minimal fix: tell the owner once when the check starts failing and once when it recovers, using fixed bot text. About 30 minutes. Bundled below.
- **D2. `list_calendar_events` silently truncates at 25 events.** `google_services.py` `list_events(max_results=25)`, and the tool schema can't raise the limit. On a busy week, "when am I free?" is answered from a partial list and can propose slots that are taken. C6 (freebusy) fixes this for availability. Exposing `max_results` fixes the listing.
- **D3. Unattended turns can destroy owner data.** The daily brief and scheduled tasks run with `owner_present=False`, yet `modify_email` (including `trash`), `update_calendar_event`, `delete_calendar_event` and `forget` have no `_require_owner` (`tools.py:_dispatch`). These are not "sends": `events.patch` and `delete` pass no `sendUpdates`, so attendees aren't notified, and the system prompt tells the model email is data. It is still an injected-email path with nobody watching, and the codebase already gates `remember` and `run_as_task` for exactly that reason. It only matters more if new unattended *agent* turns are added (C1, C3 built as agent turns). Minimal fix if those land: `_require_owner` on trash, delete and update, the same one-liner pattern. Not needed if C1 stays a no-tools structured call, as recommended below.
- **D4.** The voice-notes error in the research pack (above).
- **D5. The system prompt over-claims "label emails"** (`agent.py:45`). `modify_email` can only star or mark important; it has no custom labels. Small, but it invites the false "done" that pain #1 is about. One-word fix, or C5 makes it true.

What is correct, said plainly: email sends already have verified receipts (outbox cards are edited to Sent, Failed or Cancelled by the bot, not the model). There is no inbound port anywhere: long polling, and no ports in fly.toml or docker-compose. So OpenClaw's "exposed gateway" failure, the main evidence behind C16, does not apply here. Untrusted fields in alerts are clipped and fenced, and classifier output ids are checked against the input (`inbox_watch.py:_classify`, `by_id.pop`). New features should copy that pattern.

### 4. Per-candidate cases

Effort is in engineer-hours, test-first with fakes. "Prior work" says whether the prior_work note is a real problem (a free platform feature, or a cautionary tale) or validation of demand.

**C1 Heartbeat** (build now; the high-upside pick)
- For: "It texted me that my 9am clashes with the dentist and that Sam never answered" is the moment users screenshot. It turns ClaudeBot from cron into judgment, which is what Poke is praised for. Competing versions (Gemini Spark, ChatGPT Pulse) sit behind $100-$250 plans.
- Objection: ClaudeBot already has event-driven inbox alerts and a daily brief (competitors matrix row 8 is "P", not "N"). A heartbeat that repeats them is pure noise, so the real gap is narrower than "#1".
- Failure mode: **noise and duplication, not cost.** At the project's own Haiku price (`usage.py`: $0.10/$0.50 per MTok), a snapshot of about 3k input and 300 output tokens costs about $0.0005 a run. Six runs a day is under $0.10 a month, and even 10x is $1. OpenClaw's blowup came from Opus every 5 minutes. Accuracy risk: "deadlines mentioned in email", judged from snippets, is the signal most likely to give false positives. If it misfires, drop that signal first. Named risk.
- Security: it conflicts with the model **if built as an agent turn**, because it adds another unattended path with trash and delete tools (D3). Minimal constraint: a single structured-output Haiku call with no tools, like `InboxWatcher._classify`. Inputs are clipped and fenced; output may only reference item ids present in the snapshot; actions are buttons that route to existing owner-tap flows (`mail:draft`, `mail:later`). No unattended sends follow from that.
- Prior work: validation, plus a price wedge.
- Effort: about 3h with C2 as an input (calendar snapshot, change check, daily cap, quiet hours already in `in_quiet_hours`, source="heartbeat" in the tracker).
- What would convince me it worked (single-owner dogfood, 14 days): median of 3 or fewer pings a day; at least 40% of pings get a tap or reply within 2 hours; the owner has not switched it off; zero pings repeat an item already sent that day as an inbox alert or in the brief; `/usage` shows heartbeat spend under $0.50 for the month. If the tap rate is under about 20%, it is noise. Cut it back to C2-only nudges.

**C2 Reply tracking + Nudge** (build now)
- For: concrete and checkable: "Priya hasn't replied to your Tuesday email (4 days). Nudge?" One tap drafts a follow-up, and the existing draft flow (`buttons.py` `mail:draft`) plus the outbox handle the rest. Every email client has it; nobody delivers it in a messenger.
- Objection: most sent mail expects no reply (thanks, FYIs, receipts, lists), so naive "no reply in N days" floods the list.
- Answer and residual risk: judge "expects a reply" on the owner's last sent message with a small structured Haiku call. Decide "last message is mine" from Gmail's `SENT` label on the thread's last message, not from From-address matching (aliases break that). Residual false positives are a named risk; cap the list.
- Failure mode: noise (above), and accuracy on threads with several recipients. Cost is negligible: Gmail calls are free, and one Haiku call per new sent thread.
- Security: thread subjects and snippets, and quoted text inside the owner's sent mail, are untrusted. Clip and fence them as in inbox_watch. The Nudge is an owner tap into an owner-present turn, so the send keeps the undo window. Fine.
- Prior work: validation. Gemini AI Inbox to-dos are partial and live inside Gmail.
- Effort: about 3h (thread metadata fake, `/waiting`, Nudge button, and a hook for C1).
- Evidence: vendor help pages plus one mirrored Reddit wish. Directional, but four or more vendors converging independently is a reasonable signal.

**C3 Meeting prep briefs** (backup)
- For: "Before your 2pm: Dana Wu, CFO at Acme; last thread was her pricing objection on the 12th." That feels like magic for founders and sales, and suits students' office hours too.
- Objection: most calendar events are recurring internal meetings or solo blocks, so the value is limited to a subset of users. Briefs on internal standups are noise.
- Failure mode: accuracy (an invented "who they are" when email history is thin, or from web search on a common name), plus noise. It runs unattended.
- Security: if built as an agent turn it exercises D3. Minimal constraint: read-only tools or a structured call. Web-searching attendee names sends their names to the search provider; acceptable for one owner, but it should be stated.
- Prior work: validation (Brief My Meeting, Fireflies), with vendor-only evidence.
- Effort: about 3h. Better as a C1 signal next release.

**C4 Writes in your voice** (backup #1; first in line if time remains)
- For: the best-evidenced email pain: "Vanilla AI drafted emails are all terrible" is a real Product Hunt quote. It improves every draft, including C2 nudges.
- Objection: ClaudeBot drafts on demand a few times a week, not hundreds, so the gain is hard to see. Gmail's free Suggested Replies is "closer to your voice", and Spark learns style from 3 samples.
- Failure mode: **security and accuracy.** Sent mail contains quoted third-party text, and a style guide built from it and injected as a persistent system message is a durable instruction plant. Minimal constraint: strip quoted blocks before analysis; produce structured, length-capped style fields; the owner reviews them in `/style` before they are used; inject them as data, not as owner instructions.
- Prior work: partly a real problem (a free platform feature), partly validation.
- Effort: about 2-3h.

**C5 Plain-English inbox rules and labels** (backup)
- For: the most-shipped email feature; "anything from my landlord is urgent" also sharpens alerts.
- Objection: half of it exists. Memories already feed the alert classifier ("What I know about {owner}" in `_classify`), so "remember my landlord is urgent" works today. Labels matter only to people who live in Gmail, and ClaudeBot users live in Telegram.
- Failure mode: accuracy (misapplied labels across the whole inbox).
- Security: label creation is a write, so owner-confirmed, as the note says. Fine.
- Prior work: a real problem (crowded and commoditized: Gmail, Superhuman, Shortwave).
- Effort: M (about 4h).

**C6 Find-a-time** (build now)
- For: "Propose three times to Priya next week" gives correct slots in a ready draft. LLMs are unreliable at interval arithmetic, and a deterministic slot finder is fully testable offline.
- Objection: Opus can already read `list_calendar_events` and do it.
- Answer: not correctly on busy weeks, because of D2's silent 25-event cap. This fixes a real wrong-answer path.
- Failure mode: accuracy at the edges: all-day events, time zones, assumed working hours, and other calendars not in primary (named risk: shared work calendars are ignored).
- Security: read-only, and drafts go through the existing outbox. Fine.
- Prior work: validation (Gemini Help me schedule is paid and US-only).
- Effort: about 1.5h (`freebusy.query` under the existing `calendar` scope).

**C7 Snap-to-calendar** (quick win, copy only)
- For: forwarding a flyer and getting an event is the life-admin "aha".
- Objection: it already works. Photo or PDF goes through the Files API to the agent and on to `create_calendar_event` in an owner-present turn, and WELCOME already suggests "(send a PDF or photo) what's due in this?". A confirm-card flow isn't needed: in an owner-started turn without attendees, the owner asked for it. Attendee invites already require the owner (`tools.py`).
- Failure mode: wrong date or time pulled from the image (accuracy). The event reply shows it, and the owner can fix it.
- Prior work: validation.
- Effort: about 20 minutes for one test that proves the path, plus an "add this to my calendar" line in /help. Don't build a flow.

**C8 Lists** (backup)
- For: daily-use stickiness ("add oat milk").
- Objection: demand evidence is product positioning only. Memory and reminders cover most of it, and Telegram's native checklists need a business connection (platform.md), so the result is an inline-keyboard imitation.
- Failure mode: low use. Prior work: validation for WhatsApp bots, unproven for this audience.
- Effort: about 3h.

**C9 Brief feedback** (later)
- For: the brief gets better over time.
- Objection: one thumbs-down on a whole brief carries almost no information. Pulse's thumbs are per card, and ClaudeBot's brief is one free-text message, so this would produce vague memories ("owner disliked today's brief").
- Failure mode: memory pollution (pain #6, over-recall). Prior work: validation from a single product.
- Effort: S, but the value is low.

**C10 One-tap unsubscribe** (do not build)
- For: satisfying inbox cleanup.
- Objection: Gmail already shows its own Unsubscribe link on bulk mail.
- Failure mode and security conflict: a one-click POST to a URL taken from an untrusted email, made from the owner's server, is an attacker-chosen outbound request. It can hit the owner's LAN and confirms the address is live. The mailto variant is a send, so it needs a tap through the outbox.
- Prior work: a real problem (the platform does it for free).

**C11 Action log and verified receipts** (backup #2)
- For: pain #1 has the best evidence, and "/log: what I actually did today" is the trust feature. It becomes more valuable once C1 ships.
- Objection: the false-"done" evidence is about OpenClaw skills. ClaudeBot's email path already has bot-authored receipts, and tool errors come back as `is_error`. The uncovered writes are calendar and reminders, a smaller hole.
- Failure mode: a log nobody opens.
- Prior work: validation (competitors are weak here).
- Effort: about 2h. D1, bundled below, is the cheapest slice of the same promise.

**C12 /reminders view** (build now; also a quick win)
- For: visibility is the documented ChatGPT Tasks complaint ("dedicated reminders page"). It is deterministic, costs no model call, and still works when the budget cap blocks chat (`BudgetExceeded`), which is exactly when the owner wants to check.
- Objection: the `list_reminders` tool already lets the model answer.
- Answer: it costs a model call and can't offer cancel buttons. `/briefings` already has the exact pattern (`bot.py:805-833`).
- Failure mode: none worth naming. Copy the owner check from `on_briefing_cancel` and cap the buttons.
- Prior work: validation. Effort: about 1h.

**C13 Drafts-only mode** (quick win)
- For: lowers the trust bar for nervous new owners (pain #2 is well evidenced in tone).
- Objection: the undo window and tap-to-send already answer pain #2, so this mostly duplicates protection.
- Failure mode: the owner forgets it is on and believes mail went out. The tool result must say "saved as a draft, not sent (drafts-only mode)", and the system prompt's "send it, then confirm" must not paper over that. Named risk.
- Prior work: validation. Effort: about 45 minutes (an outbox branch plus a FIELDS entry).

**C14 Life-admin radar** (later)
- For: "Your Comcast bill is due Friday, remind me?" is useful.
- Objection: demand is explicitly UNVERIFIED (product positioning only), and the classifier deliberately suppresses receipts and shipping mail today.
- Failure mode: accuracy (wrong amounts or dates) and noise.
- Prior work: validation (Edison, EasilyDo). Revisit as a C1 signal.

**C15 Birthdays and keep-in-touch** (do not build now)
- For: warm, personal.
- Objection: thin evidence, a new Contacts scope with re-consent, and the memory-based variant mostly duplicates `set_reminder` with `repeat`. No yearly repeat exists, though, so it would need one.
- Prior work: validation of a niche.

**C16 Security self-check in /status** (backup, low)
- For: markets the security lead.
- Objection: its evidence is exposed OpenClaw gateways, and ClaudeBot opens no inbound port. The wizard already chmods `.env` and the token to 600. Little would ever show red.
- Failure mode: a green checklist that reassures without protecting.
- Prior work: none found. That reflects low demand, not an opening. Effort: about 1h.

**C17 Reactions as quick actions** (do not build now)
- For: native feel.
- Objection: whether owner reactions in a private chat reach the bot is UNVERIFIED (platform.md), and an offline fake can't settle it. You could ship a feature that never fires.
- Prior work: validation (Poke), but the platform is uncertain.

**C18 Weekly recap** (do not build)
- For: retention.
- Objection: "time saved" would be an invented number, which is the hallucinated-summary pain (#11) in a trust feature. It also depends on C11.

**C19 Owner-configured MCP connectors** (do not build)
- Objection and security conflict: MCP servers must be reachable by Anthropic, most hosted ones are paid third-party services (BRIEF forbids those), and their tool output is untrusted. The tool list is also fixed for the process lifetime by design (`tools.py` docstring).
- Prior work: a real problem (the OpenClaw marketplace is the cautionary tale).

**C20 Concise by default** (nothing to build)
- Already done: `agent.py` says "Be brief: this is a chat on a phone", and `/mode brief` exists. Any further cut risks losing useful detail.

**C21 Telegram Business: DM triage and reply-as-me** (backup; headline of the next session)
- For: the biggest upside in the pool. ClaudeBot's users live in Telegram, and no competitor triages their Telegram DMs. "Three people messaged you; your landlord needs an answer today [Draft reply]" sent from the owner's own account is something only this product can do. The PTB 22.8 surface was checked locally.
- Objection: it is a new inbox of untrusted text from everyone the owner knows, flowing into an assistant with Gmail access. It is too much security surface to rush next to C1 and C2 in one day.
- Failure mode: security and privacy. Friends' messages go to the Claude API, which the owner must be told. The 24-hour reply window confuses users.
- Load-bearing unverified fact: Business no longer needs Premium. That rests on a SendPulse snippet and the PTB 10.0 checklist.
- Security constraints that make it safe: (a) accept a `business_connection` only when its user is the owner; (b) fence all `business_message` text, and never route it, including the owner's own outgoing messages, to command or agent handlers as owner input; (c) replies only on a tap, through `business_connection_id`; (d) **no automatic `readBusinessMessage`**: read receipts are a visible action toward third parties.
- Prior work: validation (Poke and Martin on other channels). Effort: 5-6h on its own.

**C22 Gmail `history.list`** (do not build)
- Objection: the so_what is wrong (see §2). Gmail calls are free, and Claude already sees only fresh mail. The current search plus `seen_emails` design is correct.

**C23 Google Tasks sync** (do not build now)
- Objection: a new sensitive scope with re-consent, and `due` keeps the date only, so timed reminders stay in the bot anyway. Prior work: a real problem (Google's own apps).

**C24 Message Batches** (do not build)
- Objection: briefings cost cents. Batches are asynchronous (minutes to hours), so on-time delivery would need pre-generation machinery to save maybe a dollar a month.

**C25 Guest mode** (do not build)
- Objection and security conflict: replies are visible to the whole chat. Group mode already covers the web-only case.

**C26 Stop button** (do not build)
- Objection: PTB 22.8 lacks it, the payload name is UNVERIFIED (third-party changelogs only), and it can't be verified offline.

**C27 Voice notes**: the drop is correct (no speech-to-text in the allowed APIs). Fix the leftover "voice" claims in the research pack (D4).

**C28 Free/busy**: the merge into C6 is correct.

### 5. Ranking (user value per unit of effort, one session)

| Rank | Pick | Tier | Effort | One line |
|---|---|---|---|---|
| 1 | C2 Reply tracking + Nudge | Build now | ~3h | Deterministic core, reuses the draft button and outbox, demand converges across vendors; noise is the named risk. |
| 2 | C12 /reminders | Build now (quick) | ~1h | Fixes the best-evidenced pain (visibility/reliability) for no model cost, and works when the budget is hit. |
| 3 | C6 Find-a-time | Build now | ~1.5h | Correct slots instead of LLM arithmetic over a list that silently truncates at 25 (D2). |
| 4 | C1 Heartbeat | Build now (high upside) | ~3h | The feature people talk about if it stays quiet; a no-tools Haiku call costs under $0.10 a month; noise is the risk. |
| 5 | D1 fix: tell the owner when inbox checks fail or recover | Quick win | ~0.5h | A real silent failure in this product today. |
| 6 | C13 Drafts-only | Quick win | ~0.75h | Cheap trust lever for new owners; the tool result must say "not sent". |
| 7 | C7 Snap-to-calendar | Quick win (copy + one test) | ~0.3h | Already works; make it discoverable instead of building a flow. |
| 8 | C4 Voice style | Backup 1 | ~2.5h | Best-evidenced email pain; needs quote-stripping and owner review of the style guide first. |
| 9 | C11 Action log | Backup 2 | ~2h | Worth more after C1 ships unattended work; email receipts already exist. |
| 10 | C21 Telegram Business | Backup / next headline | ~5-6h | Highest upside in the pool; deserves its own session for the four constraints above. |
| 11 | C3 Meeting prep | Backup | ~3h | Strong for a segment; better as a heartbeat signal. |
| 12 | C5 Rules + labels | Backup | ~4h | Half exists via memories; crowded category. |
| 13 | C8 Lists | Backup | ~3h | Stickiness unproven for this audience. |
| 14 | C16 Security self-check | Backup (low) | ~1h | Its threat (exposed ports) doesn't apply here. |
| 15 | C9 Brief feedback | Later | S | Whole-brief thumbs carry too little signal. |
| 16 | C14 Life-admin radar | Later | M | Demand unverified; revisit as a heartbeat signal. |
| 17 | C15 Birthdays | Don't build now | M | Thin evidence; new scope. |
| 18 | C17 Reactions | Don't build now | S-M | Delivery in private chats unverified and untestable offline. |
| 19 | C23 Google Tasks | Don't build now | M | Re-consent cost; date-only due dates. |
| 20 | C18 Weekly recap | Don't build | S | "Time saved" would be made up. |
| 21 | C22 history.list | Don't build | S-M | Saves free Gmail calls only. |
| 22 | C24 Batches | Don't build | M | Pennies saved against timing complexity. |
| 23 | C26 Stop button | Don't build | S-M | SDK lacks it; payload unverified. |
| 24 | C10 Unsubscribe | Don't build | M | Outbound request to a URL from untrusted mail; Gmail does it already. |
| 25 | C19 MCP connectors | Don't build | M | Paid services, untrusted output, fixed tool list. |
| 26 | C25 Guest mode | Don't build | M | Public replies leak; group mode covers it. |
| 27 | C20 Concise | Done already | — | System prompt plus /mode brief. |
| — | C27 / C28 | Dropped / merged | — | Both correct. |

Session budget: the build-now items plus quick wins come to about 9-10 hours, which is a full day. Cut order if the day runs long: C7, then C13, then C6. Do not ship C1 without C2. If C2 isn't done by the midpoint, C1 moves to backup and the release is C2, C12, C6 and the quick wins.

### 6. Security flags on the picks

- **C1:** conflicts only if built as an agent turn (D3). Constraint: one no-tools structured call; output ids are checked against the snapshot; actions are owner taps into existing flows.
- **C2:** safe if snippets and quoted text are clipped and fenced as in inbox_watch, and the Nudge goes through the owner-tap draft flow and the outbox.
- **C6, C12, C7, C13, D1:** no conflict. C12 and D1 send only bot-authored text, with the owner check on callbacks.
- **Backups:** C4 needs the quote-strip and owner-review constraint. C21 needs constraints (a) to (d). C3 needs to be read-only when unattended.
