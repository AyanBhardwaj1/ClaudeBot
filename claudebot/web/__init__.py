"""ClaudeBot's web app: the same assistant in a browser (and in the desktop app, which opens it).

It runs inside the bot's own process, so it shares the conversation, memory and safety rules with
Telegram. Only the owner can sign in (see auth.py). By default it listens on this computer only
(127.0.0.1:8765); to reach it from elsewhere, put it behind HTTPS and set WEB_PUBLIC_URL.
"""

import logging
import time
from importlib import resources
from urllib.parse import urlsplit

from aiohttp import web

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


def login_url(config, token: str) -> str:
    base = config.web_public_url or f"http://{'localhost' if config.web_host in ('127.0.0.1', '0.0.0.0', '::') else config.web_host}:{config.web_port}"
    return f"{base}/login#t={token}"  # the fragment never reaches a server, a log or a Referer


def _static(name: str) -> bytes:
    return resources.files(__package__).joinpath("static", name).read_bytes()


class WebServer:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.db = bot.db
        self.runner: web.AppRunner | None = None
        self._failures: list[float] = []
        self.app = self.build()

    # --- app ---

    def build(self) -> web.Application:
        app = web.Application(middlewares=[self.headers_middleware, self.auth_middleware], client_max_size=64 * 1024)
        api = Api(self.bot)
        app.add_routes([web.post("/api/login", self.login), web.get("/api/health", self.health)] + api.routes())
        for path in STATIC_FILES:
            app.router.add_get(path, self.static)
        return app

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app, access_log=None)  # no request log: nothing private ends up in one
        await self.runner.setup()
        await web.TCPSite(self.runner, self.config.web_host, self.config.web_port).start()
        log.info("Web app on http://%s:%s (sign in with /web in Telegram)", self.config.web_host, self.config.web_port)

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()  # frees the port for an in-process restart
            self.runner = None

    # --- middleware ---

    @web.middleware
    async def headers_middleware(self, request: web.Request, handler):
        try:
            response = await handler(request)
        except web.HTTPException as e:
            response = e
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self._secure(request):
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if isinstance(response, web.HTTPException) and response.status >= 400:
            raise response
        return response

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
        # Either scheme for our own host: behind an HTTPS proxy (Fly, Caddy) the app sees plain http.
        # A cross-site page still fails: its origin is a different host.
        allowed = {f"http://{request.host}", f"https://{request.host}"}
        if self.config.web_public_url:
            parts = urlsplit(self.config.web_public_url)
            allowed.add(f"{parts.scheme}://{parts.netloc}")
        return origin in allowed

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
        now = time.monotonic()
        self._failures = [t for t in self._failures if now - t < 600]
        if len(self._failures) >= MAX_LOGIN_FAILURES:
            return web.json_response({"error": "Too many tries. Wait a few minutes."}, status=429)
        try:
            token = (await request.json()).get("token")
        except Exception:
            token = None
        if not auth.redeem_login_token(self.db, token):
            self._failures.append(now)
            return web.json_response({"error": "That sign-in link has expired or was already used. "
                                               "Send /web in Telegram for a new one."}, status=401)
        session_id, csrf = auth.new_session(self.db, request.headers.get("User-Agent", ""))
        from ..actions import ActionLog
        ActionLog(self.db).record("security", f"Signed in to the web app ({request.headers.get('User-Agent', '?')[:60]})")
        response = web.json_response({"ok": True, "csrf": csrf})
        response.set_cookie(COOKIE, session_id, max_age=int(auth.SESSION_TTL.total_seconds()), path="/",
                            httponly=True, samesite="Strict", secure=self._secure(request))
        return response
