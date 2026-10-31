# Platform capabilities scan, 2025-2026 (Telegram, Claude API, Google)

Date: 2026-10-31. Scope: new platform capabilities that could unlock ClaudeBot features, with exact API names, whether the installed SDKs expose them, and sources.

Installed versions, checked locally:
- `python-telegram-bot` **22.8**. `telegram.__bot_api_version__ == "10.0"`. 22.8 is still the latest PTB release (12 Jun 2026) [T5]. The master README says "All types and methods of the Telegram Bot API **10.0** are natively supported" [T4].
- `anthropic` **1.15.0**. Python SDK **2.0.0** shipped 2026-10-21, sends API version `2026-10-21` by default, and has breaking changes plus an MIT to Apache-2.0 licence change [C1, C24]. 1.15.0 still sends the older API version.
- `google-api-python-client` **2.201.0**. Its bundled discovery documents (`.venv/lib/python3.13/site-packages/googleapiclient/discovery_cache/documents/*.json`) are the local evidence for Google methods and scopes: gmail.v1 rev 20260727, calendar.v3 rev 20260708, tasks.v1 rev 20251102, people.v1 rev 20251117, drive.v3 rev 20260916, pubsub.v1 rev 20260915.
- ClaudeBot today uses `web_search_20260209`, `web_fetch_20260209`, `code_execution_20260521` with skills, `compact-2026-01-12`, `server-side-fallback-2026-07-01`, `output_config.effort` and `.format` (structured outputs), `cache_control`, citations, `send_message_draft`, and the scopes `gmail.modify` and `calendar` (from `claudebot/agent.py`, `tools.py`, `ui.py`, `google_services.py`).

Network caveat: this sandbox cannot reach `core.telegram.org`, `t.me`, `docs.python-telegram-bot.org` or `developers.google.com`. Claims attributed to those hosts come from search-result excerpts of those pages. Where the installed SDK confirms a claim, the local evidence is given as well. `platform.claude.com` and `github.com` were fetched directly.

---

## 1. Telegram Bot API (9.0 to 10.3)

### Release timeline

| Version | Date | Headline (exact names) | Source |
|---|---|---|---|
| 9.0 | 2025-04-11 | Business accounts 2.0: `BusinessBotRights`, `readBusinessMessage`, `deleteBusinessMessages`, `setBusinessAccountName/Bio/Username/ProfilePhoto`, gifts and Stars for business (`getBusinessAccountGifts`, `transferBusinessAccountStars`, `upgradeGift`), stories (`postStory`). Mini Apps get `DeviceStorage` | [T6, T15, T17] |
| 9.1 | 2025-07 | Checklists: `sendChecklist`, `editMessageChecklist`, `Checklist`, `InputChecklist`, `checklist_tasks_done` | [T6, T18] |
| 9.2 | 2025-08 | Suggested posts: `approveSuggestedPost`, `declineSuggestedPost`, `SuggestedPostInfo`; replies to checklist tasks | [T6] |
| 9.3 | 2025-12-31 | `sendMessageDraft` (streaming drafts), at first for bots in chats with topics | [T10] |
| 9.5 | 2026-03-01 | `sendMessageDraft` opened to all bots and all chats; `setChatMemberTag`; `date_time` entity | [T11, T12] |
| 9.6 | 2026-04-03 | Mini Apps `SecureStorage` | [T17] |
| 10.0 | 2026-05-08 | **Guest mode** (`guest_message`, `answerGuestQuery`, `SentGuestMessage`); bot-to-bot messaging; **managed bots** (`getManagedBotToken`, `ManagedBotCreated`, `KeyboardButtonRequestManagedBot`); **business bots no longer need Premium**; `getUserPersonalChatMessages`; live photos (`sendLivePhoto`); poll media; `deleteMessageReaction`; empty text allowed in `sendMessageDraft` | [T1, T13, T14, T16] |
| 10.1 | 2026-06-11 | **Rich Messages**: `sendRichMessage`, `sendRichMessageDraft`, `RichMessage`, `InputRichMessage`, ~26 `RichText*` and ~22 `RichBlock*` types (`RichBlockTable`, `RichBlockDetails`, `RichBlockThinking`, `RichBlockList` and others); join-request queries (`answerChatJoinRequestQuery`) | [T2] |
| 10.2 | 2026-07-14 | Ephemeral messages (`editEphemeralMessageText`, `deleteEphemeralMessage`, `ephemeral_message_id`); Communities; `InputMediaVoiceNote` in rich messages; Mini App origin enforcement | [T7, search excerpt of T6] |
| 10.3 | 2026-08-24 | No new methods. `sendMessageDraft` and `sendRichMessageDraft` gain `can_stop` and `keep_on_stop`; new update `MessageGenerationStopped`; `EphemeralMessageParameters`; `RichMessageButton`, `RichBlockDocument`, `DisabledKeyboardButton` | [T8, T9, T3] |

PTB status after 10.0: the 10.1 tracking issue #5261 is open, milestone v23, and maintainers have paused work for a refactor [T2]. A community PR for 10.3 (#5359) was closed without merging on 2026-09-16 [T3]. **Anything from 10.1 onward is not in PTB 22.8.** It can still be called with `Bot.do_api_request(endpoint, api_kwargs)`, which exists in 22.8 for forward compatibility (checked locally). Unknown update fields land in `Update.api_kwargs` (checked locally: `Update.de_json({"update_id":1,"message_generation_stopped":{...}})` puts the payload in `api_kwargs`).

### Capability table: Telegram

"PTB 22.8" gives the evidence from the installed package (`.venv/lib/python3.13/site-packages/telegram`).

| Capability | Exact API name | In PTB 22.8? (evidence) | User feature it would unlock |
|---|---|---|---|
| Business connection to the owner's personal account | Updates `business_connection`, `business_message`, `edited_business_message`, `deleted_business_messages`; `getBusinessConnection`; `BusinessConnection.rights` | **Yes.** `Update` slots include all four; `BusinessConnectionHandler`, `BusinessMessagesDeletedHandler`; `filters.UpdateType.BUSINESS_MESSAGE(S)` | **Telegram DM inbox triage**: the bot sees the owner's 1:1 Telegram chats (not groups), summarizes unread DMs in the daily brief, flags urgent ones and drafts replies. Since 10.0 the owner no longer needs Premium [T1, T13, T14]. One business bot per account [T14] |
| Business permissions | `BusinessBotRights`: `can_reply`, `can_read_messages`, `can_delete_sent_messages`, `can_delete_all_messages`, `can_edit_name/bio/profile_photo/username`, `can_change_gift_settings`, `can_view_gifts_and_stars`, `can_convert_gifts_to_stars`, `can_transfer_and_upgrade_gifts`, `can_transfer_stars`, `can_manage_stories` | **Yes.** `inspect.signature(BusinessBotRights)` lists all 14. Docstring: `can_reply` = "send and edit messages in the private chats that had incoming messages in the last 24 hours" | "Reply as me" with Send/Edit buttons (keeps the tap-to-send rule); mark as read after triage. The rights the owner grants decide what is possible. The 24-hour window means the bot can't start a conversation |
| Reply or act on the owner's behalf | `send_message(..., business_connection_id=)`, `readBusinessMessage`, `deleteBusinessMessages` | **Yes.** `Bot.read_business_message` docstring says it "Requires ... can_read_messages" | Approved replies go out from the owner's own account; "mark all as read" |
| Checklists | `sendChecklist`, `editMessageChecklist`, `InputChecklist`, `InputChecklistTask`, `Message.checklist_tasks_done/added` | **Yes**, but `send_checklist` requires a `business_connection_id` (the signature has no optional path) | Native tick-box to-do lists (packing lists, task breakdowns) sent as the owner into a chat. Only works over a business connection. Whether it can target the bot chat is [UNVERIFIED] |
| Guest mode | Update `guest_message`; `Message.guest_query_id`, `guest_bot_caller_user`, `guest_bot_caller_chat`; `answerGuestQuery` returns `SentGuestMessage`; `User.supports_guest_queries` | **Yes.** `Bot.answer_guest_query(guest_query_id, result: InlineQueryResult)`; `filters.UpdateType.GUEST_MESSAGE`. There is no dedicated handler class, so use `MessageHandler(filters.UpdateType.GUEST_MESSAGE & filters.User(owner))` | **@ClaudeBot in any chat**: the owner mentions the bot in a chat it never joined ("@bot when am I free Thursday?") and it answers there. The reply is **visible to everyone in that chat** [T16], so answers must be public-safe and limited to the owner. Guest mode is switched on in BotFather [T16] |
| Managed bots | `getManagedBotToken`, `replaceManagedBotToken`, `get/setManagedBotAccessSettings`, `KeyboardButtonRequestManagedBot`, `ManagedBotCreated`, update `managed_bot` | **Yes** (`ManagedBotUpdatedHandler`, `_managedbot.py` versionadded 22.8) | One-tap bot creation in setup, with no BotFather token copy-paste. It needs a central "manager" bot, which is hosted infrastructure the brief rules out. Low fit |
| Streaming drafts | `sendMessageDraft(chat_id, draft_id, text, ...)` | **Yes.** In 22.6, "Now all bots" in 22.7, `text` optional in 22.8. **Already used** in `claudebot/ui.py` | (in use) |
| Stop button on streams (10.3) | `sendMessageDraft(can_stop=, keep_on_stop=)` + update `message_generation_stopped` (`MessageGenerationStopped`) | **No.** Pass via `api_kwargs` and read `Update.api_kwargs`. `allowed_updates=Update.ALL_TYPES` does not list the new type, so it must be added by name. The exact field name and payload are [UNVERIFIED] (seen only in third-party changelogs [T8, T9]) | A native "Stop" control on long /research or /think streams that saves tokens and budget |
| Rich Messages (10.1) | `sendRichMessage`, `sendRichMessageDraft`, `InputRichMessage`, `RichBlockTable`, `RichBlockDetails`, `RichBlockThinking` | **No** (open issue #5261 [T2]). Use `do_api_request("sendRichMessageDraft", ...)` | Real tables for email lists and calendars, collapsible "Sources" and "Reasoning" sections, streamed with formatting intact |
| Ephemeral messages (10.2/10.3) | `EphemeralMessageParameters`, `editEphemeralMessageText`, `deleteEphemeralMessage` | **No.** Raw call; parameter names changed in 10.3 [T8] | Group mode can answer the owner privately inside a group (only the owner sees it), which fixes a leak risk in group mode |
| Reactions | `setMessageReaction`, update `message_reaction` (`MessageReactionUpdated`), `deleteMessageReaction` (10.0) | **Yes** (`MessageReactionHandler`). Docstring: "The bot must be an administrator in the chat". Whether owner reactions in a private chat arrive is [UNVERIFIED] | Instant acknowledgement (react 👀 while working, ✅ when done); thumbs-up or thumbs-down on answers as feedback |
| Inline mode | `answerInlineQuery`, `InlineQueryResultArticle`, `savePreparedInlineMessage`, `SwitchInlineQueryChosenChat` | **Yes** (`InlineQueryHandler`; `save_prepared_inline_message` present) | Write anywhere: type "@bot polite decline" in any chat to insert drafted text. Nothing is sent without a tap, so the security model holds |
| Mini Apps | `WebAppInfo`, `MenuButtonWebApp`, `answerWebAppQuery`, `savePreparedKeyboardButton` (10.0); JS `DeviceStorage` (9.0), `SecureStorage` (9.6) | **Yes** (server side). The web front end must be served over HTTPS, which Fly or Railway can do | Rich /settings, /memory and calendar views; budget dashboard |
| Personal-chat read | `getUserPersonalChatMessages(user_id, limit 1-20)` | **Yes** (`PersonalChatMessagesLimit.MAX_LIMIT == 20`) | Read the owner's profile-pinned personal channel. Low value |
| Voice and video notes | `sendVoice`, `sendVideoNote`, `Message.voice`; `InputMediaVoiceNote` (10.2, rich only) | **Yes** for send and receive. **No transcription method** exists in the Bot API (`grep -ri transcri telegram/` finds nothing) | Voice in still needs speech-to-text from somewhere. Note: `claudebot/bot.py:740` currently replies "I can't listen to voice notes yet", which contradicts the brief's "voice notes" line |
| Polls | `sendPoll` with `media`, `explanation_media`, `allows_revoting`, `members_only` (10.0) | **Yes** (signature checked) | Group mode: "make a poll for dinner times" from calendar free slots |
| Stories | `postStory`, `editStory`, `repostStory` | **Yes**, business only (`can_manage_stories`) | Low value for a personal assistant |
| Gifts and Stars, paid media | `sendGift`, `getUserGifts`, `getMyStarBalance`, `sendPaidMedia`, `sendInvoice` with XTR, `editUserStarSubscription` | **Yes** | None for a single-owner bot. Skip |
| Suggested posts | `approveSuggestedPost`, `declineSuggestedPost` | **Yes** | Channel feature. Not relevant |

**Security note (checked in code):** every ClaudeBot handler gates on `filters.UpdateType.MESSAGE` (`claudebot/bot.py:265-312`). PTB's base `UpdateFilter` also matches `business_message` and `guest_message` (`ext/filters.py:268-299`), but `UpdateType.MESSAGE` does not, so today these updates are silently ignored even though `run_polling(allowed_updates=Update.ALL_TYPES)` receives them. That is the right default. Adding business or guest features needs new, dedicated handlers that fence third-party text as untrusted. They also need care with the owner's own outgoing business messages: those have `from_user == owner`, but they are not commands to the bot.

---

## 2. Claude API (2025-2026)

Sources were fetched directly from `platform.claude.com/docs/en/...`. SDK evidence comes from `.venv/lib/python3.13/site-packages/anthropic`.

| Capability | Exact API name | Status | In SDK 1.15.0? (evidence) | User feature it would unlock |
|---|---|---|---|---|
| Web search, newest | `web_search_20260318` (adds `response_inclusion: "excluded"`); `web_search_20260209` (dynamic filtering) | GA [C2] | **Yes**: `types/web_search_tool_20260318_param.py`; in `ToolUnionParam` | Cheaper /research: drops raw search blocks that code execution already consumed. Bot uses 20260209 today |
| Web fetch, newest | `web_fetch_20260318` (`response_inclusion`), `web_fetch_20260309` (`use_cache: false`) | GA [C3] | **Yes**: `web_fetch_tool_20260318_param.py` | "Fetch fresh" for live pages (prices, status pages) |
| Code execution | `code_execution_20260521` (in use), `code_execution_20260120` (programmatic tool calling) | GA, no beta header [C4] | **Yes**: four versions in `ToolUnionParam` | (in use) |
| Programmatic tool calling | custom tool `allowed_callers: ["code_execution_20260120"]` | GA [C11] | **Yes**: `ToolParam` has `allowed_callers` | "Summarize my 200 unread newsletters": Claude loops `search_emails` and `read_email` in code without filling context |
| Tool search | `tool_search_tool_regex_20251119`, `tool_search_tool_bm25_20251119`, tool `defer_loading: true` | GA [C10] | **Yes**: `ToolParam.defer_loading`, both types present | Keeps the prompt small as tools grow (Tasks, Contacts, Drive, business tools) |
| Memory tool | `memory_20250818`; helper `BetaAbstractMemoryTool` / `BetaAsyncAbstractMemoryTool` | GA [C5] | **Yes**: `types/memory_tool_20250818_param.py`; `anthropic.lib.tools.BetaAbstractMemoryTool` | File-style long-term memory the model curates itself, backed by SQLite. ClaudeBot already has its own `remember` and `forget` tools, so the gain is small |
| Memory stores and dreams (Managed Agents) | `client.beta.memory_stores.*` (`agent-memory-2026-07-22`), `client.beta.dreams` (`dreaming-2026-04-21`, research preview) | Beta [C22, C1] | **Yes**: `resources/beta/memory_stores`, `dreams.py` | "Nightly memory tidy" (merge duplicates, drop stale facts). Tied to Managed Agents sessions. Low fit for self-hosted |
| MCP connector | `mcp_servers=[{type:"url",...}]` + `{"type":"mcp_toolset"}`; betas `mcp-client-2025-11-20`, `mcp-client-2026-09-15` | Beta [C6] | **Yes**: `beta.messages.create(mcp_servers=...)`, `BetaMCPToolsetParam` | Plug in any remote MCP server (Notion, Todoist). The server must be reachable by Anthropic, and most hosted MCP servers are paid third-party services, which the brief rules out |
| Computer use and browser use | `computer_toolset_20260801` (GA 2026-08-19), `browser_toolset_20260801` | GA (computer use); browser use launched 2026-08-19 [C7, C8, C1] | **Yes**: both toolset params plus all `browser_*` blocks | Driving a browser on the user's host: book or fill forms. Heavy, and risky against the security model. Not recommended |
| Text editor | `text_editor_20250728` | GA [C9] | **Yes** | Not needed |
| Advisor tool | `{"type":"advisor_20260301","name":"advisor","model":...}`, beta `advisor-tool-2026-03-01` | Beta [C21] | **Yes**: `BetaAdvisorTool20260301Param` | Haiku 5.5 runs triage and briefs and consults Opus 5.5 only on hard cases. A cost lever for the budget cap |
| Files API | `client.files.upload/list/download/delete` | GA since 2026-08-19 [C12, C1] | **Yes**: `client.files` (non-beta) | (in use per brief) |
| Agent Skills | `client.skills.*`, `container={"skills":[...]}` | GA since 2026-08-19 [C13] | **Yes**: `client.skills.create/list/versions` | Custom skills, for example a "ClaudeBot email style" skill |
| Compaction, threshold | `context_management.edits: [{"type":"compact_20260112"}]`, beta `compact-2026-01-12` | Beta [C15] | **Yes** (in use, `agent.py:255`) | (in use) |
| Compaction, on demand, keep recent turns, background | top-level `compaction` param, beta `compact-2026-09-04` | Beta, 2026-09-14 [C15, C1] | **Yes**: `beta.messages.create(compaction=...)` | Compact old history in the background without a pause; keep recent turns word for word |
| Context editing | `clear_tool_uses_20250919`, `clear_thinking_20251015`, beta `context-management-2025-06-27` | Beta [C14] | **Yes**: `context_management` param | Drop stale email bodies from long sessions |
| Structured outputs | `output_config.format` (`json_schema`); `client.messages.parse()`; `strict: true` | GA [C16] | **Yes** (in use in `followups.py`, `inbox_watch.py`, `settings.py`) | (in use) |
| Citations | `citations: {enabled: true}` on documents; `search_result` blocks | GA [C17] | **Yes**: `citation_*` types, `search_result_block_param.py` | Cite which email or PDF page a claim came from |
| Message Batches | `client.messages.batches.create/retrieve/results` | GA, 50% price [C18] | **Yes**: `client.messages.batches` | Scheduled news and daily briefs pre-computed an hour early at half price |
| Prompt caching | `cache_control` (`ttl: "1h"`), top-level auto-caching | GA [C19] | **Yes** | (in use) |
| Cache diagnostics | `diagnostics={"previous_message_id": ...}` returns `cache_miss_reason` | GA 2026-09-23 [C1, C20] | **Yes**: `messages.create(diagnostics=)`, `cache_miss_*` types | Show cache hit rate in /usage; catch silent cache busters |
| Per-message effort, `clear_at` system messages, mid-conversation tool changes | betas `mid-conversation-output-config-2026-07-01`, `mid-conversation-system-clear-at-2026-08-21`, `mid-conversation-tool-changes-2026-07-01`, `inline-tools-2026-09-15` | Beta [C1] | **Yes** (strings in `AnthropicBetaParam`) | /think mid-chat without busting the cache; add Gmail tools only once connected |
| Task budgets | `output_config.task_budget`, beta `task-budgets-2026-03-13` | Beta [C1] | **Yes** (beta string) | Hard token pacing for /research to fit the monthly cap |
| Fast mode | `speed="fast"` (Opus 5.5 GA 2026-10-15, $8/$40 per MTok) | GA [C26, C1] | **Yes**: `speed` param | "Fast" toggle for quick chat. 2x price |
| Speech and voice | none | **Not offered**: the release notes mention audio only as C2PA marking of generated files [C1] | **No** (`grep -ril "audio\|speech"` in the SDK finds only dream-session types) | Voice notes still need a separate STT. Claude can't fill this gap |
| User profiles | `user_profile_id` (beta `user-profiles-*`) | Launched 2026-10-20 [C25] | **Yes** | For resellers. Not relevant for one owner |
| Managed Agents | `client.beta.agents/sessions/environments/deployments/vaults/webhooks` | Beta [C23] | **Yes** | Hosted agent loop. Conflicts with self-hosting |

SDK upgrade: 2.0.0 (2026-10-21) moves to API version `2026-10-21`, under which `temperature`, `top_p` and `top_k` return 400 on every model [C24]. ClaudeBot sends none of these today (not grepped exhaustively), so the upgrade risk looks low, but it should get its own task.

---

## 3. Google APIs (OAuth Desktop client, personal account)

The scope lists and method-to-scope mapping below come from the bundled discovery documents (local). Classification and verification details are from Google pages via search excerpts.

| Capability | Exact API name | Scope needed | New scope? Classification | In installed client? | User feature it would unlock |
|---|---|---|---|---|---|
| Incremental mailbox sync | `users.history.list(startHistoryId=)` | `gmail.modify` (already granted) | No | **Yes** (gmail.v1) | Inbox alerts in about a minute with a cheap delta call instead of re-searching |
| Gmail push | `users.watch(topicName=)`, `users.stop`; Pub/Sub `projects.subscriptions.pull` | `gmail.modify` + `https://www.googleapis.com/auth/pubsub` (or `cloud-platform`) | Yes, pubsub; its classification is [UNVERIFIED] | **Yes** (gmail.v1, pubsub.v1) | Real-time alerts. A **pull** subscription needs no public endpoint, since Google supports "webhooks or polling on a single subscription" [G2]. The topic must grant Publisher to `gmail-api-push@system.gserviceaccount.com` [G2]. The watch must be renewed before `expiration` [G10]; "7 days" is from third-party sources [UNVERIFIED]. It needs a GCP project with Pub/Sub; whether the free tier covers it at no cost is [UNVERIFIED] |
| Labels | `users.labels.create/list`, `users.messages.batchModify` | `gmail.modify` (accepted per discovery) | No | **Yes** | "Label everything from my accountant as Taxes"; bulk archive or label |
| Filters | `users.settings.filters.create/list/delete` (max 1,000) | `gmail.settings.basic` | Yes. **Restricted** [G1] | **Yes** | "Always archive mail from X", a durable rule applied by Gmail itself |
| Vacation responder | `users.settings.updateVacation` | `gmail.settings.basic` | Yes. Restricted [G1] | **Yes** | "I'm off until Monday, set my auto-reply" |
| Free/busy | `freebusy.query` | `calendar` (granted) or `calendar.freebusy` | No | **Yes** | "When am I free Thursday?"; suggest slots in email replies; meeting-conflict warnings in briefs |
| Event reminders | `events.insert/patch` with `reminders.overrides[{method: "popup" or "email", minutes}]` | `calendar` (granted) | No | **Yes** (`EventReminder.method`) | "Remind me 2 hours before" on calendar events. Google pushes the alert, which also works when the bot is offline |
| Quick add, event types | `events.quickAdd`; `eventType` in {`birthday`, `focusTime`, `fromGmail`, `outOfOffice`, `workingLocation`} | `calendar` | No | **Yes** | Block focus time; out-of-office; birthdays in the daily brief |
| Calendar push | `events.watch` (`Channel.address` = HTTPS URL) | `calendar` | No | **Yes** | Needs a public HTTPS webhook. Use polling with `syncToken` instead |
| Google Tasks | `tasks.insert/list/patch/move`, `tasklists.list` | `https://www.googleapis.com/auth/tasks` | Yes. Sensitive [UNVERIFIED] | **Yes** (tasks.v1) | To-dos that sync to the Gmail/Calendar sidebar and the Tasks app. Note: `due` keeps only the date ("time portion ... is discarded"), so keep timed reminders in the bot |
| Contacts | `people.searchContacts`, `people.connections.list`, `otherContacts.search`, `people.createContact` | `contacts.readonly` + `contacts.other.readonly` (or `contacts` to write) | Yes. Sensitive [UNVERIFIED] | **Yes** (people.v1) | "Email Priya" resolves the right address; birthdays; who-is-this context for inbox alerts |
| Drive, app files | `files.create/list`, `files.export` | `drive.file` | Yes. **Non-sensitive, recommended** [G6] | **Yes** (drive.v3) | Save generated docx, xlsx and pptx to the owner's Drive and return a link |
| Drive, full | `files.list` over all files, `changes.watch` | `drive.readonly` or `drive` | Yes. **Restricted** [G6] | **Yes** | "Find the lease PDF in my Drive". Heavy scope |

**Verification implications.** Restricted scopes (`gmail.modify`, which ClaudeBot already uses, `gmail.readonly`, `gmail.settings.basic`, `drive`) normally need restricted-scope verification plus a security assessment [G1, G9]. Sensitive scopes need verification without an assessment [G1, G5]. For a self-hosted, single-owner project:
- In **Testing** status, only listed test users (at most 100) can sign in, and refresh tokens expire after 7 days [G3]. ClaudeBot owners would have to reconnect weekly.
- In **Production** while unverified, users see the unverified-app screen and the app is capped at 100 users [G3, G4]. Community reports say tokens then persist [G8]. A "personal use" exemption from verification is commonly cited, but Google's exact wording could not be confirmed here [UNVERIFIED, G4].
- Each new scope triggers re-consent. `/connect` must request the new scopes incrementally, and `google_connect.py:116` already checks that granted ⊇ required. Prefer `drive.file` over `drive`, `calendar.freebusy` over broader calendar scopes, and avoid `gmail.settings.basic` unless filters are a top feature.

---

## 4. The 8 capabilities with the biggest product upside

Ranked by user value against cost of change, within the constraints (self-hosted, one owner, no paid services, security model kept, testable offline with fakes).

1. **Telegram Business connection: DM inbox and reply-as-me.** `business_message`, `BusinessBotRights.can_reply`/`can_read_messages`, `send_message(business_connection_id=)`, `readBusinessMessage`. PTB 22.8: **yes**. Brings ClaudeBot's Gmail triage to the owner's Telegram DMs: unread-DM digest, urgent-DM alerts, drafted replies sent only on tap. No Premium needed since 10.0 [T1, T13, T14]. Risks: third-party text must be fenced, the 24-hour reply window, and the owner's own outgoing business messages must not be read as commands.
2. **Calendar `freebusy.query` + `reminders.overrides`.** No new scope. "When am I free", slot suggestions inside email replies, conflict warnings in the brief, and native Google reminders. Easy to test with fakes.
3. **Gmail `users.history.list` incremental sync** (with `users.watch` and a Pub/Sub pull as an option). Faster, cheaper inbox alerts with no public endpoint. Pub/Sub needs GCP setup and an extra scope, so start with history polling.
4. **Google Tasks API** (`tasks.insert/list/patch`, scope `tasks`). Reminders and to-dos that live where the user already looks. A common assistant ask, at the cost of one new sensitive scope.
5. **People API contact resolution** (`people.searchContacts`, `otherContacts.search`, scopes `contacts.readonly` and `contacts.other.readonly`). Turns "email Mom" into a correct send and stops address guessing in drafts.
6. **Guest mode** (`guest_message` + `answerGuestQuery`). PTB 22.8: **yes**. Summon the assistant from any chat. Must be owner-only, and replies must not leak private data because the chat sees them.
7. **Rich Messages + `sendRichMessageDraft`, with 10.3 `can_stop` and `MessageGenerationStopped`.** PTB 22.8: **no**, use `do_api_request`. Native tables, collapsible sources and reasoning, and a real Stop button for streaming. High visible polish, but the API is new and PTB lacks it, so wrap it behind a capability flag with a fallback to `sendMessageDraft`.
8. **Message Batches API for scheduled briefs** (`client.messages.batches`), with the advisor tool (`advisor_20260301`) as a runner-up cost lever. SDK: **yes**. Halves the cost of briefings that run on a schedule, which directly stretches the monthly budget cap.

Runners-up: inline mode (`answerInlineQuery`) for compose-anywhere; reactions (`setMessageReaction`) as instant acknowledgement; `drive.file` save-to-Drive; programmatic tool calling for bulk email work; on-demand background compaction (`compact-2026-09-04`); ephemeral messages for private answers in groups; Gmail filters (restricted scope).

Gaps that no platform in scope fills: **speech-to-text for voice notes.** Neither the Claude API nor the Bot API offers transcription. The brief lists voice notes, but `bot.py:740` declines them.

---

## Sources

Telegram
- [T1] PTB issue #5228, Bot API 10.0 checklist: https://github.com/python-telegram-bot/python-telegram-bot/issues/5228
- [T2] PTB issue #5261, Bot API 10.1 (open): https://github.com/python-telegram-bot/python-telegram-bot/issues/5261
- [T3] PTB PR #5359, Bot API 10.3 (closed, unmerged): https://github.com/python-telegram-bot/python-telegram-bot/pull/5359
- [T4] PTB README (Bot API 10.0 badge): https://raw.githubusercontent.com/python-telegram-bot/python-telegram-bot/master/README.rst
- [T5] PTB releases (v22.8 latest, 12 Jun): https://github.com/python-telegram-bot/python-telegram-bot/releases
- [T6] Official Bot API changelog (search excerpts only; blocked here): https://core.telegram.org/bots/api-changelog
- [T7] Bot API 10.2 migration guide: https://dev.to/unifyport/telegram-bot-api-102-migration-guide-rich-messages-ephemeral-edits-and-communities-gfe
- [T8] telegram-bot-ruby PR, Bot API 10.3: https://github.com/atipugin/telegram-bot-ruby/pull/341
- [T9] luzrain/telegram-bot-api PR, 10.3: https://github.com/luzrain/telegram-bot-api/pull/10
- [T10] sendMessageDraft in 9.3: https://github.com/openclaw/openclaw/issues/32180
- [T11] Bot API 9.5 notes: https://newreleases.io/project/github/pengrad/java-telegram-bot-api/release/9.5.0
- [T12] Habr on 9.5: https://habr.com/en/articles/1005194
- [T13] Connected business bots (MTProto, no Premium): https://core.telegram.org/api/bots/connected-business-bots
- [T14] SendPulse, Telegram Business (Premium dropped 2026-05-08; one bot per account): https://sendpulse.com/en/knowledge-base/chatbot/telegram/telegram-business
- [T15] Bot API 9.0 overview: https://kod.ru/telegram-bots-api-9-0/amp
- [T16] Guest mode write-ups: https://github.com/muffin-project/muffin-agent/issues/924 , https://github.com/currentbits/mimir/issues/138 , https://github.com/vercel/chat/pull/1024
- [T17] Mini Apps changelog (DeviceStorage 9.0, SecureStorage 9.6): https://core.telegram.org/bots/webapps
- [T18] Checklists: https://github.com/NousResearch/hermes-agent/issues/78745

Claude (fetched directly)
- [C1] Release notes: https://platform.claude.com/docs/en/release-notes/overview
- [C2] Web search: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- [C3] Web fetch: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool
- [C4] Code execution: https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
- [C5] Memory tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
- [C6] MCP connector: https://platform.claude.com/docs/en/agents-and-tools/mcp-connector
- [C7] Computer use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
- [C8] Browser use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-tool
- [C9] Text editor: https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool
- [C10] Tool search: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- [C11] Programmatic tool calling: https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling
- [C12] Files API: https://platform.claude.com/docs/en/build-with-claude/files
- [C13] Agent Skills: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- [C14] Context editing: https://platform.claude.com/docs/en/build-with-claude/context-editing
- [C15] Compaction: https://platform.claude.com/docs/en/build-with-claude/compaction (and /compaction-on-demand)
- [C16] Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- [C17] Citations: https://platform.claude.com/docs/en/build-with-claude/citations
- [C18] Batch processing: https://platform.claude.com/docs/en/build-with-claude/batch-processing
- [C19] Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- [C20] Cache diagnostics: https://platform.claude.com/docs/en/build-with-claude/cache-diagnostics
- [C21] Advisor tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool
- [C22] Managed Agents memory: https://platform.claude.com/docs/en/managed-agents/memory
- [C23] Managed Agents overview: https://platform.claude.com/docs/en/managed-agents/overview
- [C24] API version 2026-10-21 migration: https://platform.claude.com/docs/en/api/migration-2026-10-21
- [C25] User profiles: https://platform.claude.com/docs/en/manage-claude/user-profiles
- [C26] Fast mode: https://platform.claude.com/docs/en/build-with-claude/fast-mode

Google (search excerpts; developers.google.com blocked here; method and scope facts verified locally in the discovery documents)
- [G1] Gmail scopes (restricted and sensitive tiers): https://developers.google.com/workspace/gmail/api/auth/scopes
- [G2] Gmail push notifications: https://developers.google.com/gmail/api/guides/push
- [G3] OAuth app states (Testing: 100 users, 7-day tokens): https://developers.google.com/identity/protocols/oauth2/production-readiness/overview
- [G4] Unverified apps: https://support.google.com/cloud/answer/7454865
- [G5] Sensitive scope verification: https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification
- [G6] Drive scope classifications (drive.file non-sensitive; drive restricted): https://developers.google.com/slides/api/scopes
- [G8] Community note on unverified production apps: https://github.com/DeRusto/goCasa/issues/3
- [G9] Nylas scope guide: https://developer.nylas.com/docs/cookbook/use-cases/build/oauth-scopes-email-calendar/
- [G10] users.watch reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/watch
