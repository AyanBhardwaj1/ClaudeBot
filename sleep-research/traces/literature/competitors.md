# Competitor landscape: AI personal assistants for email, calendar, reminders and errands (as of 2026-10-31)

Prepared for the ClaudeBot product team. The baseline is what ClaudeBot 1.0 already does, per `sleep-research/BRIEF.md`.

## Method and caveats

- I ran 29 WebSearch queries covering messaging-app assistants, big-platform assistants, AI email clients, user-sentiment threads and security reports. Sources are mostly 2025-2026.
- WebFetch could not reach several hosts from this sandbox (blog.saner.ai, rywalker.com, maketecheasier.com did not resolve). Every claim below therefore rests on the search results: the result titles and URLs, plus the search tool's summary of those pages. I did not read pages verbatim. When a summary blended several URLs, I cite the most specific one(s). Treat any single-source figure, especially pricing, as indicative.
- **[UNVERIFIED]** marks claims that were single-source, came from an aggregator or competitor blog, or conflicted between sources.
- Many review sites are affiliate pages or competitor blogs: Saner.ai reviewing Poke, Inbox Zero comparing Superhuman and Fyxer, Lindy's own blog. They're flagged where relevant.

---

## 1. Assistants that live in messaging apps

### Poke (The Interaction Company of California)
- **What it is:** A proactive, text-first assistant you message over iMessage, SMS and WhatsApp. Setup reportedly takes about 2 minutes: phone number, connect email, start texting. https://www.unite.ai/zh-cn/poke-review/
- **Channels:** iMessage, SMS, WhatsApp (select markets). One source also lists Telegram [UNVERIFIED]. https://tooldirectory.ai/tools/poke
- **Standout features:**
  - On 2026-06-04 Poke became the first and only AI agent approved on Apple's Messages for Business platform. https://appleinsider.com/articles/26/06/04/first-ai-agent-for-messages-business-chat-approved-by-apple , https://www.techwyse.com/news/platform-updates/apple-messages-for-business-first-ai-agent-poke-approved
  - About 100M messages relayed, per the company to TechCrunch. https://ecosistemastartup.com/?p=85865
  - Proactive messaging: "doesn't always need a user prompt to message you"; bill reminders and calendar-conflict alerts. https://www.producthunt.com/p/poke-by-interaction-co/a-week-with-poke-review-a-promising-start-for-a-proactive-ai-assistant?page=3 , https://www.unite.ai/zh-cn/poke-review/
  - "Recipes": preset automations described in plain language, plus a recipe wizard called "Poke Kitchen". https://www.unite.ai/zh-cn/poke-review/
  - Integrations for Notion, GitHub, Linear and more, plus custom integrations via MCP. https://poke.com/faq
  - Gmail and Outlook (inbox, calendar, contacts); Outlook may be read-only [UNVERIFIED]. https://www.mintlify.com/x1xhlol/system-prompts-and-models-of-ai-tools/commercial/poke
  - Memory of context and preferences across conversations. https://www.unite.ai/zh-cn/poke-review/
- **Pricing:** Free tier, Pro $19/month, Ultra $199/month. One source says $9.99 Pro [UNVERIFIED, conflicting]. https://tooldirectory.ai/tools/poke , https://www.layer3labs.io/guides/poke-ai-explained
- **Ownership:** Reported acquisition by Cognition in July 2026 [UNVERIFIED, single aggregator]. https://tooldirectory.ai/tools/poke
- **Praise:** "finally proactive instead of just reactive"; polished interface. https://www.producthunt.com/p/poke-by-interaction-co/a-week-with-poke-review-a-promising-start-for-a-proactive-ai-assistant?page=3
- **Complaints:**
  - Email triage "doesn't understand context well enough" and can bury urgent mail while forwarding trivia. Recipes are "impressive when they work".
  - The $199 tier is out of reach for the people who most want an assistant. (Source is Saner.ai, a competitor.) https://www.saner.ai/blogs/poke-reviews , https://www.unite.ai/zh-cn/poke-review/

### OpenClaw (formerly Clawdbot, then Moltbot): open-source, self-hosted
- **What it is:** A self-hosted personal assistant you run on your own hardware and talk to through chat apps. It is ClaudeBot's closest structural analogue. https://www.eesel.ai/blog/how-to-use-clawd-bot
- **Names:** Clawdbot (Nov 2025), then Moltbot (2026-01-27), then OpenClaw (2026-01-30). The rename reportedly followed a trademark nudge from Anthropic. https://www.jitendrazaa.com/blog/ai/clawdbot-complete-guide , https://www.scriptbyai.com/openclaw-moltbot-clawdbot-ai-employee/
- **Channels:** WhatsApp (QR link, like WhatsApp Web), Telegram (bot token; the first DM returns a pairing code that must be approved), Discord, Slack, Signal, iMessage and more. https://www.eesel.ai/blog/how-to-use-clawd-bot
- **Standout features:**
  - Email and calendar management; one reviewer had it schedule a meeting. Browser automation; scheduled reminders and briefings. https://maketecheasier.com/self-hosted-clawdbot-ai-assistant
  - Two proactivity primitives:
    - **heartbeat:** a periodic judgment-based check-in in the main session.
    - **cron:** fixed jobs in isolated sessions.
    https://www.stanza.dev/courses/openclaw/automation-workflows/openclaw-cron-vs-heartbeat , https://www.ampere.sh/blog/cron-jobs-heartbeats-making-openclaw-proactive.md
  - File-based memory (`MEMORY.md` plus daily logs), with weekly consolidation jobs that propose edits for approval. https://cookbook.solomonneas.dev/automation/openclaw-cron-deep-dive/
  - A skill marketplace (ClawHub). https://www.theregister.com/2026/02/05/openclaw_skills_marketplace_leaky_security/
  - One-click hosted deploy templates (Railway). https://railway.com/deploy/openclaw-clawdbot-moltbot-aug26--openclaw-jun26
- **Pricing:** Free and open source; you pay for your own model and API usage [UNVERIFIED: no cost figures found].
- **Popularity:** 147k+ GitHub stars [UNVERIFIED, single blog]. https://maketecheasier.com/self-hosted-clawdbot-ai-assistant
- **Praise:** "incredibly powerful", more than a chatbot. https://www.eesel.ai/blog/how-to-use-clawd-bot
- **Complaints (security dominates):**
  - Koi Security found 341 malicious skills out of 2,857 on ClawHub.
  - Snyk found about 7.1% of roughly 4,000 skills expose credentials.
  - Cisco found the top-ranked skill exfiltrated data via prompt injection.
  - Sandboxing is opt-in, and skills get no permission boundaries.
  - OpenClaw itself calls prompt injection "an industry-wide unsolved problem".

  https://www.theregister.com/2026/02/05/openclaw_skills_marketplace_leaky_security/ , https://www.techradar.com/pro/here-are-the-openclaw-security-risks-you-should-know-about , https://blog.barrack.ai/openclaw-security-vulnerabilities-2026/
- **Setup:** "serious technical hurdles". https://www.eesel.ai/blog/how-to-use-clawd-bot

### Meta AI in WhatsApp
- **What it is:** A general assistant built into WhatsApp, Messenger and Instagram.
- **Memory:** Meta AI remembers details from 1:1 chats (not groups). You can review and delete memories, but there is reportedly no opt-out of personalization. https://www.maginative.com/article/meta-ai-rolls-out-new-memory-and-personalization-features/ , https://www.androidauthority.com/meta-ai-whatsapp-memory-3492224/ , https://tech.yahoo.com/ai/articles/instagram-whatsapps-shared-ai-chatbot-145512884.html
- **Reminders:** Seen in WhatsApp beta 2.25.9.14 as "in development". I found no confirmed general rollout; one guide says Meta AI can't set reminders in WhatsApp yet. https://www.huaweicentral.com/whatsapp-beta-shows-new-message-reminders-feature-for-meta-ai/ , https://wabetainfo.com/whatsapp-beta-for-android-2-25-9-14-whats-new/ , https://techpoint.africa/guide/meta-ai-on-whatsapp-how-to-use/
- **Not a Gmail or Calendar assistant** in anything I found.
- **Business agent:** Meta launched a separate Meta Business Agent for businesses on 2026-06-04. https://gdeltcloud.com/events/meta-launches-ai-business-agent-for-whatsapp-instagram-and-m--cameoplus_fb7e450c
- **Pricing:** Free.
- **Concerns:** Privacy track record. https://www.maginative.com/article/meta-ai-rolls-out-new-memory-and-personalization-features/

### Grok (xAI), including in Telegram
- **Telegram:** Durov announced a $300M deal to integrate Grok into Telegram, which Musk disputed ("deal is not signed"). Grok is available as a Telegram bot for Premium subscribers. https://wbgsv0a.gigazine.net/gsc_news/en/20250529-xai-pay-telegram-300-million-integrate-grok , https://tech.yahoo.com/ai/articles/xai-chatbot-grok-available-telegram-203900522.html
- **Tasks:** Scheduled prompts that run once, daily, on chosen weekdays, monthly or yearly, with in-app or email notification. https://testingcatalog.com/grok-set-to-gain-tasks-feature-for-periodical-execution , https://www.testingcatalog.com/upcoming-groks-tasks-feature-gets-ui-upgrade-and-scheduling-tweaks
- **Automations:** Includes inbox-triggered runs [UNVERIFIED]. https://mindstudio.ai/blog/grok-automations-scheduled-tasks-email-triggers
- **Pricing and limits:** X Premium or SuperGrok subscription; limits of 20 standard and 5 advanced tasks per day [UNVERIFIED]. https://www.ainews.com/p/xai-launches-grok-tasks-to-automate-real-time-ai-monitoring-and-analysis
- I found no Gmail or Calendar write integration.

### Dot (New Computer): defunct
- An AI companion that shut down on 2025-10-05 after the co-founders' "diverging visions"; users could export their data first. About 24.5k lifetime iOS downloads by third-party estimate. https://techcrunch.com/2025/09/05/personalized-ai-companion-app-dot-is-shutting-down , https://futurism.com/ai-dot-companion-controversy
- **Lesson:** Companionship alone, without utility, did not sustain it.

### Martin (YC S23)
- **Channels:** iOS app, web, SMS, WhatsApp, phone call, email, Slack. https://www.producthunt.com/products/martin/reviews , https://www.eesel.ai/blog/martin-ai-review
- **Features:** Reads, drafts and sends email; reads and writes the calendar; to-dos and reminders; sends texts and makes calls for you; web search. You can review or edit important actions before they run. https://softwarefinder.com/collaboration-productivity-software/martin , https://www.eesel.ai/blog/martin-ai-review
- **Pricing:** Free trial; paid price not found [UNVERIFIED]. https://tooldirectory.ai/tools/martin
- **Praise:** 4.6 on Product Hunt (7 reviews); "game-changer". https://www.producthunt.com/products/martin/reviews
- I found no independent tests.

### Lindy
- **What it is:** A texting-first "AI executive assistant" over iMessage or SMS (SMS on Android). https://www.lindy.ai/pricing
- **Features:**
  - Gmail and Outlook triage, drafts "in your voice", meeting scheduling and rescheduling, a daily brief, and follow-ups.
  - A meeting notetaker that joins Meet, Zoom and Teams calls from your calendar.
  - Higher tiers add an AI phone agent, computer use and hundreds of integrations.

  https://zapier.com/blog/lindy-review/ , https://www.cloudtalk.io/blog/lindy-ai-review/ , https://pipeline.zoominfo.com/sales/lindy-ai-features
- **Pricing:** Plus $49.99/month (2 inboxes); 7-day trial that requires a card. Higher tiers are listed as $59.99 on lindy.ai or Pro $99.99 and Max $199.99 elsewhere [conflicting]. Voice calls cost $0.19/min. https://www.lindy.ai/pricing , https://www.cloudtalk.io/blog/lindy-ai-pricing/ , https://www.wearefounders.uk/lindy-pricing-2026-every-plan-explained/
- **Praise:** Feels like "texting an assistant"; good transcripts. G2 4.9/5 (171 reviews). https://www.g2.com/products/lindy-lindy
- **Complaints:** "Expensive" is the most common complaint; credits run out faster than expected; billing disputes. https://www.cloudtalk.io/blog/lindy-ai-review/

### Other messaging-app assistants found
- **Zapia (Uruguay):** A WhatsApp assistant with reminders, calendar management and scheduled WhatsApp messages. Raised $7M led by Prosus Ventures; 3.5M+ users. https://latamlist.com/zapia-raises-a-7m-round/ , https://www.contxto.com/en/funding/prosus-ventures-leads-7-25-million-round-for-zapia/ , https://apps.apple.com/app/id6470821480
- **Coco:** On WhatsApp and Telegram. Reminders for you and your friends, Google and Outlook calendar, shared lists. https://www.producthunt.com/products/coco-4/launches
- **Yaya:** A WhatsApp assistant for reminders, tasks, calendar and shopping lists (launched Feb 2026). https://www.producthunt.com/products/yaya-ai-whatsapp-assistant/launches
- **HelloAria:** Reminders, to-dos, events, meeting notes and follow-ups from WhatsApp, Telegram or email. https://www.producthunt.com/posts/hello-aria-3
- **Waply:** Reminders and calendar over WhatsApp, by text or voice note. https://betalist.com/startups/waply
- **Toki:** Reportedly ended WhatsApp support on 2026-02-15 because of WhatsApp policy changes, and is now app-only [UNVERIFIED, third-party]. https://smartcalendars.ai/en/articles/smart-calendars-ai-vs-toki
  - This is a channel-risk signal for any WhatsApp-based assistant.
- **Saner.ai:** An ADHD-oriented app (not a messaging bot) with an assistant called "Skai". It turns brain dumps into tasks and events, builds a morning plan from tasks, email and calendar, and has an AI inbox. Freemium. It is repeatedly recommended in 2026 Reddit threads. https://tooldirectory.ai/tools/saner-ai , https://www.eesel.ai/blog/saner-ai-pricing , https://reddit.sentinel-team.org/posts/1sv3ucz/snapshots/2026-05-01T23%3A40%3A05.297317Z
- **Orchid:** Positioned as an executive-assistant alternative to Poke (vendor comparison page). https://orchid.ai/compare/orchid-vs-poke

---

## 2. Big-platform assistants

### ChatGPT (OpenAI)
- **Pulse:**
  - Nightly background research from chat history, memory and feedback, delivered as morning cards. Users curate it with thumbs up and down.
  - Optional Gmail and Calendar connectors (off by default) can draft meeting agendas, for example.
  - Launched 2025-09-25 for Pro ($200/month) on mobile, with Plus "later".

  https://yourstory.com/ai-story/openai-chatgpt-pulse-pro-daily-briefings , https://www.besthub.dev/articles/how-chatgpt-s-new-pulse-turns-ai-into-a-proactive-personal-assistant-a8461c4b717b , https://forklog.com/en/openai-introduces-pulse-mode-in-chatgpt-for-proactive-updates/
  - Current 2026 tier availability is [UNVERIFIED].
- **Tasks (scheduled tasks):**
  - Introduced January 2025 for paid tiers: one-off or recurring reminders and scheduled prompts, managed from a Tasks list.
  - A 2026 analysis says tasks are scheduled prompts, not autonomous agents, and that recall of memory in scheduled runs is not guaranteed.

  https://fortune.com/2025/01/16/openai-chatgpt-tasks-features-how-it-works/ , https://blog.laozhang.ai/en/posts/chatgpt-scheduled-tasks-context-memory-tools
- **Agent mode:**
  - Browses and acts on websites, for example restaurant and hotel bookings, and asks for confirmation before consequential steps. https://www.ninetwothree.co/blog/chatgpt-agent-mode , https://www.tomsguide.com/ai/chatgpt/i-use-chatgpt-to-do-all-of-my-restaurant-bookings-and-it-saves-me-so-much-time
  - Critics call it "Sometimes Helpful, Mostly (still) Useless" and cite a cap of 40 agent messages per month on Plus [UNVERIFIED, may be outdated]. https://pupuweb.com/is-chatgpt-agent-mode-a-complete-waste-of-money-and-time , https://www.nngroup.com/articles/impressions-chatgpt-agent/
- **Channel:** App and web. (A Telegram or WhatsApp presence was not covered by my searches.)

### Google Gemini
- **Scheduled actions:**
  - Recurring or one-time prompts, for example daily calendar and email summaries.
  - Up to 10 active at a time; requires Google AI Pro, Ultra or Workspace; disabled if "Keep Activity" is off.

  https://www.tomsguide.com/ai/google-gemini/gemini-now-rivals-chatgpt-in-another-key-feature-heres-how-to-schedule-ai-tasks , https://beebom.com/gemini-scheduled-actions-feature-rolling-out
- **Gemini in Gmail (January 2026 "Gemini era"):**
  - **AI Inbox:** Filters low-importance mail and surfaces to-dos.
  - **Suggested Replies:** Context-aware and closer to your voice. Free for all users, alongside Help Me Write.
  - **"Help me schedule":** Proposes meeting times inside an email. Paid plans; US-only for personal accounts.

  https://blog.google/products-and-platforms/products/gmail/gmail-is-entering-the-gemini-era/ , https://fortune.com/2026/01/08/google-ai-inbox-gmail-gemini-3-integration-email-new-view-features/ , https://support.google.com/mail/answer/16831098
- **Gemini Agent:** Launched November 2025 for US Ultra subscribers. Example tasks: manage Calendar events, create reminders, organize the Gmail inbox. https://9to5google.com/2025/11/18/gemini-3-pro-app/ , https://kompozy.io/reviews/gemini-agent
- **Gemini Spark:** Announced at I/O 2026 as an always-on personal agent that prioritizes your day from Gmail, Calendar and Tasks. Rolling out to US Ultra subscribers from late May 2026. https://www.digitalapplied.com/blog/gemini-spark-always-on-personal-agent , https://arynews.tv/gemini-spark-ai-agent-rolls-out-to-google-ai-ultra-subscribers , https://www.phonearena.com/news/every-gemini-update-google-announced-at-io-2026-declaring-the-agentic-era-is-here_id180486
- **Personal Intelligence:** Connects Gmail, Calendar and Photos; Google says it does not train on that data directly. https://nextpj-net.pages.dev/blog/gemini-personal-intelligence-gmail-calendar-photos-guide-2026
- **Pricing:** AI Pro $19.99/month; Ultra figures conflict ($99.99 to $249.99) [UNVERIFIED].
- **Complaint:** The agent features are "locked behind a $100 monthly paywall". https://www.pulse.bot/ai/news/googles-ai-agent-ambitions-are-real-but-remain-locked-behind-a-100-monthly-paywall-25e1f3d8-0f02-40b7-94ac-583809dddca3/

### Claude (Anthropic) apps
- **Google Calendar connector:** Pro, Max, Team and Enterprise; beta. https://claude.com/docs/connectors/google/calendar.md
  - Reported to have full read and write access to events and to find availability. The Gmail connector is reported to be draft-only, with no direct send [UNVERIFIED, secondary]. https://www.usecarly.com/blog/claude-google-calendar-integration/
- **Memory:**
  - Unified across chat and Cowork from 2026-08-25.
  - On by default for Free, Pro and Max; off by default for Team and Enterprise.
  - Users can edit, pause or erase memories.

  https://thenextweb.com/news/anthropic-claude-cowork-shared-memory-default , https://engadget.com/2243753/claude-memory-now-works-across-both-chats-and-cowork-sessions , https://www.techrepublic.com/article/news-turn-off-claude-memory/
- **Cowork Scheduled Tasks:** Reported in February 2026. Sources disagree on whether tasks need the desktop app open [UNVERIFIED]. https://www.besthub.dev/articles/anthropic-unveils-7-major-updates-this-week-a-full-breakdown-e957f871d242 , https://www.usecarly.com/blog/claude-google-calendar-integration/
- **Claude in Chrome:** A side panel that is part of the same memory. https://engadget.com/2243753/claude-memory-now-works-across-both-chats-and-cowork-sessions
- **Channel:** App, web, desktop and Chrome. There is no first-party Telegram or WhatsApp channel, which is the gap ClaudeBot fills.

### Apple Intelligence / Siri
- **Status:** Personal-context Siri slipped from 2025 to 2026. https://www.macrumors.com/2025/06/12/apple-intelligence-siri-spring-2026/
- At WWDC 2026 Apple unveiled a rebuilt "Siri AI" that combines personal context from messages, email, photos and on-device data with Gemini-powered world knowledge. https://www.eweek.com/news/apple-siri-ai-wwdc-2026/
- It reportedly ships as a beta in late 2026, English-only, with the EU delayed and China not included at launch. https://www.lagaceta.com.ar/nota/1140259/sociedad/apple-cumplio-presento-siri-ai-asistente-quiere-cambiar-forma-usamos-iphone.html
- A conflicting source says app-aware Siri shipped in iOS 26.4, "smaller than the 2024 demo" [UNVERIFIED]. https://plainai.aguidetocloud.com/changes/apple-intelligence-siri-shipped/
- **Concern:** Ecosystem lock-in. https://bsppd.business-standard.com/technology/tech-news/apple-s-ai-reset-is-a-step-in-right-direction-but-rollout-questions-linger-126060900003_1.html
- **Channel:** Built into iPhone and Mac.

### Amazon Alexa+
- **Features:**
  - Summarizes your day from connected calendars and schedules events.
  - Pulls events from emails, invites and school flyers into the calendar. You can email a document to Alexa, and it asks which event to add.
  - Lists and reminders.

  https://aboutamazon.com/news/devices/new-alexa-top-features , https://www.techradar.com/home/smart-home/up-close-with-alexa-plus-this-may-finally-be-the-echo-upgrade-ive-been-waiting-for , https://tomsguide.com/ai/ive-been-using-alexa-for-3-months-here-are-my-5-favorite-features-and-one-im-not-a-fan-of
- **Complaints:**
  - "Functional but flawed".
  - Struggled to add Google Calendar events accurately.
  - Some features were missing at launch.

  https://fortune.com/2025/07/26/amazon-alexa-plus-ai-agent-voice-assistant-hands-on-review-compared-chatgpt/ , https://aichief.com/news/alexa-review-amazons-new-ai-assistant-tested/ , https://www.tomsguide.com/ai/alexa-is-here-but-its-missing-some-features-heres-why-thats-not-such-a-bad-thing
- **Channel:** Echo devices, app and web. Pricing not confirmed in my searches [UNVERIFIED].

---

## 3. AI email clients and inbox assistants

### Superhuman (now Grammarly-owned)
- **Ownership:** https://www.dragapp.com/blog/superhuman-alternatives/
- **Features:**
  - **Split Inbox:** VIP, team, newsletter and notification streams.
  - **Auto Labels** and **Write with AI**, on Starter at $30/month.
  - **Auto Drafts:** Drafts waiting in the inbox; Business plan at $40/month.
  - **Ask AI:** Q&A over your inbox; Business plan.

  https://fast.io/resources/superhuman-ai-review-2026/ , https://www.usecarly.com/blog/superhuman-review/
- **Complaint:** A tester found Auto Drafts "often generated a positive response to a pitch, or agreed to a meeting at a post-midnight time". https://fast.io/resources/superhuman-ai-review-2026/
- **Channel:** Desktop and mobile app.

### Shortwave (Gmail client)
- **Features:**
  - **AI Assistant:** Chat over your inbox; drafts email, schedules calendar events, searches email and the web.
  - **Ghostwriter:** Learns your voice from your sent mail.
  - **AI Filters:** Plain-English rules that label, star, archive or delete.
  - Threads can be handled like tasks: done, snooze, pin.

  https://shortwave.com/docs/guides/ai-assistant , https://www.shortwave.com/blog/2023-wrapped-year-of-ai-email , https://yespress.io/products/shortwave.md
- **Pricing:** Conflicting. Roughly $9-24 per seat, plus a Premier tier near $45; AI-filter caps vary by tier [UNVERIFIED]. https://costbench.com/compare/shortwave-vs-superhuman/ , https://aiagentrank.io/blog/shortwave-vs-superhuman-2026
- **Praise:** "wins on AI features and price" against Superhuman. https://www.asianefficiency.com/email-management/superhuman-vs-shortwave/

### Fyxer
- **What it is:** An overlay on Gmail or Outlook, not a client.
- **Features:**
  - Fixed category labels such as To Respond, FYI and Marketing.
  - Reply drafts in your tone.
  - A meeting notetaker for Zoom, Meet and Teams that emails the notes; scheduling.

  https://docs.fyxer.com/get-started/quickstart , https://support.fyxer.com/en/articles/10968437-what-is-fyxer-ai , https://gmelius.com/ja/blog/fyxer-ai-review
- **Pricing:** About $30/month minimum [UNVERIFIED; the source is competitor Inbox Zero]. https://www.getinboxzero.com/superhuman-vs-fyxer
- **Complaints:**
  - Drafts often need rewriting.
  - Rigid sorting buries important mail.
  - Outlook lags Gmail.
  - Trial and billing friction.
  - Mixed views on the meeting notes.

  https://www.alkmist.com/fyxer-ai-review , https://ca.trustpilot.com/review/fyxer.com?page=9 , https://www.g2.com/products/fyxer/reviews

### Inbox Zero (open source)
- **Features:**
  - An assistant driven by plain-English rules: draft, label, archive, forward, mark spam, call a webhook.
  - **Reply Zero:** Tracks mail you need to reply to and replies you're waiting on.
  - Bulk unsubscribe, a cold-email blocker and email analytics.
  - Chat with the assistant from Slack or **Telegram**.

  https://cdn.jsdelivr.net/gh/elie222/inbox-zero@main/README.md , https://github.blesdmm.dns-dynamic.net/elie222/inbox-zero
- **Hosting:** Self-hostable (Docker image). https://hub.docker.com/r/elie222/inbox-zero
- **Pricing:** Hosted from about $6/month [UNVERIFIED]. https://efficient.app/apps/inbox-zero

### Notion Mail
- **Auto label:** Describe the categories you want, confirm the AI's sample matches, and it learns from your corrections. https://www.notion.com/en-gb/help/guides/organize-your-inbox-with-notion-ai-auto-labeling
- **Shutdown:** Localized help pages reportedly say Notion Mail stopped service on 2026-09-22 [UNVERIFIED].

### Spark (Readdle)
- **Features:**
  - **+AI:** Summarize threads, draft and rephrase, adjust tone.
  - **"My Writing Style":** Learns from 3 sent samples.
  - **Priority and Gatekeeper:** Screen senders.
  - 40 AI meeting notes per month on Spark Plus.
  - AI Assistant searchable over 1 year of history (unlimited on Pro).
  - AI email rules slated for Pro.

  https://readdle.com/press/release/4647 , https://www.macrumors.com/2024/02/22/spark-mail-ai-writing-assistant , https://apps.apple.com/app/id6445813049
- **Pricing:** Current prices not confirmed [UNVERIFIED].

---

## 4. What users say they want (cross-product sentiment)

From 2026 Reddit threads (archived mirror) https://reddit.sentinel-team.org/posts/1sv3ucz/snapshots/2026-05-01T23%3A40%3A05.297317Z , https://reddit.sentinel-team.org/posts/1t7c020/snapshots/2026-05-15T18%3A26%3A28.525889Z (anecdotal, small sample):

1. **Real proactivity.** Flag deadlines before they're missed. A timed inbox check "is closer to an alarm clock" than a proactive assistant.
2. **Memory, tool access and follow-up on open commitments.**
3. **Less setup.** Learn calendar habits by observation rather than configuration. Calendar handling is "one of the worst implementations across every tool".
4. **Turn email into calendar events and actions.** Drafting is treated as a solved, minor feature.
5. **Trust and timing.** Wariness about deep email and calendar permissions without an export path. The core tension: "having it do stuff when you don't want it to, and [not] doing stuff when you want it to".

---

## (a) Feature matrix

Legend: Y = has it, P = partial, N = no, ? = not confirmed in my sources. ClaudeBot's column is based only on BRIEF.md.

| # | Feature | Poke | OpenClaw | Lindy | Martin | Zapia / WA bots | Meta AI (WA) | ChatGPT | Gemini | Claude app | Superhuman | Shortwave | Fyxer | Inbox Zero | **ClaudeBot** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Lives in a messaging app (no new app) | Y | Y | Y | Y | Y | Y | N | N | N | N | N | N | P (Telegram/Slack chat) | **Y** (Telegram) |
| 2 | More than one messaging channel | Y | Y | P (iMessage/SMS) | Y | P (Coco: WA+TG) | N | N | N | N | N | N | N | Y | **N** |
| 3 | Email search/read/send | Y | Y | Y | Y | ? | N | P (connectors) | Y | P (draft-only, unverified) | Y | Y | P (drafts) | Y | **Y** (+ undo window) |
| 4 | Calendar read/write | Y | Y | Y | Y | Y | N | P | Y | Y | ? | Y | Y | ? | **Y** |
| 5 | Reminders / one-off scheduled nudges | Y | Y | ? | Y | Y | P (beta) | Y | Y | ? | N | P (snooze) | N | N | **Y** |
| 6 | Recurring scheduled prompts (Tasks/cron) | Y (recipes) | Y | ? | ? | ? | N | Y | Y | Y (Cowork) | N | N | N | N | **Y** |
| 7 | Daily brief / morning digest | ? | Y | Y | ? | ? | N | Y (Pulse) | Y (Spark/scheduled) | ? | N | N | N | P (analytics) | **Y** |
| 8 | Event-driven proactivity (conflicts, bills, deadlines, heartbeat) | Y | Y (heartbeat) | P | ? | ? | N | P (Pulse) | Y (Spark) | N | N | N | N | N | **P** (new-mail alerts only) |
| 9 | Inbox triage / auto-categorize / priority labels | Y (weak) | ? | Y | ? | N | N | N | Y (AI Inbox) | N | Y (Split, Auto Labels) | Y | Y | Y | **P** (Haiku triage to alerts; no Gmail labels) |
| 10 | Natural-language email rules | Y (recipes) | P (skills) | ? | ? | N | N | N | N | N | P | Y (AI Filters) | N | Y | **N** |
| 11 | Auto-drafted replies waiting in inbox | ? | ? | Y | ? | N | N | N | P (Suggested Replies) | N | Y | P | Y | Y | **N** (on-demand drafts only) |
| 12 | Writes in *your* voice (learned style) | ? | ? | Y | ? | N | N | N | Y | N | ? | Y (Ghostwriter) | Y | ? | **N** (not stated) |
| 13 | Reply / follow-up tracking ("waiting on") | ? | ? | Y | ? | N | N | N | P (AI Inbox to-dos) | N | ? | P | N | Y (Reply Zero) | **N** |
| 14 | Meeting scheduling help (propose times, find availability) | ? | Y | Y | Y | ? | N | N | Y (Help me schedule) | Y (find availability) | ? | Y | Y | N | **P** (calendar access; no flow stated) |
| 15 | Extract events/tasks from email, docs, photos | ? | ? | ? | ? | ? | N | ? | ? | ? | N | P | N | N | **P** (reads photos/PDFs; no stated extraction flow) |
| 16 | To-do / shopping lists, shared lists | ? | ? | Y (ad-hoc tasks) | Y | Y (Coco, Yaya) | N | N | Y (Tasks) | N | N | P | N | N | **N** |
| 17 | Persistent memory, user-viewable/deletable | Y | Y (MEMORY.md) | ? | ? | ? | Y | Y | Y | Y | N | N | N | N | **Y** (/memory) |
| 18 | Web search / research with citations | ? | Y | ? | Y | ? | Y | Y | Y | Y | N | Y (web search) | N | N | **Y** (/research) |
| 19 | Browser agent for errands (book, fill forms) | ? | Y | Y (computer use) | ? | N | N | Y (agent mode) | Y (Agent) | Y (Chrome) | N | N | N | N | **N** |
| 20 | Third-party integrations / MCP / skills | Y (MCP) | Y (ClawHub) | Y (hundreds) | P (Slack) | ? | N | Y (connectors) | P (Google apps) | Y (connectors) | N | N | N | P (webhook) | **N** (Google only) |
| 21 | Meeting notetaker | ? | ? | Y | ? | N | N | ? | ? | ? | N | N | Y | N | **N** |
| 22 | Voice input | ? | ? | ? | Y (call) | Y (Waply) | Y | Y | Y | Y | N | N | N | N | **Y** (voice notes) |
| 23 | Acts on your behalf to third parties (texts, calls) | ? | ? | Y (phone agent) | Y | P (scheduled WA msgs) | N | P (agent) | N | N | N | N | N | N | **N** |
| 24 | Human-in-the-loop confirmation before consequential actions | ? | P (opt-in) | ? | Y | ? | n/a | Y | ? | Y (drafts) | Y | Y | Y (drafts) | P | **Y** (tap to send, undo) |
| 25 | Bulk unsubscribe / cleanup / cold-email blocker | ? | ? | ? | ? | N | N | N | N | N | ? | ? | N | Y | **N** |

**Sources for the matrix:** the per-product sections above. "?" means my searches neither confirmed nor ruled out the feature. It does not mean the product lacks it.

**ClaudeBot strengths in the matrix:**
- It already covers the core "assistant in your messenger" stack: rows 1, 3-7, 17, 18, 22 and 24.
- It does things few competitors claim: fact-checking forwarded messages, a code sandbox with office-file skills, charts, personality and job modes, a budget cap, and a strict untrusted-data fencing model.

---

## (b) Features competitors have that ClaudeBot lacks, ranked

The score combines **frequency** (how many products in this survey ship the feature) and **user value** (explicit praise or demand in reviews and Reddit). Feasibility under the BRIEF constraints (self-hosted, Claude, Telegram and Google APIs only, offline-testable, keep the security model) is noted but does not change the rank.

| Rank | Missing feature | Frequency (products) | User-value evidence | Fit with constraints |
|---|---|---|---|---|
| 1 | **Event-driven proactivity ("heartbeat")**: periodic judgment-based scan of email, calendar and reminders that pings only when something matters (conflicts, deadlines, bills, unanswered threads) | Poke, OpenClaw, Gemini Spark, ChatGPT Pulse, Lindy (5) | The top Reddit complaint is that scheduled checks are "an alarm clock"; Poke's main praise is "proactive instead of reactive" | High. Haiku triage plus a scheduler already exist; keep tap-to-send |
| 2 | **Inbox triage into Gmail labels / priority view, with NL rules** ("label anything from my landlord as Urgent") | Superhuman, Shortwave, Fyxer, Inbox Zero, Notion Mail, Gemini AI Inbox, Spark, Poke, Lindy (9) | Most common email feature. Accuracy is the top complaint (Poke, Fyxer), so a confirm-and-learn loop like Notion's is valued | High. Gmail labels API plus Haiku; rules stored in SQLite |
| 3 | **Reply / follow-up tracking**: "you haven't replied to X in 3 days", "Y hasn't answered you" | Inbox Zero (Reply Zero), Lindy follow-ups, Gemini AI Inbox to-dos (3+) | Reddit wish list: "Proactive follow-up" on open commitments | High. Thread-state queries over Gmail |
| 4 | **Auto-drafted replies in the user's voice**, ready to approve from an alert | Superhuman, Fyxer, Inbox Zero, Lindy, Shortwave (Ghostwriter), Spark, Gemini (7) | Widely marketed; users complain drafts need rewriting or agree to bad things (post-midnight meeting) | High. Few-shot from sent mail; already gated by tap-to-send |
| 5 | **Meeting scheduling flow**: find mutual free slots, propose times in a reply, create the event on acceptance | Gemini (Help me schedule), Lindy, Martin, Shortwave, Fyxer, Claude connector (6) | Reddit: calendar is "one of the worst implementations" | High. Calendar freebusy plus a draft |
| 6 | **Email, photo or PDF to calendar event or task extraction** (forward a flyer, get an event) | Alexa+, Saner, HelloAria, Toki (image/email capture), Shortwave (4+) | Reddit: "integration of email events with … the calendar is the next step" | High. Files API vision plus Calendar; confirm button |
| 7 | **Lists / to-dos** (shopping, packing, shared) beyond reminders | Coco, Yaya, Martin, Alexa+, Saner, Gemini/Google Tasks (6) | Core to WhatsApp bots' pitch | High. SQLite or Google Tasks API |
| 8 | **Third-party integrations via MCP / skills** | Poke, OpenClaw, Lindy, ChatGPT, Claude (5) | Valued, but OpenClaw's marketplace shows a severe security downside | Medium. Owner-configured MCP only; no marketplace |
| 9 | **Brief personalization feedback** (thumbs up or down on brief items to tune topics) | ChatGPT Pulse (1, but flagship) | Pulse is curated this way | High. Buttons plus memory |
| 10 | **Inbox cleanup**: bulk unsubscribe, cold-email blocker | Inbox Zero, Spark Gatekeeper (2) | A common inbox-zero motivation | High. List-Unsubscribe header plus Gmail filters |
| 11 | **Browser agent for errands** (bookings, forms) | ChatGPT agent, Gemini Agent, OpenClaw, Lindy, Claude in Chrome (5) | Mixed: "Sometimes Helpful, Mostly (still) Useless"; usage caps; injection risk | Low-medium. Conflicts with the untrusted-web fencing model |
| 12 | **Multiple messaging channels** (WhatsApp, Signal, Discord) | OpenClaw, Poke, Martin, Coco, HelloAria (5) | Distribution advantage; Toki reportedly lost WhatsApp to policy changes | Low. BRIEF scopes to Telegram; WhatsApp terms and cost [UNVERIFIED] |
| 13 | **Meeting notetaker** | Lindy, Fyxer, Spark (3) | Mixed reviews (Fyxer) | Low. Needs a meeting bot or transcription service outside the allowed APIs |
| 14 | **Acting toward third parties** (texting or calling others, reminders to friends) | Martin, Lindy, Zapia, Coco (4) | Distinctive, but "do stuff when you don't want it to" is the fear | Low. Telephony is a paid service; breaks the no-unattended-sends rule |

---

## (c) What differentiates the winners

1. **Zero-install distribution inside a messenger the user already lives in.**
   - Poke's traction (about 100M messages; first agent approved for Apple Messages for Business) and Zapia's 3.5M users both come from meeting users in iMessage or WhatsApp with a 2-minute onboarding. https://ecosistemastartup.com/?p=85865 , https://appleinsider.com/articles/26/06/04/first-ai-agent-for-messages-business-chat-approved-by-apple , https://latamlist.com/zapia-raises-a-7m-round/ , https://www.unite.ai/zh-cn/poke-review/
   - ClaudeBot has the channel. Its friction is self-hosting setup, which its wizard, pairing code and /connect address.
2. **Proactivity that feels like judgment, not cron.**
   - Users and reviewers separate "texts me first about something that matters" from timed digests. https://www.producthunt.com/p/poke-by-interaction-co/a-week-with-poke-review-a-promising-start-for-a-proactive-ai-assistant?page=3 , https://reddit.sentinel-team.org/posts/1sv3ucz/snapshots/2026-05-01T23%3A40%3A05.297317Z
   - OpenClaw formalized this as heartbeat vs cron. https://www.stanza.dev/courses/openclaw/automation-workflows/openclaw-cron-vs-heartbeat
3. **Triage accuracy, which is the trust bottleneck.** The most repeated complaints across Poke, Fyxer and Alexa+ are misclassification and bad actions, not missing features. https://www.saner.ai/blogs/poke-reviews , https://www.alkmist.com/fyxer-ai-review , https://aichief.com/news/alexa-review-amazons-new-ai-assistant-tested/
   - Winners keep a human in the loop: Martin's review-before-execute, ChatGPT agent confirmations, drafts rather than sends. https://www.eesel.ai/blog/martin-ai-review , https://www.ninetwothree.co/blog/chatgpt-agent-mode
   - Notion's confirm-and-learn labeling is the model for improving accuracy. https://www.notion.com/en-gb/help/guides/organize-your-inbox-with-notion-ai-auto-labeling
4. **Security is now a market differentiator.** OpenClaw, the most direct self-hosted competitor, is publicly associated with malicious skills, credential leaks and prompt injection. https://www.theregister.com/2026/02/05/openclaw_skills_marketplace_leaky_security/ , https://www.techradar.com/pro/here-are-the-openclaw-security-risks-you-should-know-about
   - ClaudeBot's model fits this gap: owner-only, untrusted text fenced, no unattended sends, defanged URLs. It is worth marketing explicitly.
5. **Price and value.** Cost is a top complaint for the premium assistants:
   - Lindy: "expensive", credits drain. https://www.cloudtalk.io/blog/lindy-ai-review/
   - Poke: $199 tier "out of reach". https://www.saner.ai/blogs/poke-reviews
   - Gemini agents: "$100 monthly paywall". https://www.pulse.bot/ai/news/googles-ai-agent-ambitions-are-real-but-remain-locked-behind-a-100-monthly-paywall-25e1f3d8-0f02-40b7-94ac-583809dddca3/
   - ChatGPT Pulse: started at $200/month Pro. https://yourstory.com/ai-story/openai-chatgpt-pulse-pro-daily-briefings
   - A self-hosted, pay-per-token bot with a budget cap and /usage is a credible counter-position.
6. **Platform gravity is squeezing standalone email tools.** Gemini puts AI Inbox, Suggested Replies and scheduling directly in Gmail, partly for free. Siri AI and Alexa+ use device-level personal context. https://blog.google/products-and-platforms/products/gmail/gmail-is-entering-the-gemini-era/ , https://www.eweek.com/news/apple-siri-ai-wwdc-2026/
   - Reddit users note Gmail and Gemini improving fast. https://reddit.sentinel-team.org/posts/1t7c020/snapshots/2026-05-15T18%3A26%3A28.525889Z
   - Standalone products survive on cross-tool orchestration, channel convenience and trust, not on drafting alone.
7. **Churn and fragility.** Some products in the space shut down or retreated:
   - Dot shut down. https://techcrunch.com/2025/09/05/personalized-ai-companion-app-dot-is-shutting-down
   - Notion Mail reportedly sunset [UNVERIFIED]. https://www.notion.com/en-gb/help/guides/organize-your-inbox-with-notion-ai-auto-labeling
   - Toki reportedly dropped WhatsApp [UNVERIFIED]. https://smartcalendars.ai/en/articles/smart-calendars-ai-vs-toki
   - Users explicitly ask for export paths. https://reddit.sentinel-team.org/posts/1sv3ucz/snapshots/2026-05-01T23%3A40%3A05.297317Z
   - Self-hosting with a local SQLite store is a durability selling point.

## Suggested shortlist for ClaudeBot (all fit the BRIEF constraints and can be tested offline with fakes)
1. A heartbeat proactivity engine: judgment-based, quiet by default, and still tap-to-send.
2. Gmail auto-labeling with plain-English rules and confirm-to-learn.
3. Reply and follow-up tracking ("waiting on" and "you owe a reply").
4. Voice-matched auto-drafts attached to inbox alerts.
5. A find-a-time scheduling flow.
6. Forward-to-calendar extraction from email, photo or PDF.
7. Lists.
8. Thumbs up or down feedback on the daily brief.
9. One-tap unsubscribe.
