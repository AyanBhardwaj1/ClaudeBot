"""Gmail and Google Calendar access. All functions are blocking; call them via asyncio.to_thread."""

import base64
import html
import json
import re
from datetime import date, datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import Config
from .files import MAX_FILE_BYTES

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # read, label, draft and send
    "https://www.googleapis.com/auth/calendar",
]

MAX_BODY_CHARS = 15000


class GoogleNotConnected(RuntimeError):
    pass


class Google:
    def __init__(self, config: Config):
        self.config = config
        self.tz: ZoneInfo = config.timezone
        self._creds: Credentials | None = None

    # --- auth ---

    def _credentials(self) -> Credentials:
        if self._creds is None:
            if self.config.google_token_json:
                info = json.loads(self.config.google_token_json)
            elif self.config.google_token_file.exists():
                info = json.loads(self.config.google_token_file.read_text())
            else:
                raise GoogleNotConnected(
                    "Google account not connected. Run `python -m claudebot.google_auth` first."
                )
            self._creds = Credentials.from_authorized_user_info(info, SCOPES)
        if not self._creds.valid:
            self._creds.refresh(Request())
            if not self.config.google_token_json:
                self.config.google_token_file.write_text(self._creds.to_json())
        return self._creds

    def _gmail(self):
        # A fresh client per call: googleapiclient's HTTP layer is not thread-safe.
        return build("gmail", "v1", credentials=self._credentials(), cache_discovery=False)

    def _calendar(self):
        return build("calendar", "v3", credentials=self._credentials(), cache_discovery=False)

    # --- gmail ---

    def search_emails(self, query: str, max_results: int = 10) -> list[dict]:
        gmail = self._gmail()
        listing = (
            gmail.users()
            .messages()
            .list(userId="me", q=query, maxResults=min(max(max_results, 1), 50))
            .execute()
        )
        results = []
        for ref in listing.get("messages", []):
            msg = (
                gmail.users()
                .messages()
                .get(
                    userId="me",
                    id=ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                )
                .execute()
            )
            headers = _headers(msg)
            results.append(
                {
                    "id": msg["id"],
                    "thread_id": msg["threadId"],
                    "from": headers.get("from", ""),
                    "to": headers.get("to", ""),
                    "subject": headers.get("subject", ""),
                    "date": headers.get("date", ""),
                    "snippet": html.unescape(msg.get("snippet", "")),
                    "unread": "UNREAD" in msg.get("labelIds", []),
                }
            )
        return results

    def read_email(self, message_id: str) -> dict:
        msg = self._gmail().users().messages().get(userId="me", id=message_id, format="full").execute()
        headers = _headers(msg)
        body = _extract_body(msg["payload"])
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + f"\n[... truncated, {len(body)} chars total]"
        return {
            "id": msg["id"],
            "thread_id": msg["threadId"],
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "labels": msg.get("labelIds", []),
            "attachments": _attachment_names(msg["payload"]),
            "body": body,
        }

    def get_attachment(self, message_id: str, filename: str) -> tuple[bytes, str]:
        """Download one attachment by filename. Returns (bytes, mime type)."""
        gmail = self._gmail()
        msg = gmail.users().messages().get(userId="me", id=message_id, format="full").execute()
        part = next((p for p in _walk(msg["payload"]) if p.get("filename") == filename), None)
        if part is None:
            names = ", ".join(_attachment_names(msg["payload"])) or "none"
            raise ValueError(f"No attachment named {filename!r}. Attachments: {names}")
        body = part.get("body", {})
        if body.get("size", 0) > MAX_FILE_BYTES:
            raise ValueError(f"{filename} is too large to read ({body['size'] // (1024 * 1024)} MB).")
        data = body.get("data")
        if data is None:
            data = (
                gmail.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=body["attachmentId"])
                .execute()["data"]
            )
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)), part.get("mimeType", "")

    def _build_message(
        self, to: str, subject: str, body: str, cc: str, bcc: str, reply_to_message_id: str
    ) -> dict:
        email = EmailMessage()
        email["To"] = to
        if cc:
            email["Cc"] = cc
        if bcc:
            email["Bcc"] = bcc
        payload: dict = {}
        if reply_to_message_id:
            original = (
                self._gmail()
                .users()
                .messages()
                .get(
                    userId="me",
                    id=reply_to_message_id,
                    format="metadata",
                    metadataHeaders=["Message-ID", "References", "Subject"],
                )
                .execute()
            )
            headers = _headers(original)
            if headers.get("message-id"):
                email["In-Reply-To"] = headers["message-id"]
                email["References"] = (
                    headers.get("references", "") + " " + headers["message-id"]
                ).strip()
            if not subject:
                subject = headers.get("subject", "")
            if subject and not subject.lower().startswith("re:"):
                subject = "Re: " + subject
            payload["threadId"] = original["threadId"]
        email["Subject"] = subject
        email.set_content(body)
        payload["raw"] = base64.urlsafe_b64encode(email.as_bytes()).decode()
        return payload

    def send_email(
        self, to: str, subject: str, body: str, cc: str = "", bcc: str = "", reply_to_message_id: str = ""
    ) -> dict:
        payload = self._build_message(to, subject, body, cc, bcc, reply_to_message_id)
        sent = self._gmail().users().messages().send(userId="me", body=payload).execute()
        return {"status": "sent", "id": sent["id"], "thread_id": sent["threadId"]}

    def create_draft(
        self, to: str, subject: str, body: str, cc: str = "", bcc: str = "", reply_to_message_id: str = ""
    ) -> dict:
        payload = self._build_message(to, subject, body, cc, bcc, reply_to_message_id)
        draft = (
            self._gmail().users().drafts().create(userId="me", body={"message": payload}).execute()
        )
        return {"status": "draft saved", "draft_id": draft["id"]}

    def modify_email(self, message_id: str, action: str) -> dict:
        messages = self._gmail().users().messages()
        if action == "trash":
            messages.trash(userId="me", id=message_id).execute()
            return {"status": "moved to trash"}
        changes = {
            "archive": {"removeLabelIds": ["INBOX"]},
            "mark_read": {"removeLabelIds": ["UNREAD"]},
            "mark_unread": {"addLabelIds": ["UNREAD"]},
            "star": {"addLabelIds": ["STARRED"]},
            "unstar": {"removeLabelIds": ["STARRED"]},
            "mark_important": {"addLabelIds": ["IMPORTANT"]},
        }
        if action not in changes:
            raise ValueError(f"Unknown action {action!r}")
        messages.modify(userId="me", id=message_id, body=changes[action]).execute()
        return {"status": "done", "action": action}

    # --- calendar ---

    def list_events(self, start: str, end: str, max_results: int = 25) -> list[dict]:
        events = (
            self._calendar()
            .events()
            .list(
                calendarId="primary",
                timeMin=self._to_datetime(start).isoformat(),
                timeMax=self._to_datetime(end).isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=min(max(max_results, 1), 100),
            )
            .execute()
        )
        return [
            {
                "id": e["id"],
                "summary": e.get("summary", "(no title)"),
                "start": e["start"].get("dateTime", e["start"].get("date")),
                "end": e["end"].get("dateTime", e["end"].get("date")),
                "location": e.get("location", ""),
                "attendees": [a.get("email") for a in e.get("attendees", [])],
                "description": (e.get("description") or "")[:500],
            }
            for e in events.get("items", [])
        ]

    def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
        attendees: list[str] | None = None,
    ) -> dict:
        body = {
            "summary": summary,
            "start": self._event_time(start),
            "end": self._event_time(end),
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        event = (
            self._calendar()
            .events()
            .insert(calendarId="primary", body=body, sendUpdates="all" if attendees else "none")
            .execute()
        )
        return {"status": "created", "id": event["id"], "link": event.get("htmlLink", "")}

    def update_event(self, event_id: str, **fields) -> dict:
        body = {}
        for key in ("summary", "description", "location"):
            if fields.get(key):
                body[key] = fields[key]
        for key in ("start", "end"):
            if fields.get(key):
                body[key] = self._event_time(fields[key])
        event = (
            self._calendar().events().patch(calendarId="primary", eventId=event_id, body=body).execute()
        )
        return {"status": "updated", "id": event["id"]}

    def delete_event(self, event_id: str) -> dict:
        self._calendar().events().delete(calendarId="primary", eventId=event_id).execute()
        return {"status": "deleted"}

    # --- helpers ---

    def _to_datetime(self, value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=self.tz)

    def _event_time(self, value: str) -> dict:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return {"date": date.fromisoformat(value).isoformat()}
        return {"dateTime": self._to_datetime(value).isoformat(), "timeZone": str(self.tz)}


def _headers(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _walk(part: dict):
    yield part
    for sub in part.get("parts", []) or []:
        yield from _walk(sub)


def _extract_body(payload: dict) -> str:
    plain, rich = [], []
    for part in _walk(payload):
        data = part.get("body", {}).get("data")
        if not data or part.get("filename"):
            continue
        if part.get("mimeType") == "text/plain":
            plain.append(_decode(data))
        elif part.get("mimeType") == "text/html":
            rich.append(_html_to_text(_decode(data)))
    return "\n".join(plain or rich).strip()


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\n\s*\n+", "\n\n", text)


def _attachment_names(payload: dict) -> list[str]:
    return [p["filename"] for p in _walk(payload) if p.get("filename")]
