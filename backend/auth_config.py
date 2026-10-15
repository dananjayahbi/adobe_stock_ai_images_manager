"""Standalone settings for the local-first authentication layer.

This module is deliberately kept *out of* ``config.py``: the auth feature is
developed alongside other backend work, and a separate file means parallel
changes to the central settings module can never conflict with it. It reads
the same ``.env`` files as ``config`` (repo root first, then ``backend/``)
so operators configure everything in one place.

Environment variables (all optional — the defaults describe a local-only
install with an ``admin``/``admin`` login):

* ``AUTH_ENABLED``          - master switch; ``False`` passes everything through
* ``AUTH_USERNAME``         - the single local account
* ``AUTH_PASSWORD``         - its password
* ``AUTH_SECRET_KEY``       - HMAC key signing session cookies
* ``AUTH_SESSION_TTL_HOURS``- session lifetime in hours
* ``AUTH_COOKIE_NAME``      - name of the session cookie
"""

from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve repo root (one level above backend/) locally rather than importing
# from config.py — auth must stay importable even while config is in flux.
_REPO_ROOT = Path(__file__).resolve().parent.parent


class AuthSettings(BaseSettings):
    """Settings for login, signed session cookies, and middleware enforcement."""

    #: Master switch. ``False`` disables login enforcement entirely — the test
    #: suite relies on flipping this per-test instead of sending cookies.
    AUTH_ENABLED: bool = True
    #: Single local account (this is a local-first app, not a multi-user service).
    AUTH_USERNAME: str = "admin"
    AUTH_PASSWORD: str = "admin"
    #: HMAC-SHA256 key for session tokens. Override in .env for anything
    #: beyond casual local use; the default only needs to be stable, not secret.
    AUTH_SECRET_KEY: str = "dev-secret-change-me"
    #: How long a signed session stays valid before the cookie must be renewed.
    AUTH_SESSION_TTL_HOURS: int = 24
    #: Browser cookie carrying the signed session token.
    AUTH_COOKIE_NAME: str = "studio_session"

    model_config = {
        # Accept .env at the repo root or beside the backend code; backend/ wins.
        "env_file": (str(_REPO_ROOT / ".env"), str(_REPO_ROOT / "backend" / ".env")),
        "env_file_encoding": "utf-8",
        # .env is shared with config.Settings: ignore every key that belongs
        # to the main app instead of failing on "extra_forbidden".
        "extra": "ignore",
    }


auth_settings = AuthSettings()
