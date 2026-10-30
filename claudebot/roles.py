"""Occupation profiles: tailor the assistant, inbox alerts, the daily brief and suggestions to
what the owner does for a living.

Like personality modes, a profile reaches the agent as a mid-conversation system message, so the
system prompt (and with it the conversation history and prompt cache) never changes.
"""

from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .db import Database

ROLE_KEY = "role"
DETAIL_KEY = "role_detail"
MAX_DETAIL = 150


@dataclass(frozen=True)
class Role:
    key: str
    label: str
    guidance: str  # how the assistant should work for this job
    inbox_priorities: str  # what deserves an inbox alert
    brief_focus: str  # what the daily brief adds
    starters: tuple[str, ...]  # one-tap setups offered when the role is chosen


ROLES = {
    "student": Role(
        "student", "🎓 Student",
        "Prioritize classes, assignments, exams and deadlines, professors and TAs, internships and "
        "recruiting. Help them learn: explain step by step, quiz them, make study guides and plans "
        "around due dates. Emails to professors should be brief and polite. Don't write graded work "
        "for them to hand in as their own; help them understand, outline and check it instead.",
        "professors, TAs, the registrar or financial aid, changes to deadlines or exams, internship "
        "and recruiting emails",
        "anything due or any exam in the next 7 days",
        ("Every Sunday 6pm: my week ahead", "Make a study plan for my exams", "Find internships to apply to"),
    ),
    "engineer": Role(
        "engineer", "💻 Engineer",
        "Prioritize incidents and on-call, code reviews, their manager and team, and recruiter "
        "outreach. Be technically precise, show code when it helps, and use the code workbench to "
        "check numbers or logic. Status updates: what shipped, what's blocked, what's next.",
        "incidents and monitoring alerts, code review requests, their manager or teammates, recruiters",
        "meetings today, and anything urgent from work email (incidents, reviews waiting on them)",
        ("Weekly: AI and dev tools news", "Prep me for my next 1:1", "Draft my weekly status update"),
    ),
    "founder": Role(
        "founder", "🚀 Founder",
        "Prioritize investors, customers, hiring and cash. Be crisp and numbers-first; flag risks "
        "early. Drafts to investors and customers should be short, specific and confident.",
        "investors, customers and partners, candidates they're hiring, legal, banking or payroll",
        "investor and customer emails waiting on a reply",
        ("Weekly: news on my competitors", "Draft a monthly investor update", "Build a fundraising tracker"),
    ),
    "sales": Role(
        "sales", "📈 Sales",
        "Prioritize prospect and client replies, follow-ups that are due, and meetings. Help with "
        "call prep, objection handling, crisp follow-up emails and keeping deal notes straight.",
        "replies from prospects and clients, contract or deal changes, meeting requests",
        "prospect replies waiting on them and today's calls",
        ("Draft follow-ups for today", "Prep me for my next call", "Weekly: news on my accounts"),
    ),
    "healthcare": Role(
        "healthcare", "🩺 Healthcare",
        "Prioritize shifts and schedule changes, credentialing and time-sensitive messages. For "
        "clinical questions, cite current guidelines, say what's uncertain, and never stand in for "
        "clinical judgment. Keep patient-identifying details out of emails unless they ask.",
        "shift or schedule changes, credentialing and licensing, messages from colleagues or clinics",
        "today's shifts and anything time-sensitive",
        ("Weekly: new guidelines in my field", "Plan my shifts this week", "Summarize a paper for me"),
    ),
    "legal": Role(
        "legal", "⚖️ Legal",
        "Prioritize deadlines and filings, clients and opposing counsel. Be precise, cite sources, "
        "note the jurisdiction and flag uncertainty. Drafts should be careful and conservative.",
        "court or filing deadlines, clients, opposing counsel, bar or CLE notices",
        "deadlines and filings coming up this week",
        ("Weekly: legal news in my area", "List my deadlines this week", "Summarize a long contract"),
    ),
    "teacher": Role(
        "teacher", "🍎 Teacher",
        "Prioritize parents, administration and schedule changes. Help plan lessons, write quizzes, "
        "rubrics and handouts (as real documents via the workbench), and draft warm, clear notes "
        "to parents.",
        "parents, administration, schedule or room changes, deadlines for grades or reports",
        "classes and meetings today, and anything parents or admin are waiting on",
        ("Make a quiz for my class", "Plan next week's lessons", "Draft a note to parents"),
    ),
    "creator": Role(
        "creator", "🎬 Creator",
        "Prioritize brand deals, collaborations and platform notices. Help with content ideas, "
        "hooks, titles, posting schedules and pitch emails; keep an eye on trends in their niche.",
        "brand deal and sponsorship offers, collaboration requests, platform policy or payout notices",
        "deal emails waiting on them and what's trending in their niche",
        ("Weekly: trends in my niche", "Brainstorm 10 video ideas", "Draft a brand pitch"),
    ),
    "finance": Role(
        "finance", "💹 Finance",
        "Prioritize markets, deals, deadlines and compliance. Be numbers-first and precise; use the "
        "code workbench for calculations and models; flag assumptions and risks.",
        "deal and client emails, compliance or regulatory notices, deadlines from their team",
        "market-moving news and anything time-sensitive from work",
        ("Daily: market open briefing", "Build a model from my data", "Weekly: deals in my sector"),
    ),
}

ALIASES = {
    "student": "student", "undergrad": "student", "grad": "student", "phd": "student",
    "engineer": "engineer", "software": "engineer", "swe": "engineer", "developer": "engineer",
    "programmer": "engineer", "dev": "engineer",
    "founder": "founder", "cofounder": "founder", "co-founder": "founder", "ceo": "founder",
    "sales": "sales", "salesperson": "sales", "account": "sales", "sdr": "sales", "bdr": "sales",
    "healthcare": "healthcare", "doctor": "healthcare", "nurse": "healthcare", "physician": "healthcare",
    "resident": "healthcare", "pharmacist": "healthcare", "medical": "healthcare",
    "legal": "legal", "lawyer": "legal", "attorney": "legal", "paralegal": "legal",
    "teacher": "teacher", "educator": "teacher",
    "creator": "creator", "youtuber": "creator", "influencer": "creator", "streamer": "creator",
    "finance": "finance", "banker": "finance", "analyst": "finance", "trader": "finance",
    "investor": "finance",
    # Two-word titles are matched before single words.
    "software engineer": "engineer", "data scientist": "engineer", "medical student": "student",
    "law student": "student", "content creator": "creator", "account executive": "sales",
}

CUSTOM = Role(
    "custom", "💼 Your job",
    "Tailor priorities, examples and drafts to their work as described. Ask what matters most to "
    "them in their job if it isn't clear.",
    "anything time-sensitive or important for their work",
    "anything urgent for their work today",
    ("What can you do for my job?", "Set up a weekly work briefing", "Draft my weekly update"),
)


def _clean(text: str) -> str:
    return " ".join(text.replace("<", " ").replace(">", " ").split())[:MAX_DETAIL]


@dataclass(frozen=True)
class Profile:
    role: Role
    detail: str

    def describe(self) -> str:
        if self.role.key == "custom":
            return self.detail
        return f"{self.role.label.split(' ', 1)[1]}" + (f" ({self.detail})" if self.detail else "")

    @property
    def signature(self) -> str:
        return f"{self.role.key}|{self.detail}"

    def system_message(self, owner: str) -> str:
        return f"Profile: {owner}'s job is {self.describe()}. {self.role.guidance}"


def set_role(db: Database, text: str) -> Profile:
    """From "/role student CS at UT Austin", "nurse", or any job description."""
    cleaned = _clean(text)
    words = cleaned.split()
    key, used = None, 0
    for size in (2, 1):  # "software engineer at Google" before "software ..."
        if len(words) >= size and " ".join(words[:size]).lower() in ALIASES:
            key, used = ALIASES[" ".join(words[:size]).lower()], size
            break
    if key is None:
        db.set_setting(ROLE_KEY, "custom")
        db.set_setting(DETAIL_KEY, cleaned)
        return Profile(CUSTOM, cleaned)
    detail = " ".join(words[used:])
    db.set_setting(ROLE_KEY, key)
    db.set_setting(DETAIL_KEY, detail)
    return Profile(ROLES[key], detail)


def pick_role(db: Database, key: str) -> Profile | None:
    """A preset chosen from the picker buttons."""
    if key not in ROLES:
        return None
    db.set_setting(ROLE_KEY, key)
    db.set_setting(DETAIL_KEY, "")
    return Profile(ROLES[key], "")


def clear_role(db: Database) -> None:
    db.delete_setting(ROLE_KEY)
    db.delete_setting(DETAIL_KEY)


def current_profile(db: Database) -> Profile | None:
    key = db.get_setting(ROLE_KEY)
    if key is None:
        return None
    role = CUSTOM if key == "custom" else ROLES.get(key)
    return Profile(role, db.get_setting(DETAIL_KEY) or "") if role else None


def role_keyboard() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(role.label, callback_data=f"role:{key}") for key, role in ROLES.items()]
    return InlineKeyboardMarkup([buttons[i : i + 3] for i in range(0, len(buttons), 3)])
