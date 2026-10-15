"""Signed session tokens and cookie helpers — stdlib only.

The token format is a compact, dependency-free JWS-style string::

    base64url(json_payload) + "." + base64url(hmac_sha256(secret, payload_b64))

with payload ``{"u": username, "exp": unix_expiry}``.  A flipped byte anywhere
breaks the signature (verified with ``hmac.compare_digest`` to avoid timing
oracle differences), and an expired ``exp`` is rejected on read — there is no
server-side session store to consult or clean up, which suits a local-first
app.

All settings are read from ``auth_settings`` *at call time* so tests can
monkeypatch credentials, TTL, or the cookie name on the shared instance.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from auth_config import auth_settings


def _b64url_encode(data: bytes) -> str:
    """URL-safe base64 without padding (``=`` would clutter the cookie)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Inverse of :func:`_b64url_encode`; restores the stripped padding."""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def create_token(username: str) -> str:
    """Sign a session token for ``username``, expiring per current TTL."""
    ttl_seconds = auth_settings.AUTH_SESSION_TTL_HOURS * 3600
    payload = {"u": username, "exp": int(time.time()) + ttl_seconds}
    payload_b64 = _b64url_encode(json.dumps(payload).encode("utf-8"))
    signature = hmac.new(
        auth_settings.AUTH_SECRET_KEY.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}"


def verify_token(token: str) -> str | None:
    """Return the username carried by ``token``, or ``None`` if it is unusable.

    ``None`` covers every rejection reason: malformed structure, undecodable
    payload, signature mismatch (tampering), and expired sessions.
    """
    try:
        payload_b64, signature_b64 = token.split(".")
        expected = hmac.new(
            auth_settings.AUTH_SECRET_KEY.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64url_decode(signature_b64), expected):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

    username = payload.get("u")
    exp = payload.get("exp")
    if not isinstance(username, str) or not isinstance(exp, (int, float)):
        return None
    if int(time.time()) >= exp:
        return None
    return username


def check_credentials(username: str, password: str) -> bool:
    """Constant-time comparison against the configured local account."""
    return hmac.compare_digest(
        username.encode("utf-8"), auth_settings.AUTH_USERNAME.encode("utf-8")
    ) and hmac.compare_digest(
        password.encode("utf-8"), auth_settings.AUTH_PASSWORD.encode("utf-8")
    )


def set_session_cookie(response, token: str) -> None:
    """Attach the signed session cookie to ``response``.

    ``httponly`` keeps the token out of JS reach; ``samesite="lax"`` blocks
    cross-site form POSTs while still allowing normal top-level navigation.
    """
    response.set_cookie(
        auth_settings.AUTH_COOKIE_NAME,
        token,
        max_age=auth_settings.AUTH_SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    """Remove the session cookie (logout must succeed even if it is absent)."""
    response.delete_cookie(auth_settings.AUTH_COOKIE_NAME, path="/")
