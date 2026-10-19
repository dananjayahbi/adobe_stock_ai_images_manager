"""HTTP middleware enforcing the signed session cookie on every route.

Exemptions (checked per request, in this order):

1. ``AUTH_ENABLED = False`` — pass everything through.  This is the test
   suite's escape hatch: ``conftest.py``'s ``client`` fixture flips it off so
   the pre-auth tests never need a login, and the middleware reads the flag
   *per request* (never captured at install time) so tests can also toggle it
   mid-test with ``monkeypatch``.
2. ``OPTIONS`` — CORS preflights carry no cookies, so rejecting them would
   break cross-origin calls before the browser ever sends credentials.
3. A small public allowlist — the login/logout endpoints (you cannot require
   a session to obtain one), plus framework/utility paths (``/health``,
   ``/docs``, ``/redoc``, ``/openapi.json``, ``/favicon.ico``).

Everything else — *including* ``/api/auth/me`` (the frontend probes it to
learn session state and expects the standard 401 shape when logged out),
all ``/api/*`` data endpoints, ``/thumbnails`` static files, and unknown
paths — must present a valid, unexpired cookie or receives
``401 {"detail": "Not authenticated"}`` before routing ever runs.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from auth_config import auth_settings
from services.auth_service import verify_token

#: Exempt prefixes — login/logout must work before a session exists, the
#: docs UI serves sub-assets from under its root path, and ``/flutter`` is
#: the public shell of the mobile web build (static JS/HTML only — every
#: ``/api/*`` call it makes still requires the cookie).
_ALLOWLIST_PREFIXES = (
    "/api/auth/login",
    "/api/auth/logout",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/flutter",
)
#: Exempt exact paths — single endpoints with no sub-assets.
_ALLOWLIST_EXACT = frozenset({"/health", "/favicon.ico"})


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests with the standard 401 payload."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Read the flag per request: tests monkeypatch AUTH_ENABLED at
        # runtime, so caching it when the middleware is installed would
        # silently ignore them (and keep the 62-file legacy suite locked out).
        if not auth_settings.AUTH_ENABLED:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in _ALLOWLIST_EXACT or path.startswith(_ALLOWLIST_PREFIXES):
            return await call_next(request)

        token = request.cookies.get(auth_settings.AUTH_COOKIE_NAME)
        if token is None or verify_token(token) is None:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        return await call_next(request)


def install_auth_middleware(app: FastAPI) -> None:
    """Add the session-checking middleware to ``app`` (single middleware).

    Call once at startup; whether auth is active is decided per request via
    ``auth_settings.AUTH_ENABLED`` — see the module docstring for why.
    """
    app.add_middleware(AuthMiddleware)
