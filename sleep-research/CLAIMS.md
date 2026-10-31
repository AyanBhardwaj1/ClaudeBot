# Claims audit
Trace: traces/claims/round1.md. Fresh same-family auditor, **provisional**.

| Claim | Verdict | Resolution |
|---|---|---|
| IDEA_REPORT: "voice" listed as a strength | no | Removed; voice notes are unsupported (no speech-to-text API) |
| Landing page: "Free and open source" | no | Now "Free, source on GitHub". **The repo has no LICENSE; the owner must pick one.** |
| README: unattended turns "can't plant anything for later" | partial | Code fix: fired reminders have their links defanged. Wording narrowed to tasks, memories and invites |
| Nudge/Reply drafts "never sent on their own" | partial | Code fix: draft buttons run as not-owner-present, so a send is held for ✅ Send |
| /reminders "everything" | partial | Reworded to every reminder, scheduled task and briefing |
| "Busy weeks read in full (250)" | partial | Reworded: free-time searches and check-ins read up to 250; listings say when they're cut short |
| Check-ins "every few hours", alerts "every 10 minutes" | partial | Test added: jobs run every 3h and 10min |
| "Undo every send", "Only talks to you", phishing "does nothing", "numbers computed with code", "source for each claim" | partial | Landing copy narrowed to what the code enforces |
| /help "lists everything" | partial | /help, /setup and /disable added; a test checks that HELP covers every menu command |
| Welcome: "I'll ping you when important email arrives" | partial | Now "Once Gmail is connected..." |
| Cost table missing the 1.1 Haiku jobs | partial | Check-ins row added |
| "Five minutes", "a few dollars a month", "fraction of a cent" | unverifiable offline | Left as estimates; worth timing a real setup before launch |

Supported with code and tests: drafts-only mode, inbox-down and recovery notices, exact free-time math, restrictions on unattended turns, "nothing sends while you're away", "links inside emails are never opened", the spending cap.
