"""Connect Gmail and Google Calendar from the chat, no browser on the server needed.

The owner opens Google's sign-in link on their phone. Google then redirects to a localhost
address that doesn't load; the owner pastes that address back into the chat, and the code in it
is exchanged for a token. This is the standard flow for Desktop-app OAuth clients on a headless
machine. PKCE and the state check mean a pasted code is only good for the sign-in started here.
"""

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from google_auth_oauthlib.flow import Flow

from .config import Config
from .db import Database
from .google_services import SCOPES

REDIRECT_URI = "http://localhost:1/"  # nothing listens there: the browser shows the code in its address bar
PENDING_KEY = "google_oauth"
EXPIRY_SECONDS = 15 * 60
CLIENT_FILE = "google_client.json"
# Google's own endpoints. A client file's auth_uri / token_uri are never trusted: they decide where
# the sign-in page and the one-time code go.
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
_REDIRECT_URL = re.compile(r"http://localhost:1/\S*")
_BARE_CODE = re.compile(r"4/[\w.-]{10,}")


class ConnectError(RuntimeError):
    """A message for the owner."""


def client_file(config: Config) -> Path | None:
    # A file sent in chat wins: it's the newest, and it's how a bad credentials.json gets replaced.
    for path in (config.data_dir / CLIENT_FILE, config.google_credentials_file):
        if path.exists():
            return path
    return None


def write_private(path: Path, text: str) -> None:
    """Write-then-rename, readable only by this user: these files hold secrets."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def save_client(config: Config, data: bytes) -> None:
    """Store the OAuth client JSON downloaded from Google Cloud Console (sent as a file in chat)."""
    try:
        info = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ConnectError("That file isn't JSON. Send the OAuth client file you downloaded from Google Cloud.") from e
    if not isinstance(info, dict):
        raise ConnectError("That doesn't look like a Google OAuth client file.")
    if "web" in info:
        raise ConnectError(
            "That's a Web application client. Create one of type Desktop app instead "
            "(Credentials → Create credentials → OAuth client ID → Desktop app) and send that file."
        )
    installed = info.get("installed")
    needed = ("client_id", "client_secret", "auth_uri", "token_uri")
    if not isinstance(installed, dict) or not all(isinstance(installed.get(k), str) for k in needed):
        raise ConnectError("That doesn't look like a Google OAuth client file (Desktop app).")
    if not installed["client_id"].endswith(".apps.googleusercontent.com"):
        raise ConnectError("That client ID isn't a Google one. Download the file again from Google Cloud.")
    clean = {"installed": {"client_id": installed["client_id"], "client_secret": installed["client_secret"],
                           "auth_uri": AUTH_URI, "token_uri": TOKEN_URI, "redirect_uris": ["http://localhost"]}}
    write_private(config.data_dir / CLIENT_FILE, json.dumps(clean))


def _flow(path: Path, **kwargs) -> Flow:
    info = json.loads(path.read_text())
    installed = info.get("installed")
    if not isinstance(installed, dict):
        raise ConnectError("The Google client file must be a Desktop app client.")
    installed = {**installed, "auth_uri": AUTH_URI, "token_uri": TOKEN_URI}  # whatever the file says
    return Flow.from_client_config({"installed": installed}, SCOPES, redirect_uri=REDIRECT_URI, **kwargs)


def start(config: Config, db: Database) -> str:
    """Begin a sign-in. Returns Google's consent URL for the owner to open."""
    path = client_file(config)
    if path is None:
        raise ConnectError("no client")
    flow = _flow(path)
    url, state = flow.authorization_url(prompt="consent", access_type="offline")
    db.set_setting(PENDING_KEY, json.dumps({"state": state, "verifier": flow.code_verifier, "at": time.time()}))
    return url


def is_sign_in_reply(db: Database, text: str, expecting_code: bool = False) -> bool:
    """The address Google redirected to (or, when asked for, the bare code), while a sign-in is
    in progress. Anything else, like a question about some other localhost URL, is a normal message."""
    if db.get_setting(PENDING_KEY) is None:
        return False
    match = _REDIRECT_URL.search(text)
    if match and "state=" in match.group(0):
        return True
    return expecting_code and bool(_BARE_CODE.fullmatch(text.strip()))


def finish(config: Config, db: Database, pasted: str) -> None:
    """Exchange the pasted redirect URL for a token and save it. Blocking (network)."""
    raw = db.get_setting(PENDING_KEY)
    pending = json.loads(raw) if raw else None
    if not pending or time.time() - pending["at"] > EXPIRY_SECONDS:
        db.delete_setting(PENDING_KEY)
        raise ConnectError("That sign-in link expired. Send /connect to get a new one.")
    if _BARE_CODE.fullmatch(pasted.strip()):
        query = {"state": [pending["state"]], "code": [pasted.strip()]}  # PKCE still binds it to us
    else:
        match = _REDIRECT_URL.search(pasted)
        query = parse_qs(urlsplit(match.group(0) if match else "").query)
    if "error" in query:
        db.delete_setting(PENDING_KEY)
        raise ConnectError("Google says access wasn't allowed. Send /connect to try again.")
    if query.get("state", [None])[0] != pending["state"] or not query.get("code"):
        raise ConnectError(
            "That isn't the address from this sign-in. Paste the whole address the browser shows "
            "after you tap Allow (it starts with http://localhost)."
        )
    path = client_file(config)
    if path is None:
        raise ConnectError("The Google client file is gone. Send /connect to set it up again.")
    flow = _flow(path, state=pending["state"], code_verifier=pending["verifier"])
    # Let a partial grant through oauthlib (it raises otherwise) so the check below can explain it.
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    try:
        flow.fetch_token(code=query["code"][0])
    except Exception as e:  # oauthlib raises many types; the message is enough for the owner
        raise ConnectError(f"Google didn't accept that code ({type(e).__name__}). Send /connect to try again.") from e
    granted = flow.credentials.granted_scopes or SCOPES
    if isinstance(granted, str):
        granted = granted.split()
    if not set(SCOPES) <= set(granted):
        raise ConnectError("Some access was unticked. Send /connect and allow both Gmail and Calendar.")
    write_private(config.google_token_file, flow.credentials.to_json())
    db.delete_setting(PENDING_KEY)
