"""Personality modes, and fencing for text that comes from someone other than the owner.

A mode switch is sent as a mid-conversation `role: "system"` message rather than an edit to the
system prompt: the prompt stays byte-identical, so the conversation history and the prompt cache
stay valid.
"""

from .db import Database

MODE_KEY = "mode"
DEFAULT_MODE = "default"

MODES = {
    "default": (
        "😌 Default",
        "Mode change: back to your default style - calm, sharp, quietly witty, brief.",
    ),
    "fun": (
        "😈 Fun",
        "Mode change: FUN mode. Be the funny friend who happens to know everything: witty "
        "one-liners, playful roasts of the owner (never cruel, never about their looks or "
        "identity), bold opinions with a wink, an emoji when it lands. Stay accurate and useful: "
        "the joke rides on top of the answer, never instead of it. Emails you write still use "
        "the owner's own voice, and every security rule still applies.",
    ),
    "brief": (
        "⚡ Brief",
        "Mode change: BRIEF mode. Answer in as few words as possible, one line when you can. "
        "No preamble, no sign-off.",
    ),
    "deep": (
        "🧠 Deep",
        "Mode change: DEEP mode. Give thorough answers: explain the reasoning, the trade-offs and "
        "what you're unsure of. Verify facts with web search and cite sources. Longer is fine.",
    ),
}


def current_mode(db: Database) -> str:
    mode = db.get_setting(MODE_KEY)
    return mode if mode in MODES else DEFAULT_MODE


def set_mode(db: Database, name: str) -> bool:
    if name not in MODES:
        return False
    db.set_setting(MODE_KEY, name)
    return True


def mode_message(name: str) -> dict:
    return {"role": "system", "content": MODES[name][1]}


def fence_external(tag: str, author: str, text: str) -> str:
    """Wrap text written by someone else so it can't pose as the owner or close its own fence."""
    safe_author = " ".join(author.split()).replace('"', "'").replace("<", "‹").replace(">", "›")[:80]
    safe_text = text.replace("<", "‹").replace(">", "›")
    return f'<{tag} from="{safe_author}">\n{safe_text}\n</{tag}>'
