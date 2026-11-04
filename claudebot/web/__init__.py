"""ClaudeBot's web app: the same assistant in a browser (and in the desktop app, which opens it).

It runs inside the bot's own process, so it shares the conversation, memory and safety rules with
Telegram. Only the owner can sign in (see auth.py). By default it listens on this computer only
(127.0.0.1:8765); to reach it from elsewhere, put it behind HTTPS and set WEB_PUBLIC_URL.
"""

import asyncio
import logging
import time
from collections import deque
from importlib import resources
from urllib.parse import urlsplit

from aiohttp import web

from ..files import MAX_FILE_BYTES
from . import auth
from .api import COOKIE, Api

log = logging.getLogger(__name__)

STATIC_FILES = {  # path -> (file, content type); nothing else under /static is served
    "/": ("index.html", "text/html; charset=utf-8"),
    "/login": ("index.html", "text/html; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/icon.svg": ("icon.svg", "image/svg+xml"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; "
       "object-src 'none'")
OPEN_PATHS = {"/api/login", "/api/health"}
MAX_LOGIN_FAILURES = 20  # per 10 minutes, across everyone: tokens are unguessable, this just stops noise
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
FAILED_LOGIN_DELAY = 0.3  # seconds
MAX_BODY = 64 * 1024  # every request but a chat message with a file


LOOPBACK = {"localhost", "127.0.0.1", "::1"}
WILDCARDS = {"0.0.0.0", "::", ""}


def login_url(config, token: str) -> str:
    if config.web_public_url:
        base = config.web_public_url
    else:
        host = "localhost" if config.web_host in WILDCARDS | {"127.0.0.1", "::1"} else config.web_host
        base = f"http://{f'[{host}]' if ':' in host else host}:{config.web_port}"
    return f"{base}/login#t={token}"  # the fragment never reaches a server, a log or a Referer


def check_public_url(config) -> None:
    """Plain http is fine on this computer only: elsewhere the sign-in link and cookie would cross the
    network unencrypted. That covers WEB_PUBLIC_URL, and WEB_HOST when links would point at it."""
    url = config.web_public_url
    if url and urlsplit(url).scheme != "https" and (urlsplit(url).hostname or "") not in LOOPBACK:
        raise RuntimeError(f"WEB_PUBLIC_URL must be https:// for anything but this computer (got {url}).")
    if not url and config.web_host not in LOOPBACK | WILDCARDS:
        raise RuntimeError(f"WEB_HOST={config.web_host} would send sign-in links over plain http. "
                           "Put HTTPS in front and set WEB_PUBLIC_URL=https://...")


def _static(name: str) -> bytes:
    return resources.files(__package__).joinpath("static", name).read_bytes()


class WebServer:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
        self.runner: web.AppRunner | None = None
        self._failures: deque[float] = deque(maxlen=MAX_LOGIN_FAILURES + 1)  # bounded: a flood can't grow it
        self.chatting: set[str] = set()  # sessions with a chat turn in flight (one each)
        public = urlsplit(config_url) if (config_url := self.config.web_public_url) else None
        self.public_host = public.hostname if public else None
        self.public_netloc = public.netloc if public else None
        self.public_origin = f"{public.scheme}://{public.netloc}" if public else None
        self.app = self.build()

    # --- app ---

    def build(self) -> web.Application:
        app = web.Application(middlewares=[self.host_middleware, self.auth_middleware],
                              client_max_size=MAX_FILE_BYTES + 1024 * 1024)  # room for one file in chat
        app.on_response_prepare.append(self.security_headers)  # every response: streams and errors too
        api = Api(self.bot, self)
        app.add_routes([web.post("/api/login", self.login), web.get("/api/health", self.health)] + api.routes())
        for path in STATIC_FILES:
            app.router.add_get(path, self.static)
        return app

    async def start(self) -> None:
        check_public_url(self.config)
        self.runner = web.AppRunner(self.app, access_log=None)  # no request log: nothing private ends up in one
        await self.runner.setup()
        await web.TCPSite(self.runner, self.config.web_host, self.config.web_port).start()
        log.info("Web app on http://%s:%s (sign in with /web in Telegram)", self.config.web_host, self.config.web_port)

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()  # frees the port for an in-process restart
            self.runner = None

    # --- middleware ---

    async def security_headers(self, request: web.Request, response: web.StreamResponse) -> None:
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self._secure(request):
            response.headers["Strict-Transport-Security"] = "max-age=31536000"

    def _host_ok(self, request: web.Request) -> bool:
        """Only names this app is meant to be reached by: this computer, the public address, or the
        address it listens on. A DNS-rebinding page arrives with its own name and is turned away."""
        host = request.url.host or ""
        allowed = LOOPBACK | ({self.public_host} if self.public_host else set())
        if self.config.web_host not in WILDCARDS:
            allowed.add(self.config.web_host)
        return host.strip("[]") in allowed

    @web.middleware
    async def host_middleware(self, request: web.Request, handler):
        if not self._host_ok(request):
            return web.json_response({"error": "Unknown host."}, status=421)
        if request.path != "/api/chat" and (request.content_length or 0) > MAX_BODY:
            return web.json_response({"error": "That's too big."}, status=413)  # only chat takes files
        return await handler(request)

    @web.middleware
    async def auth_middleware(self, request: web.Request, handler):
        if not request.path.startswith("/api/"):
            return await handler(request)
        if request.method not in SAFE_METHODS and not self._same_origin(request):
            return web.json_response({"error": "Wrong origin."}, status=403)
        if request.path in OPEN_PATHS:
            return await handler(request)
        record = auth.session(self.db, request.cookies.get(COOKIE))
        if record is None:
            return web.json_response({"error": "Sign in with /web in Telegram."}, status=401)
        if request.method not in SAFE_METHODS and not auth.csrf_ok(record, request.headers.get("X-CSRF-Token")):
            return web.json_response({"error": "Missing or wrong CSRF token."}, status=403)
        request["session"] = record
        return await handler(request)

    def _secure(self, request: web.Request) -> bool:
        return request.secure or (self.config.web_public_url or "").startswith("https://")

    def _same_origin(self, request: web.Request) -> bool:
        """A change must come from this app's own pages. Browsers send Origin on every POST/DELETE;
        a request without one isn't from a browser page, so a cross-site form can't ride the cookie."""
        origin = request.headers.get("Origin")
        if origin is None:
            return request.headers.get("Sec-Fetch-Site") in (None, "same-origin")
        if self.public_netloc and request.host == self.public_netloc:
            return origin == self.public_origin  # the public address: exactly its own origin
        # This computer (the host was already checked): either scheme, since a local HTTPS proxy
        # (Caddy) shows the app plain http.
        return origin in {f"http://{request.host}", f"https://{request.host}"}

    # --- handlers ---

    async def static(self, request: web.Request) -> web.Response:
        name, content_type = STATIC_FILES[request.path]
        cache = "no-store" if name in ("index.html", "sw.js") else "no-cache"
        return web.Response(body=_static(name), content_type=content_type.split(";")[0],
                            charset="utf-8" if "charset" in content_type else None,
                            headers={"Cache-Control": cache})

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def login(self, request: web.Request) -> web.Response:
        """A valid link always works: the token is checked first, and only failures are throttled,
        so nobody can lock the owner out by sending junk."""
        try:
            token = (await request.json()).get("token")
        except Exception:
            token = None
        if not auth.redeem_login_token(self.db, token):
            now = time.monotonic()
            self._failures.append(now)
            await asyncio.sleep(FAILED_LOGIN_DELAY)  # failures are slowed down; nothing else waits on it
            if len(self._failures) > MAX_LOGIN_FAILURES and now - self._failures[0] < 600:
                return web.json_response({"error": "Too many tries. Wait a few minutes."}, status=429)
            return web.json_response({"error": "That sign-in link has expired or was already used. "
                                               "Send /web in Telegram for a new one."}, status=401)
        session_id, csrf = auth.new_session(self.db, request.headers.get("User-Agent", ""))
        from ..actions import ActionLog
        ActionLog(self.db).record("security", f"Signed in to the web app ({request.headers.get('User-Agent', '?')[:60]})")
        response = web.json_response({"ok": True, "csrf": csrf})
        response.set_cookie(COOKIE, session_id, max_age=int(auth.SESSION_TTL.total_seconds()), path="/",
                            httponly=True, samesite="Strict", secure=self._secure(request))
        return response
