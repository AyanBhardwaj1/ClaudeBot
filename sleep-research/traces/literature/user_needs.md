# User needs and pain points: AI personal and email assistants (late 2026)

Prepared 2026-10-31 for the ClaudeBot product team (see `../../BRIEF.md`).

## Method and caveats (read first)

- **25 WebSearch queries** were run (list in the appendix). They covered Reddit (via mirrors), Hacker News, Product Hunt, G2, Trustpilot, the OpenAI community forum, tech press, and vendor blogs, for 2025-2026.
- **WebFetch was blocked by the sandbox network policy.** Hosts that failed: study8677.github.io, blog.saner.ai, frontpage-app.vercel.app. So no page was opened in full. Every "quote" below is a **short phrase from the search tool's result snippets**, not checked verbatim against the page. Treat quoted wording as near-verbatim at best.
- **Reddit came through a third-party mirror** (reddit.sentinel-team.org). The search snippets did not say which mirror URL held which comment. Where a claim rests on those threads, I list the mirror URLs from that result set and tag the claim **[mirror; post-to-claim mapping UNVERIFIED]**.
- **Many results are vendor blogs** that sell a competing or managed product. They are tagged **[vendor]**. They are good evidence of what is being marketed and weak evidence of real demand.
- **How the ranking was done:** I judged frequency (how many separate queries or sources surfaced the theme) and intensity (money lost, data leaked, or the user quitting) qualitatively. No counts were collected.

---

## (a) Top 15 user needs and pain points (ranked)

### 1. Reliability: silent failures, false "done" reports, broken reminders
This is the most common theme across products. Users leave once they can't predict what the agent will do.
- OpenClaw reviewers say it "sometimes reports success when it hasn't actually completed the task", that failing skills "often fail silently", and that only "5 of 15 skills worked properly." https://dev.to/likhit/i-spent-47-testing-openclaw-for-a-week-heres-whats-actually-happening-4j2b , https://dev.to/yoges/openclaw-in-production-the-reality-behind-347k-github-stars-163m (exact attribution between these review pages UNVERIFIED)
- ChatGPT Tasks: a Reddit commenter said it is "not reliable" and recommended Google Assistant or a phone alarm for appointments. How-To Geek / Tom's Guide found recurring reminders stopping after two entries and "nonsensical timeframes." https://www.tomsguide.com/ai/i-tried-chatgpt-tasks-and-im-sticking-with-siri-for-now-heres-why , https://community.openai.com/t/chatgpt-tasks-gpt-4o-with-scheduled-tasks-broken/1091150 , https://reddit.sentinel-team.org/posts/1q0xulg/snapshots/2026-01-01T13%3A58%3A15.04925Z [mirror; mapping UNVERIFIED]
- An article on abandonment argues users stop when they "cannot form a reliable model of what the agent will do." https://audienceintelligence.pages.dev/articles/4-reasons-users-abandon-ai-agent-fix.html

### 2. Fear of wrong or autonomous sends, and invented commitments in email
Users hold this fear intensely. Email is hard to undo, so the stated preference is "draft, human sends."
- Reddit posters say one hallucinated commitment to a customer costs more than the tool saves. One commenter has seen founders "burned by fully autonomous setups." https://reddit.sentinel-team.org/posts/1sj7qtz/snapshots/2026-04-17T22%3A56%3A48.086887Z , https://reddit.sentinel-team.org/posts/1s2mc82/snapshots/2026-03-27T16%3A20%3A19.954082Z [mirror; mapping UNVERIFIED]
- Human-in-the-loop guides warn of the failure where "nothing sat between the LLM and the send button," and say plain approve/reject is not enough because reviewers "need to adjust tone or correct a detail." https://cli.nylas.com/guides/build-human-in-loop-email-agent , https://www.zoho.com/agentinbox/articles/human-approval-loops-ai-email-agents.html [vendor]

### 3. Runaway cost and token burn
This dominates complaints about OpenClaw/Clawdbot. It mostly comes from background polling and "heartbeat" jobs running on expensive models.
- Notebookcheck reports about 25 overnight Opus calls asking "is it daytime yet" at roughly $0.75 each, and c't spending over $100 in one day. https://www.notebookcheck.net/18-75-overnight-to-ask-Is-it-daytime-yet-The-absurd-economics-of-OpenClaw-s-token-use.1219925.0.html
- A $623/month bill from 5-minute heartbeats. https://zeroclaw.pages.dev/blog/hidden-costs-of-ai-agents [vendor]
- An HN thread listing includes "burning too many tokens." https://frontpage-app.vercel.app/newest/46838946 (seen only as a snippet)

### 4. Setup friction and maintenance burden
- OpenClaw reviewers report about 12 hours, and about 15 hours over four sessions, to get one agent stable. One concluded it is "probably not worth it for most founders right now." https://little-might.pages.dev/openclaw-review/ , https://aimaker.substack.com/p/openclaw-review-setup-guide
- "Installation failed due to sandboxing" (HN). A Turkish guide calls installation troublesome. https://frontpage-app.vercel.app/newest/46838946 , https://lilys.ai/notes/tr/unreal-engine-5-20260221/clawdbot-was-missing
- Advice to "pin your version and wait 48 hours before applying updates." https://dev.to/yoges/openclaw-in-production-the-reality-behind-347k-github-stars-163m

### 5. Drafts that don't sound like me (tone and voice)
- Product Hunt: "Vanilla AI drafted emails are all terrible and without tuning to my previous emails they don't provide me any value." https://www.producthunt.com/p/fyxer/what-fyxer-alternative-do-you-know-that-is-good
- A reviewer said the drafts didn't "feel" like how they would respond, and were "quite basic." https://efficient.app/apps/fyxer
- A Reddit user (via eesel) said that after a year the "drafts no longer sound 'right'" and that personality can't be adjusted. https://www.eesel.ai/blog/fyxer-ai-reviews [vendor-adjacent]
- Separately, users like AI as a tone checker before they send. One runs "basically every important email" through ChatGPT for tone. https://reddit.sentinel-team.org/posts/1qgh6rp/snapshots/2026-01-19T22%3A01%3A19.602329Z [mirror; mapping UNVERIFIED]

### 6. Memory: forgetting context, or dragging in irrelevant old context
Complaints run both ways.
- One user says it "forgets what we chatted about in the same thread after no more than 3-4 prompts." Memory "does not seem to update properly, even when I explicitly ask." https://community.openai.com/t/4o-model-ruined-after-updates/1119804 , https://reddit.sentinel-team.org/posts/1r84upx/snapshots/2026-02-18T20%3A22%3A07.430425Z [mirror; mapping UNVERIFIED]
- Overreach: it "keeps dragging in old stuff that's totally irrelevant" and "ends up making assumptions instead of asking." One workaround: "given up on chatgpt's built-in memory and just paste a context block." https://reddit.sentinel-team.org/posts/1six7vd/snapshots/2026-04-17T18%3A20%3A09.692309Z , https://reddit.sentinel-team.org/posts/1rj4rjx/snapshots/2026-03-04T15%3A00%3A28.593799Z [mirror; mapping UNVERIFIED]

### 7. Follow-up tracking ("waiting on reply") and nudges
Every major email tool now ships this as a feature, which suggests strong demand. The evidence is mostly vendor pages.
- Superhuman's Remind Me defaults to "if no reply." Inbox Zero has an "Awaiting Reply" view with a "Nudge" button that drafts a polite follow-up. Fyxer tracks sent mail with no reply. https://help.superhuman.com/hc/en-us/articles/45265917418259-Follow-Up-Faster , https://www.getinboxzero.com/blog/post/how-to-see-all-emails-waiting-for-reply , https://support.fyxer.com/article/track-email-follow-ups [vendor]
- OpenClaw-ecosystem workflows for Gmail follow-up reminders. https://www.betterclaw.io/workflows/follow-up-reminder [vendor]

### 8. Too verbose, sycophantic, or hedging
- "ChatGPT's answers too long, verbose and a lot of noises." "I am tired of prompting 'answer in concise manner'." Claude "seems to only say what needs to be said." https://reddit.sentinel-team.org/posts/1sgpr3v/snapshots/2026-04-10T15%3A43%3A25.232209Z , https://reddit.sentinel-team.org/posts/1s4iakh/snapshots/2026-03-27T16%3A20%3A19.954082Z [mirror; mapping UNVERIFIED]
- The swing from sycophancy to contrarianism: "now it seems to disagree just to disagree." https://aiproductivity.ai/news/chatgpt-sycophancy-problem-persists-2026/

### 9. Notification overload and unwanted proactivity
- Gmail's unrequested Gemini summaries were "distracting." Turning them off also removes smart features such as inbox categories. https://reddit.sentinel-team.org/posts/1qfmcj9/snapshots/2026-01-19T18%3A20%3A25.249359Z [mirror] , https://www.itpro.com/software/google-is-overhauling-gmail-with-new-gemini-ai-features-heres-how-to-turn-them-off
- OpenClaw guides recommend quiet hours, batching, and a silent "nothing to report" token. One puts the healthy level at about 3-5 proactive messages a day. https://clawdocs.org/guides/heartbeat , https://dev.to/hex_agent/openclaw-heartbeats-making-your-ai-agent-proactive-instead-of-reactive-2pi5 [community docs]
- I found no direct user complaint about too many pings from Poke or OpenClaw. **[UNVERIFIED as a user complaint; inferred from guidance]**

### 10. Proactive reminders and deadline check-ins (students)
- An OpenAI community user asked for "reminders or subtle notifications for important tasks" for students who plan study in ChatGPT. https://community.openai.com/t/request-suggestion-to-the-developers/1115355
- StudentClaw on Product Hunt: agents "that can message you first instead of waiting for you to open an app," for deadlines and exams. https://www.producthunt.com/products/studentclaw
- A MyStudyLife AI review says users want reminders that are more customizable. https://buildaiq.com/blog/92rcb9w5rlcrfs6-mrhgm-xj9b4-fc7c3-mhw4z-whw8c-k5lhh-m9ler-93c27-zscy4-fgx3m-3jtlm-djs7g-b5bkx
- I found no direct "I wish..." quotes from students on Reddit. **[UNVERIFIED demand strength]**

### 11. Hallucinated facts and wrong summaries
- Tom's Guide: Gemini in Gmail listed newsletters as the user's most-discussed topics. https://www.tomsguide.com/ai/i-am-using-gemini-now-for-my-gmail-and-theres-one-major-discovery-thats-surprising
- A Reddit user said the bot apologized for a hallucination without fixing it, and concluded it was "far from reliable." https://reddit.sentinel-team.org/posts/1tpdp7j/snapshots/2026-05-30T02%3A41%3A26.708778Z [mirror; mapping UNVERIFIED]
- The NewsGuard 2025 audit found chatbots repeating false claims 35% of the time, up from 18% (cited by a vendor). https://www.groovehq.com/blog/how-helply-ai-eliminates-hallucination [vendor citing third party]

### 12. Fits into existing channels, not "another tab"
- One user says AI that sits apart from their workflow becomes "another tab, another context switch," and they abandon it. https://reddit.sentinel-team.org/posts/1rpk86k/snapshots/2026-03-10T19%3A13%3A03.595731Z [mirror; mapping UNVERIFIED]
- "The hard part isn't generating text, it's reliability and actually fitting into existing workflows." "Specialized tools that handle one thing well tend to stick." https://reddit.sentinel-team.org/posts/1t12niv/snapshots/2026-05-02T04%3A02%3A18.821067Z [mirror; mapping UNVERIFIED]

### 13. Meeting prep briefs
- The pain behind Brief My Meeting: "before each call, I'd spend time Googling attendees and digging through emails." Fireflies sends prep 1 hour ahead and warns that briefs may not arrive for meetings added with under 30 minutes' notice. https://www.producthunt.com/posts/brief-my-meeting , https://guide.fireflies.ai/articles/3878280311-meeting-prep-get-briefed-before-every-meeting
- Littlebird's own survey: 89% said meeting notes reduced their "anxiety about dropping the ball." https://littlebird.ai/blog/ai-meeting-prep [vendor survey]

### 14. Life-admin extraction from email: bills, subscriptions, packages, travel
The evidence is product positioning only, not demand data. **[demand UNVERIFIED]**
- Apps parse bills, send renewal reminders, and flag price increases. EasilyDo does shipping updates and flight gate changes. Yuki auto-syncs itineraries from booking emails. Edison does bill-due reminders. https://apps.apple.com/app/hawksubber/id6747628748 , https://www.edisonmail.com/features/edison-mail-assistant , https://apps.apple.com/app/id6759008814
- A Poke reviewer liked that it "flags flight changes." https://www.producthunt.com/p/general/a-week-with-poke-review-a-promising-start-for-a-proactive-ai-assistant

### 15. Relationship reminders and a personal CRM (birthdays, check-ins, gift ideas)
These are mostly product pages. **[demand UNVERIFIED]**
- Birthday auto-reminders, "relationship warmth tracking," and updating contacts in natural language through your AI assistant (Mob). OpenClaw skills exist for a personal CRM. https://getdex.com/blog/top-10-best-personal-crm-apps-in-2026-to-up-your-networking-game , https://alternativeto.net/software/mob-personal-crm/about/ , https://getclawkit.com/skills/official-matthewpoe-personal-crm
- Users also asked for assistants that handle "notes, tasks, calendar, emails, reminders, contacts." https://reddit.sentinel-team.org/posts/1qq97t2/snapshots/2026-01-29T14%3A25%3A03.043845Z [mirror; mapping UNVERIFIED]

**Honorable mentions (thin evidence):**
- Hard caps, such as ChatGPT Tasks' 10 active tasks. https://www.tomsguide.com/ai/chatgpt/chatgpt-tasks-has-replaced-my-reminder-app-heres-5-prompts-to-try (the cap comes from a snippet aggregating several articles)
- Reminders breaking when their chat is deleted, and a request for a dedicated reminders page. https://community.openai.com/t/chatgpt-tasks-gpt-4o-with-scheduled-tasks-broken/1091150
- Outlook users getting fewer features than Gmail users. https://www.eesel.ai/blog/fyxer-ai-reviews
- Journaling through Telegram as what finally made the habit stick (a single anecdote). https://dev.to/reeddev42/i-replaced-my-journaling-app-with-an-ai-that-talks-back-2369

---

## (b) Top 10 "delight" features users rave about

1. **No app to install; it lives in the messaging app you already use.** A Poke Product Hunt reviewer said they "didn't need to download a new app" and that reminders arrive in their existing messenger. Saner calls it "a brilliant interface attached to an incomplete product." https://www.producthunt.com/products/poke-by-interaction-co/reviews , https://www.saner.ai/blogs/poke-reviews
2. **Real proactivity: it messages you first.** "Finally proactive instead of just reactive." Pings "when a thread it's watching moves." https://www.producthunt.com/p/general/a-week-with-poke-review-a-promising-start-for-a-proactive-ai-assistant
3. **A morning briefing pushed to chat** (weather, calendar, tasks, headlines). Repeatedly called the most popular first OpenClaw setup, "useful from day one." https://openclawinstall.pages.dev/blog/use-case-daily-morning-briefing , https://getclawdbot.pages.dev/showcase/daily-briefings , https://git.cynarski.dev/Awesome/awesome-openclaw-usecases/src/branch/main/usecases/custom-morning-brief.md [vendor/community; "most popular" is UNVERIFIED]. A Reddit user also describes a daily news briefing pushed to their chat app. https://reddit.sentinel-team.org/posts/1qq97t2/snapshots/2026-01-29T14%3A25%3A03.043845Z [mirror]
4. **Native-feeling messaging: reactions and voice notes understood.** Poke "can see your iMessage reactions, understands voice notes." https://www.producthunt.com/products/poke-by-interaction-co/reviews
5. **Drafts that learned my voice.** A G2 reviewer: it "learned my business within 2 weeks. It drafts the email for me, as I would have written and better." https://www.g2.com/products/fyxer/reviews
6. **Calendar and scheduling automation that saves back-and-forth.** An OpenClaw reviewer reports "approximately 2-3 hours" a week saved after a 30-minute Google Calendar hookup. https://aimlapi.com/blog/openclaw-review-real-world-use-setup-on-a-5-vps-and-what-actually-works (attribution among review pages in that result set UNVERIFIED)
7. **Build-a-workflow-from-chat.** One user asks for a Todoist workflow and the agent builds and runs it from Telegram. https://www.kimi.ai/resources/openclaw-use-cases , https://thesolai.github.io/guides/awesome-openclaw-usecases.html [community list]
8. **One-tap "Nudge" follow-up drafts on threads awaiting a reply.** https://www.getinboxzero.com/blog/post/how-to-see-all-emails-waiting-for-reply [vendor]
9. **Pre-meeting briefs delivered automatically.** For example, emailed four hours before external meetings. https://www.producthunt.com/posts/brief-my-meeting , https://peerpush.com/p/brief-my-meeting
10. **Voice-note journaling and habit check-ins in chat, with streaks and follow-ups when you go quiet.** https://operator.io/habit-tracker , https://dev.to/reeddev42/i-replaced-my-journaling-app-with-an-ai-that-talks-back-2369 , https://www.getfolk.app/use-cases/ai-journaling-companion.md [vendor plus one anecdote]

---

## (c) Top 5 trust and safety concerns

1. **Prompt injection through email, leading to data exfiltration.**
   - Radware's "Shadow Leak": a hidden email instruction made ChatGPT Deep Research exfiltrate Gmail data. https://brainai-pro.pages.dev/news/en/2025/09/19/shadow-leak-shows-how-chatgpt-agents-can-exfiltrate-gmail-data-via-prompt-inject , https://beyondmachines.net/event_details/service-side-prompt-injection-exfiltration-vulnerability-reported-in-chatgpt-s-deep-research-agent-0-u-p-o-i
   - A Superhuman AI exfiltration flaw (PromptArmor, January 2026). https://www.webpronews.com/superhuman-ai-email-vulnerability-enables-stealthy-data-exfiltration
   - Gemini Gmail summaries tricked by hidden prompts. https://www.androidcentral.com/apps-software/turns-out-gmails-ai-email-summaries-arent-as-secure-as-we-thought
   - An HN experiment: "4,000 emails from 1,600 senders" in three days, all trying to make an agent leak a secret. https://fernandoi-cl.pages.dev/posts/hackmyclaw/
2. **Self-hosted does not mean secure: exposed instances and leaked keys.**
   - 923 Clawdbot gateways "completely exposed," plus a default bind to "all" that users set without realizing. https://www.notebookcheck.net/From-hype-to-wallet-drain-OpenClaw-can-quietly-burn-hundreds-of-Dollars-per-day.1219925.0.html
   - 21,639 exposed instances, of which more than 1,800 leaked API keys or chat history, and CVE-2026-25253 (CVSS 8.8, per a vendor). https://zeroclaw.pages.dev/blog/hidden-costs-of-ai-agents [vendor; figures UNVERIFIED]
   - "Private by architecture only until you misconfigure the door." https://dev.to/yankoaleksandrov/building-a-private-ai-assistant-in-2026-no-cloud-required-mostly-3d46
3. **Unreviewed autonomous actions.** Wrong sends, invented commitments, and false "success" reports (see a1 and a2). Users want an approve or edit step before any outbound action. https://cli.nylas.com/guides/build-human-in-loop-email-agent , https://reddit.sentinel-team.org/posts/1sj7qtz/snapshots/2026-04-17T22%3A56%3A48.086887Z [mirror]
4. **Cloud data exposure and over-broad OAuth scopes.**
   - "Every email you paste into a cloud AI assistant is potentially logged, used for training…" https://memx.app/blog/run-llms-locally-ollama-offline-privacy/
   - Connecting Google grants access to Gmail, Calendar, and Drive. https://www.eesel.ai/blog/instinct-ai-for-email-management
   - Lemmy user: "I wouldn't trust an llm solution with sensitive information unless I host it myself." https://old.lemmy.dbzer0.com/post/20832651
   - Poke's security protections "remain company-stated." https://www.layer3labs.io/guides/poke-ai-explained
5. **Uncontrolled spend as a safety issue.** Background loops can run up bills overnight. Users ask for hard provider-level caps and cheaper models for background jobs. https://www.notebookcheck.net/18-75-overnight-to-ask-Is-it-daytime-yet-The-absurd-economics-of-OpenClaw-s-token-use.1219925.0.html , https://coclawcom.pages.dev/blog/openclaw-cost-api-challenges [vendor]

---

## Implications for ClaudeBot (analyst inference, not sourced)

**Already covered:**
- Tap-to-send and the Undo window (a2, c3).
- Untrusted-text fencing (c1).
- Owner-only access (c2).
- Budget cap and /usage (a3, c5).
- Haiku for triage (a3).
- Daily brief (b3).
- Telegram-native voice notes (b1, b4).
- Setup wizard (a4).

**Likely gaps worth testing:**
- "Waiting on reply" tracking with Nudge drafts (a7, b8).
- Pre-meeting briefs from Calendar and Gmail (a13, b9).
- Quiet hours, batching and a silent no-news rule for proactive alerts (a9).
- Voice or style learning from sent mail (a5, b5).
- Verified completion: confirming tool results instead of claiming success (a1).
- A reminders list view (a1).
- Bills, subscriptions, package and travel extraction from Gmail (a14).
- Contact and birthday reminders (a15).
- Concise-by-default replies (a8).
- A security self-check in /status for bind address, token storage and OAuth scopes (c2, c4).

---

## Appendix: queries run (25)
1. reddit AI email assistant frustrations wrong tone hallucinated 2025
2. what do you actually use your AI personal assistant for daily reddit 2026
3. Clawdbot OpenClaw users feature requests complaints Hacker News
4. Poke AI assistant iMessage review users love
5. ChatGPT Tasks feature requests complaints reminders unreliable reddit
6. why I stopped using AI assistant forgets context too chatty notifications abandoned
7. r/selfhosted self-hosted AI assistant privacy email access Telegram bot
8. AI assistant follow-up tracking "waiting on reply" emails remind me if no response
9. Hacker News AI email agent Gmail access privacy "prompt injection" personal assistant 2026
10. OpenClaw use cases users love morning briefing Telegram what people use it for
11. students AI assistant wishlist deadlines reminders reddit "I wish" assistant would
12. Product Hunt reviews AI email assistant Fyxer Superhuman complaints drafts don't sound like me
13. OpenClaw token cost expensive API bill security exposed instances complaints
14. AI assistant track subscriptions bills package tracking travel itinerary from email users want
15. ChatGPT memory forgets context annoying complaints reddit personal assistant "remember"
16. AI personal assistant relationship reminders contacts birthdays "personal CRM" users want
17. Gemini in Gmail complaints summaries useless wrong reddit r/gmail 2025
18. proactive AI assistant too many notifications annoying pings Poke OpenClaw heartbeat spam
19. r/LocalLLaMA why self-host personal assistant privacy don't trust cloud with my email
20. AI meeting prep brief before meeting attendees context assistant users rave
21. "Is OpenClaw worth the hype" review setup took hours what worked what didn't
22. AI assistant journaling habit tracking voice notes Telegram users reddit love daily check-in
23. AI email assistant "approve before sending" human in the loop draft never auto-send users prefer
24. ChatGPT too verbose sycophantic long answers annoying "just answer" reddit 2025 2026
25. Poke Interaction Company Hacker News discussion texting assistant privacy pricing negotiation

**Fetch attempts that failed (network policy):** study8677.github.io (OpenClaw user-demand report), blog.saner.ai (Poke reviews), frontpage-app.vercel.app (HN thread mirror). Allowing these hosts would let the quotes be checked verbatim.
