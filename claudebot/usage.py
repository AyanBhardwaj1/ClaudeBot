"""Estimated API spend per call, running totals, and an optional monthly budget cap."""

from datetime import datetime
from zoneinfo import ZoneInfo

from .db import Database

# USD per million tokens: (input, output, cache read, 5-minute cache write).
# Estimates for the owner's own tracking; the Anthropic Console has the real bill.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
FAMILY_PRICES = {"opus": PRICES["claude-opus-5-5"], "sonnet": PRICES["claude-sonnet-5-5"],
                 "haiku": PRICES["claude-haiku-5-5"]}
FALLBACK_PRICE = PRICES["claude-opus-5-5"]  # unknown models are priced high, never as free
WEB_SEARCH_USD = 0.01  # $10 per 1,000 searches
PER_MILLION = 1_000_000


class BudgetExceeded(RuntimeError):
    pass


def _price(model: str) -> tuple[float, float, float, float]:
    if model in PRICES:
        return PRICES[model]
    for family, price in FAMILY_PRICES.items():
        if family in model:
            return price
    return FALLBACK_PRICE


def _tokens(usage) -> tuple[int, int, int, int, int]:
    server = getattr(usage, "server_tool_use", None)
    return (
        usage.input_tokens or 0,
        usage.output_tokens or 0,
        getattr(usage, "cache_read_input_tokens", None) or 0,
        getattr(usage, "cache_creation_input_tokens", None) or 0,
        (getattr(server, "web_search_requests", None) or 0) if server else 0,
    )


def _token_cost(model: str, fresh: int, output: int, cache_read: int, cache_write: int) -> float:
    input_price, output_price, read_price, write_price = _price(model)
    return (
        fresh * input_price + output * output_price + cache_read * read_price + cache_write * write_price
    ) / PER_MILLION


def estimate_cost(model: str, usage) -> float:
    """Estimated USD for one response.

    When the API ran several steps (compaction, a refusal fallback), `usage.iterations` itemizes
    each one and the top-level counts cover only the last, so sum the steps at their own prices.
    """
    fresh, output, cache_read, cache_write, searches = _tokens(usage)
    iterations = getattr(usage, "iterations", None)
    if not iterations:
        return _token_cost(model, fresh, output, cache_read, cache_write) + searches * WEB_SEARCH_USD
    total = 0.0
    for step in iterations:
        step_model = getattr(step, "model", None) or model  # compaction steps run on the request's model
        step_fresh, step_output, step_read, step_write, _ = _tokens(step)
        total += _token_cost(step_model, step_fresh, step_output, step_read, step_write)
    return total + searches * WEB_SEARCH_USD


class UsageTracker:
    def __init__(self, db: Database, tz: ZoneInfo, monthly_budget: float | None):
        self.db = db
        self.tz = tz
        self.monthly_budget = monthly_budget

    def record(self, response, source: str) -> float:
        cost = estimate_cost(response.model, response.usage)
        fresh, output, cache_read, cache_write, searches = _tokens(response.usage)
        self.db.record_usage(response.model, source, fresh, output, cache_read, cache_write, searches, cost)
        return cost

    def _month_start(self, now: datetime) -> datetime:
        return now.astimezone(self.tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def month_cost(self, now: datetime | None = None, source: str | None = None) -> float:
        now = now or datetime.now(self.tz)
        return self.db.usage_totals(self._month_start(now), source)[1]

    def check_budget(self, now: datetime | None = None) -> None:
        if self.monthly_budget is None:
            return
        spent = self.month_cost(now)
        if spent >= self.monthly_budget:
            raise BudgetExceeded(
                f"Monthly budget reached: ${spent:.2f} of ${self.monthly_budget:.2f}. "
                "Raise MONTHLY_BUDGET_USD to keep going."
            )

    def summary(self, now: datetime | None = None) -> str:
        now = now or datetime.now(self.tz)
        day_start = now.astimezone(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        day_n, day_cost = self.db.usage_totals(day_start)
        month_n, month_cost = self.db.usage_totals(self._month_start(now))
        lines = [
            "Estimated Claude API spend",
            f"- Today: ${day_cost:.2f} ({day_n} requests)",
            f"- This month: ${month_cost:.2f} ({month_n} requests)",
        ]
        if self.monthly_budget is not None:
            lines.append(f"- Monthly budget: ${self.monthly_budget:.2f} "
                         f"(${max(self.monthly_budget - month_cost, 0):.2f} left)")
        lines.append("Exact billing: console.anthropic.com")
        return "\n".join(lines)
