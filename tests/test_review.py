"""Weekly review and daily-brief feedback."""

from types import SimpleNamespace

from helpers import make_config


def make_bot(tmp_path, monkeypatch):
    from claudebot.bot import TelegramBot

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    bot = TelegramBot(make_config(tmp_path, telegram_token="123:abc"))
    sent, asked = [], []

    async def send_to_owner(text, reply_markup=None):
        sent.append((text, reply_markup))

    async def ask_agent(content, owner_present=True, effort=None):
        asked.append((content[0]["text"], owner_present))
        return "You had a good week."

    bot.send_to_owner = send_to_owner
    bot._ask_agent = ask_agent
    return bot, sent, asked


async def test_weekly_review_runs_unattended_and_can_be_turned_off(tmp_path, monkeypatch):
    bot, sent, asked = make_bot(tmp_path, monkeypatch)
    await bot._weekly_review_job(None)
    assert "action_log" in asked[0][0] and asked[0][1] is False and sent[-1][0].startswith("🗓 Your week")
    bot.db.set_setting("weekly_review", "off")
    await bot._weekly_review_job(None)
    assert len(asked) == 1


async def test_brief_has_feedback_buttons_and_feedback_becomes_a_memory(tmp_path, monkeypatch):
    bot, sent, _ = make_bot(tmp_path, monkeypatch)
    await bot._send_brief()
    datas = [b.callback_data for row in sent[-1][1].inline_keyboard for b in row]
    assert datas == ["brief:good", "brief:tune"]

    async def answer(text=None):
        pass

    def tap(data, user_id=1):
        return SimpleNamespace(callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id), data=data,
                                                              answer=answer))

    await bot.on_brief_button(tap("brief:tune", user_id=999), None)
    assert bot._awaiting() is None
    await bot.on_brief_button(tap("brief:tune"), None)
    message = SimpleNamespace(text="skip the headlines <please>", forward_origin=None)
    assert await bot.handle_answer(message)
    facts = [m["text"] for m in bot.db.list_memories()]
    assert facts == ["Daily brief preference: skip the headlines please"]
    await bot.on_brief_button(tap("brief:good"), None)
    assert bot.db.get_setting("brief_thumbs_up") == "1"


async def test_review_is_scheduled_for_sunday_evening(tmp_path, monkeypatch):
    bot, _, _ = make_bot(tmp_path, monkeypatch)
    bot.db.set_setting("onboarded", "1")
    daily = {}

    async def noop(*a, **k):
        pass

    def run_daily(job, time, days=tuple(range(7)), name=None):
        daily[name] = (time.hour, days)

    app = SimpleNamespace(job_queue=SimpleNamespace(run_daily=run_daily, run_repeating=lambda *a, **k: None),
                          bot=SimpleNamespace(set_my_commands=noop))
    bot.outbox.resume = noop
    await bot._post_init(app)
    assert daily["weekly-review"] == (18, (0,))



async def test_newsletter_digest_is_opt_in(tmp_path, monkeypatch):
    bot, sent, _ = make_bot(tmp_path, monkeypatch)
    ran = []

    async def run_agent(content, owner_present=True, effort=None, live=False):
        ran.append((content[0]["text"], owner_present))
        return "1. AI news", True

    bot._run_agent = run_agent
    bot.google.is_connected = lambda: True
    await bot._digest_job(None)
    assert ran == []

    async def noop(*a, **k):
        pass

    await bot.on_settings_button(SimpleNamespace(callback_query=SimpleNamespace(
        from_user=SimpleNamespace(id=1), data="set:digest", answer=noop)), None)
    await bot._digest_job(None)
    assert ran[0][1] is False and "newsletters" in ran[0][0] and sent[-1][0].startswith("📰")
