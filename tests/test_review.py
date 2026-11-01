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
        return SimpleNamespace(message_id=700 + len(sent))

    async def run_agent(content, owner_present=True, effort=None, live=False, source=None):
        asked.append((content[0]["text"], owner_present))
        return "You had a good week.", True

    bot.send_to_owner = send_to_owner
    bot._run_agent = run_agent
    bot.google.is_connected = lambda: True
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
    assert not await bot.handle_answer(SimpleNamespace(text="remind me at 6pm to call mom", forward_origin=None,
                                                       reply_to_message=None))
    message = SimpleNamespace(text="skip the headlines <please>", forward_origin=None,
                              reply_to_message=SimpleNamespace(message_id=700 + len(sent)))
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

    repeating = {}

    def run_daily(job, time, days=tuple(range(7)), name=None):
        daily[name] = ((time.hour, time.minute), days)

    def run_repeating(job, interval, first=None, name=None):
        repeating[name] = interval

    app = SimpleNamespace(job_queue=SimpleNamespace(run_daily=run_daily, run_repeating=run_repeating),
                          bot=SimpleNamespace(set_my_commands=noop))
    bot.outbox.resume = noop
    await bot._post_init(app)
    every_day = tuple(range(7))
    assert daily["weekly-review"] == ((18, 0), (0,))  # Sunday
    assert daily["newsletter-digest"] == ((10, 0), (6,))  # Saturday
    assert daily["journal"] == ((21, 30), every_day) and daily["habits"] == ((20, 30), every_day)
    assert daily["backup"] == ((3, 0), every_day)
    assert repeating["meeting-prep"] == 15 * 60 and repeating["check-ins"] == 3 * 3600
    assert repeating["alert-digest"] == 3600 and repeating["alive"] == 60



async def test_newsletter_digest_is_opt_in(tmp_path, monkeypatch):
    bot, sent, _ = make_bot(tmp_path, monkeypatch)
    ran = []

    async def run_agent(content, owner_present=True, effort=None, live=False, source=None):
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



async def test_weekend_brief_can_be_turned_off(tmp_path, monkeypatch):
    from datetime import datetime as real_datetime

    bot, sent, asked = make_bot(tmp_path, monkeypatch)
    briefs = []

    async def send_brief():
        briefs.append(1)

    bot._send_brief = send_brief

    class Saturday(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 11, 7, 8, 0, tzinfo=tz)

    monkeypatch.setattr("claudebot.bot.datetime", Saturday)
    await bot._brief_job(None)
    bot.db.set_setting("brief_weekends", "off")
    await bot._brief_job(None)
    assert briefs == [1]



async def test_the_brief_and_scheduled_tasks_run_as_turns_the_owner_didnt_start(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from helpers import TZ

    bot, sent, asked = make_bot(tmp_path, monkeypatch)
    await bot._send_brief()
    assert asked[-1][1] is False  # the brief
    seen = []

    async def ask_agent(content, owner_present=True, effort=None, source="chat"):
        seen.append(owner_present)
        return "done"

    bot._ask_agent = ask_agent
    rid = bot.db.add_reminder("check the inbox", datetime.now(TZ) + timedelta(minutes=1), "none", True)
    await bot._reminder_job(SimpleNamespace(job=SimpleNamespace(data=rid)))
    assert seen == [False]  # a scheduled task


def test_sweep_never_touches_starred_or_important_mail():
    from claudebot.sweep import SWEEPS

    assert all("-is:starred" in q and "-is:important" in q for _, q in SWEEPS.values())


async def test_meeting_prep_stays_quiet_during_a_pause(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from helpers import TZ

    bot, sent, asked = make_bot(tmp_path, monkeypatch)
    soon = datetime.now(TZ) + timedelta(minutes=50)
    bot.google.list_events = lambda *a, **k: [{
        "id": "e1", "summary": "Sync", "start": soon.isoformat(), "end": (soon + timedelta(hours=1)).isoformat(),
        "attendees": ["a@x.com", "b@y.com"], "accepted": True}]
    bot.db.set_setting("dnd_until", (datetime.now(TZ) + timedelta(hours=2)).isoformat())
    await bot._meeting_prep_job(None)
    assert asked == []
    bot.db.delete_setting("dnd_until")
    await bot._meeting_prep_job(None)
    assert len(asked) == 1  # the same meeting, once the pause is over
