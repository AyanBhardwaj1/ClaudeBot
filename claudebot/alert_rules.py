"""Plain-English inbox alert rules: "never alert me about LinkedIn", "always alert for my landlord".
They are the owner's own words and go to the inbox classifier ahead of its defaults."""

import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .db import Database

RULES_KEY = "alert_rules"
MAX_RULES = 20
MAX_RULE = 150


class AlertRules:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> list[dict]:
        return json.loads(self.db.get_setting(RULES_KEY) or "[]")

    def add(self, text: str) -> dict:
        text = " ".join(text.replace("<", " ").replace(">", " ").split())[:MAX_RULE]
        if not text:
            raise ValueError("A rule needs some words, e.g. never alert me about LinkedIn.")
        rules = self.all()
        if len(rules) >= MAX_RULES:
            raise ValueError(f"That's {MAX_RULES} rules already; remove one first (/rules).")
        rule = {"id": max((r["id"] for r in rules), default=0) + 1, "text": text}
        self.db.set_setting(RULES_KEY, json.dumps(rules + [rule]))
        return rule

    def remove(self, rule_id: int) -> bool:
        rules = self.all()
        kept = [r for r in rules if r["id"] != rule_id]
        self.db.set_setting(RULES_KEY, json.dumps(kept))
        return len(kept) < len(rules)

    def for_classifier(self, owner: str) -> str:
        rules = self.all()
        if not rules:
            return ""
        lines = "\n".join(f"- {r['text']}" for r in rules)
        return f"{owner}'s own alert rules (they override the defaults above):\n{lines}\n\n"


def rules_view(rules: AlertRules) -> tuple[str, InlineKeyboardMarkup | None]:
    items = rules.all()
    if not items:
        return ("No alert rules yet. Add one in plain English:\n/rules never alert me about LinkedIn\n"
                "/rules always alert for anything from my landlord"), None
    lines = ["📏 Your alert rules:"] + [f"{i}. {r['text']}" for i, r in enumerate(items, 1)]
    buttons = [[InlineKeyboardButton(f"✖️ {r['text'][:40]}", callback_data=f"rule:del:{r['id']}")] for r in items]
    return "\n".join(lines) + "\n\nAdd one: /rules <rule>", InlineKeyboardMarkup(buttons)


class RuleHandlers:
    """Mixed into TelegramBot."""

    async def on_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        rules = AlertRules(self.db)
        text = " ".join(context.args or [])
        if text:
            try:
                rule = rules.add(text)
            except ValueError as e:
                await update.effective_message.reply_text(str(e))
                return
            await update.effective_message.reply_text(f"📏 Rule added: {rule['text']}\nIt applies to new email from now on.")
            return
        text, markup = rules_view(rules)
        await update.effective_message.reply_text(text, reply_markup=markup)

    async def on_rule_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not self._from_owner(query):
            await query.answer()
            return
        removed = AlertRules(self.db).remove(int(query.data.split(":")[2]))
        await query.answer("Removed." if removed else "Already gone.")
        text, markup = rules_view(AlertRules(self.db))
        await query.edit_message_text(text, reply_markup=markup)
