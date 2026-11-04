"""The web app's JSON API. Each handler goes through the same code the Telegram commands and buttons
use, so the rules (validation, reminders by id, the action log) are the same wherever you click."""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from aiohttp import web

from ..actions import ActionLog
from ..bills import Bills, next_due, paid_dates
from ..birthdays import Birthdays, next_birthday, parse_birthday
from ..checkins import URGENT_WAKES_KEY
from ..expenses import Expenses
from ..files import MAX_FILE_BYTES, UnsupportedFile
from ..inbox_watch import ALERT_MODE_KEY
from ..lists import Lists
from ..quiet import dnd_until, parse_pause
from . import auth

log = logging.getLogger(__name__)

MAX_CHAT_CHARS = 8000
HISTORY_LIMIT = 60
STREAM_EVERY = 0.15  # seconds between streamed updates
KEEPALIVE = 15  # seconds


def _json(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store"})


def _error(message: str, status: int = 400) -> web.Response:
    return _json({"error": message}, status)


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise web.HTTPBadRequest(text="Expected JSON") from None
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Expected a JSON object")
    return data


def _int(request: web.Request, name: str) -> int:
    try:
        return int(request.match_info[name])
    except (KeyError, ValueError):
        raise web.HTTPNotFound() from None


def _is_special_file(data: bytes, name: str) -> bool:
    """A ClaudeBot export (restored only in Telegram, after its review card) or a Google OAuth client
    file (its secret must never reach Claude)."""
    lowered = name.lower()
    if lowered.startswith("claudebot-export") and lowered.endswith(".json"):
        return True
    return lowered.endswith(".json") and b"client_secret" in data[:200_000]


def history_view(messages: list[dict]) -> list[dict]:
    """What the owner and ClaudeBot said in this conversation, for the chat screen. The owner's words
    are the last text block of a user turn (the first is the time/memory preamble, and background
    events are fenced blocks); tool results and system messages aren't shown."""
    out = []
    for m in messages:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": str(m["content"])}]
        if m["role"] == "user":
            texts = [b.get("text", "") for i, b in enumerate(blocks)
                     if b.get("type") == "text" and i > 0 and not b.get("text", "").startswith("<background_events>")]
            if any(b.get("type") == "tool_result" for b in blocks) and not texts:
                continue
            files = any(b.get("type") in ("image", "document", "container_upload") for b in blocks)
            text = (f"📎 {texts[-1]}" if files else texts[-1]) if texts else ("📎 (a file)" if files else "")
            if text:
                out.append({"role": "you", "text": text})
        elif m["role"] == "assistant":
            text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
            if text:
                out.append({"role": "claudebot", "text": text})
    return out[-HISTORY_LIMIT:]


class Api:
    def __init__(self, bot, server=None):
        self.bot = bot
        self.db = bot.db
        self.chatting: set[str] = server.chatting if server is not None else set()

    def routes(self) -> list:
        g, p, d = web.get, web.post, web.delete
        return [
            g("/api/me", self.me), p("/api/logout", self.logout), p("/api/logout-all", self.logout_all),
            g("/api/history", self.history), p("/api/chat", self.chat), p("/api/new", self.new_chat),
            g("/api/today", self.today), g("/api/week", self.week),
            g("/api/reminders", self.reminders), p("/api/reminders", self.add_reminder),
            p("/api/reminders/{id}/cancel", self.cancel_reminder),
            g("/api/lists", self.lists), p("/api/lists/items", self.add_list_items),
            p("/api/lists/{list_id}/items/{item_id}/toggle", self.toggle_item),
            p("/api/lists/{list_id}/clear", self.clear_list),
            g("/api/bills", self.bills), p("/api/bills/{id}/paid", self.pay_bill), d("/api/bills/{id}", self.delete_bill),
            g("/api/birthdays", self.birthdays), p("/api/birthdays", self.add_birthday),
            d("/api/birthdays/{id}", self.delete_birthday),
            g("/api/memories", self.memories), p("/api/memories", self.add_memory),
            d("/api/memories/{id}", self.delete_memory), g("/api/search", self.search),
            g("/api/log", self.action_log), g("/api/usage", self.usage), g("/api/dms", self.dms),
            g("/api/settings", self.settings), p("/api/settings", self.change_settings),
            g("/api/outbox", self.outbox), p("/api/outbox/{id}/send", self.outbox_send),
            p("/api/outbox/{id}/cancel", self.outbox_cancel),
        ]

    # --- session ---

    async def me(self, request: web.Request) -> web.Response:
        record = request["session"]
        return _json({"name": self.bot.config.owner_name, "csrf": record["csrf"],
                      "google": self.bot.google.is_connected(), "dms": bool(self.bot.dms.active_connection_id()),
                      "timezone": str(self.bot.config.timezone)})

    async def logout(self, request: web.Request) -> web.Response:
        auth.end_session(self.db, request.cookies.get(COOKIE))
        response = _json({"ok": True})
        response.del_cookie(COOKIE, path="/")
        return response

    async def logout_all(self, request: web.Request) -> web.Response:
        ended = auth.end_all_sessions(self.db)
        ActionLog(self.db).record("security", f"Signed out of the web app everywhere ({ended} sessions)")
        response = _json({"ok": True, "ended": ended})
        response.del_cookie(COOKIE, path="/")
        return response

    # --- chat ---

    async def history(self, request: web.Request) -> web.Response:
        thread_id = self.db.latest_thread_id()
        return _json({"messages": history_view(self.db.load_messages(thread_id)) if thread_id else []})

    async def new_chat(self, request: web.Request) -> web.Response:
        async with self.bot._message_order:
            self.db.new_thread(self.bot.agent.config_hash)
        return _json({"ok": True})

    async def chat(self, request: web.Request) -> web.StreamResponse:
        """One turn, streamed as server-sent events: `delta` with the reply so far, then `done`.
        The turn runs on its own task: closing the tab doesn't cut it off halfway through a tool."""
        upload = None
        if request.content_type == "multipart/form-data":
            try:
                text, upload = await self._read_upload(request)
            except ValueError as e:
                return _error(str(e))
        else:
            text = str((await _body(request)).get("text", "")).strip()
        if not text and upload is None:
            return _error("Say something first.")
        if len(text) > MAX_CHAT_CHARS:
            return _error(f"That's over {MAX_CHAT_CHARS:,} characters.")
        busy_key = request["session"]["csrf"]  # one turn at a time per sign-in: a stuck tab can't queue up costs
        if busy_key in self.chatting:
            return _error("Still answering your last message.", 409)
        self.chatting.add(busy_key)
        try:
            content = [{"type": "text", "text": text}]
            if upload is not None:
                try:
                    block = await self._file_block(*upload)
                except UnsupportedFile as e:
                    return _error(str(e))
                except Exception:
                    log.exception("Storing a web upload failed")
                    return _error("I couldn't save that file just now. Please try again.", 502)
                question = text or "(sent with no message: say briefly what it is and anything I need to act on)"
                content = [block, {"type": "text", "text": question}]  # as a file sent on Telegram
            return await self._chat_turn(request, content)
        finally:
            self.chatting.discard(busy_key)

    async def _read_upload(self, request: web.Request) -> tuple[str, tuple[bytes, str, str] | None]:
        """A message and at most one file, as multipart: `text`, then `file`."""
        reader = await request.multipart()
        text, upload = "", None
        async for part in reader:
            if part.name == "text":
                text = (await part.text())[: MAX_CHAT_CHARS + 1].strip()
            elif part.name == "file" and part.filename and upload is None:
                data = await part.read(decode=False)
                if len(data) > MAX_FILE_BYTES:
                    raise ValueError(f"{part.filename} is too big for me (10 MB max).")
                name = " ".join(part.filename.split())[:80] or "file"
                upload = (bytes(data), part.headers.get("Content-Type", ""), name)
        if len(text) > MAX_CHAT_CHARS:
            raise ValueError(f"That's over {MAX_CHAT_CHARS:,} characters.")
        if upload and _is_special_file(upload[0], upload[2]):
            raise ValueError("Send that file in Telegram: exports are restored there after a tap, and Google "
                             "client files are set up with /connect, so their secret never reaches Claude.")
        return text, upload

    async def _file_block(self, data: bytes, mime: str, name: str) -> dict:
        from ..bot import (
            workbench_file_note,  # here, not at the top: bot.py imports the web app
        )
        from ..files import is_workbench_file

        if is_workbench_file(mime):  # Excel/Word/PowerPoint: Claude opens these with code in the workbench
            await self.bot.uploader.store_raw(data, mime, name)
            return {"type": "text", "text": workbench_file_note(name, None)}
        return await self.bot.uploader.to_block(data, mime, name)

    async def _chat_turn(self, request: web.Request, content: list[dict]) -> web.StreamResponse:
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store",
                                               "X-Accel-Buffering": "no"})
        await response.prepare(request)
        state = {"open": True, "last": 0.0}

        async def send(event: str, data: dict) -> None:
            if not state["open"]:
                return
            try:
                await response.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
            except (ConnectionResetError, RuntimeError):
                state["open"] = False  # the tab closed; the turn carries on and lands in the history

        async def on_text(so_far: str) -> None:
            now = asyncio.get_running_loop().time()
            if now - state["last"] >= STREAM_EVERY:
                state["last"] = now
                await send("delta", {"text": so_far})

        async def turn() -> tuple[str, bool]:
            async with self.bot._message_order:  # after any Telegram message already queued
                return await self.bot._run_agent(content, owner_present=True, source="web", on_text=on_text)

        await send("start", {})
        task = asyncio.ensure_future(turn())
        while True:  # a comment line now and then, so proxies don't drop a stream that's waiting its turn
            done, _ = await asyncio.wait({task}, timeout=KEEPALIVE)
            if done:
                break
            if state["open"]:
                try:
                    await response.write(b": still working\n\n")
                except (ConnectionResetError, RuntimeError):
                    state["open"] = False
        try:
            reply, ok = task.result()
        except Exception:  # anything unexpected still ends the stream properly
            log.exception("A web chat turn failed")
            reply, ok = "Something went wrong on my side. Try again in a moment.", False
        await send("done", {"text": reply, "ok": ok})
        if state["open"]:
            await response.write_eof()
        return response

    # --- glance ---

    async def today(self, request: web.Request) -> web.Response:
        return _json(await self.bot.today_data())

    async def week(self, request: web.Request) -> web.Response:
        return _json(await self.bot.week_data())

    # --- reminders ---

    async def reminders(self, request: web.Request) -> web.Response:
        tz = self.bot.config.timezone
        owned = {b.get("reminder_id") for b in Bills(self.db).all() + Birthdays(self.db).all()}
        rows = [{"id": r["id"], "text": r["text"], "repeat": r["repeat"], "task": bool(r["run_as_task"]),
                 "briefing": bool(r["briefing"]), "owned": r["id"] in owned,
                 "next": datetime.fromisoformat(r["due_at"]).astimezone(tz).isoformat()}
                for r in self.db.active_reminders()]
        return _json({"reminders": rows})

    async def add_reminder(self, request: web.Request) -> web.Response:
        """A plain reminder from the form: same checks as the set_reminder tool (a real time, in the
        future unless it repeats, one of the known repeats)."""
        from ..tools import REPEAT_OPTIONS

        body = await _body(request)
        text = " ".join(str(body.get("text", "")).split())[:300]
        repeat = body.get("repeat", "none")
        if not text:
            return _error("What should I remind you about?")
        if repeat not in REPEAT_OPTIONS:
            return _error("Pick how often it repeats.")
        tz = self.bot.config.timezone
        try:
            when = datetime.fromisoformat(str(body.get("when", "")))
        except ValueError:
            return _error("Pick a date and time.")
        when = when.replace(tzinfo=tz) if when.tzinfo is None else when.astimezone(tz)
        if when <= datetime.now(tz) and repeat == "none":
            return _error("That time has already passed.")
        reminder_id = self.db.add_reminder(text, when, repeat, False)
        self.bot.schedule_reminder(reminder_id)
        ActionLog(self.db).record("reminder", f"Reminder set for {when:%a %b %-d %H:%M}: {text} (web)")
        return _json({"id": reminder_id, "next": when.isoformat()})

    async def cancel_reminder(self, request: web.Request) -> web.Response:
        reminder_id = _int(request, "id")
        if self._owned_reminder(reminder_id):
            return _error("That reminder belongs to a bill or birthday; remove it there.")
        cancelled = self.db.deactivate_reminder(reminder_id)
        self.bot.unschedule_reminder(reminder_id)
        if cancelled:
            ActionLog(self.db).record("reminder", f"Cancelled reminder #{reminder_id} (web)")
        return _json({"cancelled": cancelled})

    def _owned_reminder(self, reminder_id: int) -> bool:
        return any(b.get("reminder_id") == reminder_id for b in Bills(self.db).all() + Birthdays(self.db).all())

    # --- lists ---

    async def lists(self, request: web.Request) -> web.Response:
        lists = Lists(self.db)
        return _json({"lists": [{"id": lists.id_of(n), "name": n, "items": lists.items(n)} for n in lists.names()]})

    async def add_list_items(self, request: web.Request) -> web.Response:
        body = await _body(request)
        name, items = str(body.get("list", "")).strip(), body.get("items")
        if not name or not isinstance(items, list) or not items or len(items) > 50:
            return _error("Name a list and up to 50 items.")
        try:
            added = Lists(self.db).add(name, [str(i) for i in items])
        except ValueError as e:
            return _error(str(e))
        return _json({"added": added})

    async def toggle_item(self, request: web.Request) -> web.Response:
        item = Lists(self.db).toggle(_int(request, "item_id"), _int(request, "list_id"))
        return _json({"item": item}) if item else _error("That item is gone.", 404)

    async def clear_list(self, request: web.Request) -> web.Response:
        lists = Lists(self.db)
        name = lists.name_of(_int(request, "list_id"))
        if name is None:
            return _error("That list is gone.", 404)
        return _json({"cleared": lists.clear_done(name)})

    # --- bills ---

    async def bills(self, request: web.Request) -> web.Response:
        today = datetime.now(self.bot.config.timezone).date()
        rows = []
        for b in sorted(Bills(self.db).all(), key=lambda b: next_due(b["day"], today)):
            due = next_due(b["day"], today)
            rows.append({"id": b["id"], "name": b["name"], "amount": b["amount"], "currency": b["currency"],
                         "day": b["day"], "next_due": due.isoformat(), "paid": due.isoformat() in paid_dates(b)})
        return _json({"bills": rows})

    async def pay_bill(self, request: web.Request) -> web.Response:
        bills, bill_id = Bills(self.db), _int(request, "id")
        bill = next((b for b in bills.all() if b["id"] == bill_id), None)
        if bill is None:
            return _error("That bill is gone.", 404)
        settled = bills.mark_paid(bill_id, datetime.now(self.bot.config.timezone).date())
        if settled is None:
            return _error(f"{bill['name']} is already logged as paid.", 409)
        Expenses(self.db).log(bill["amount"], "bills", bill["name"], bill["currency"])
        ActionLog(self.db).record("money", f"Paid {bill['name']}: {bill['amount']:,.2f} {bill['currency']} (web)")
        return _json({"settled": settled.isoformat()})

    async def delete_bill(self, request: web.Request) -> web.Response:
        gone = Bills(self.db).remove(_int(request, "id"))
        if gone is None:
            return _error("That bill is gone.", 404)
        self.bot._cancel_bill_reminder(gone)
        ActionLog(self.db).record("money", f"Removed bill: {gone['name']} (web)")
        return _json({"removed": gone["name"]})

    # --- birthdays ---

    async def birthdays(self, request: web.Request) -> web.Response:
        today = datetime.now(self.bot.config.timezone).date()
        rows = [{"id": b["id"], "name": b["name"], "month": b["month"], "day": b["day"],
                 "next": next_birthday(b["month"], b["day"], today).isoformat()} for b in Birthdays(self.db).all()]
        return _json({"birthdays": sorted(rows, key=lambda b: b["next"])})

    async def add_birthday(self, request: web.Request) -> web.Response:
        body = await _body(request)
        parsed = parse_birthday(f"{body.get('name', '')} {body.get('month', '')}-{body.get('day', '')}")
        if parsed is None:
            return _error("A birthday needs a name and a real date.")
        try:
            item = self.bot.add_birthday(*parsed)
        except ValueError as e:
            return _error(str(e))
        return _json({"birthday": item})

    async def delete_birthday(self, request: web.Request) -> web.Response:
        gone = Birthdays(self.db).remove(_int(request, "id"))
        if gone is None:
            return _error("That birthday is gone.", 404)
        self.bot._cancel_birthday_reminder(gone)
        ActionLog(self.db).record("reminder", f"Birthday removed: {gone['name']} (web)")
        return _json({"removed": gone["name"]})

    # --- memory, log, usage, DMs ---

    async def memories(self, request: web.Request) -> web.Response:
        return _json({"memories": [{"id": m["id"], "text": m["text"]}
                                   for m in self.db.list_memories()]})

    async def add_memory(self, request: web.Request) -> web.Response:
        text = " ".join(str((await _body(request)).get("text", "")).split())[:500]
        if not text:
            return _error("What should I remember?")
        if text in {m["text"] for m in self.db.list_memories()}:
            return _error("I already remember that.", 409)
        memory_id = self.db.add_memory(text)
        ActionLog(self.db).record("memory", f"Saved memory #{memory_id} (web)")
        return _json({"id": memory_id})

    async def search(self, request: web.Request) -> web.Response:
        """Find things across memories, lists, reminders, bills and birthdays. Plain substring
        matching on what's stored here: no model call, nothing leaves the server."""
        query = " ".join(request.query.get("q", "").lower().split())[:100]
        if len(query) < 2:
            return _json({"results": []})
        hits = []

        def add(kind: str, text: str, page: str) -> None:
            if query in text.lower() and len(hits) < 40:
                hits.append({"kind": kind, "text": text, "page": page})

        for m in self.db.list_memories():
            add("memory", m["text"], "memory")
        lists = Lists(self.db)
        for name in lists.names():
            for item in lists.items(name):
                add("list", f"{name}: {item['text']}", "lists")
        for r in self.db.active_reminders():
            add("reminder", r["text"], "reminders")
        for b in Bills(self.db).all():
            add("bill", b["name"], "bills")
        for b in Birthdays(self.db).all():
            add("birthday", b["name"], "birthdays")
        return _json({"results": hits})

    async def delete_memory(self, request: web.Request) -> web.Response:
        memory_id = _int(request, "id")
        if not self.db.delete_memory(memory_id):
            return _error("That memory is gone.", 404)
        ActionLog(self.db).record("memory", f"Forgot memory #{memory_id} (web)")
        return _json({"deleted": memory_id})

    async def action_log(self, request: web.Request) -> web.Response:
        try:
            days = min(max(int(request.query.get("days", "7")), 1), 60)
        except ValueError:
            days = 7
        tz = self.bot.config.timezone
        rows = ActionLog(self.db).since(datetime.now(tz) - timedelta(days=days))
        return _json({"actions": [{**r, "at": datetime.fromisoformat(r["at"]).astimezone(tz).isoformat()}
                                  for r in reversed(rows)]})

    async def usage(self, request: web.Request) -> web.Response:
        tracker = self.bot.tracker
        now = datetime.now(self.bot.config.timezone)
        start = tracker._month_start(now)
        by_source = [{"source": s, "calls": n, "cost": round(c, 4)} for s, n, c in self.db.usage_by_source(start)]
        return _json({"month_cost": round(tracker.month_cost(now), 4), "budget": self.bot.config.monthly_budget_usd,
                      "by_source": by_source})

    async def dms(self, request: web.Request) -> web.Response:
        if not self.bot.dms.active_connection_id():
            return _json({"connected": False, "waiting": []})
        return _json({"connected": True, "waiting": [
            {"chat_id": c.chat_id, "name": c.name, "since": c.waiting_since.isoformat(), "messages": c.messages,
             "can_reply": c.can_reply} for c in self.bot.dms.unanswered()]})

    # --- outbox: emails waiting out their Undo window, or waiting for a Send tap ---

    async def outbox(self, request: web.Request) -> web.Response:
        """Every recipient and the whole body, as the Telegram card shows them: a hidden bcc can't slip
        past the owner here either."""
        rows = []
        for status in ("held", "pending"):
            for r in self.db.outbox_with_status(status):
                email = json.loads(r["email_json"])
                rows.append({"id": r["id"], "status": status, "send_at": r["send_at"],
                             "to": email.get("to", ""), "cc": email.get("cc") or "", "bcc": email.get("bcc") or "",
                             "subject": email.get("subject") or "(reply)", "body": email.get("body", "")})
        return _json({"emails": rows})

    async def outbox_send(self, request: web.Request) -> web.Response:
        """Same as the ✅ Send button: only an email held for the owner's say-so."""
        result = await self.bot.outbox.approve(_int(request, "id"))
        return _json({"result": result}, 200 if result == "Sending." else 409)

    async def outbox_cancel(self, request: web.Request) -> web.Response:
        """Same as ↩️ Undo / ✖️ Cancel."""
        result = await self.bot.outbox.undo(_int(request, "id"))
        return _json({"result": result}, 200 if result == "Cancelled." else 409)

    # --- settings ---

    async def settings(self, request: web.Request) -> web.Response:
        now = datetime.now(self.bot.config.timezone)
        until = dnd_until(self.db, now)
        return _json({"quiet_until": until.isoformat() if until else None,
                      "alert_mode": self.db.get_setting(ALERT_MODE_KEY) or "instant",
                      "urgent_wakes": self.db.get_setting(URGENT_WAKES_KEY) == "on",
                      "quiet_hours": self.bot.config.quiet_hours})

    async def change_settings(self, request: web.Request) -> web.Response:
        body = await _body(request)
        now = datetime.now(self.bot.config.timezone)
        if "quiet" in body:  # "off", "1h", "90m", "morning"
            choice = str(body["quiet"]).strip().lower()
            until = None if choice == "off" else parse_pause(choice, now)
            if choice != "off" and until is None:
                return _error("Try 30m, 2h or morning.")
            self.bot._pause(until)
        if "alert_mode" in body:
            if body["alert_mode"] not in ("instant", "hourly"):
                return _error("Alert mode is instant or hourly.")
            self.db.set_setting(ALERT_MODE_KEY, body["alert_mode"])  # as /settings stores it
        if "urgent_wakes" in body:
            if body["urgent_wakes"] is True:
                self.db.set_setting(URGENT_WAKES_KEY, "on")
            else:
                self.db.delete_setting(URGENT_WAKES_KEY)
        return await self.settings(request)


COOKIE = "cb_session"
