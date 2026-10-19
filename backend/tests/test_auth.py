"""Auth tests: credential check, signed cookie lifecycle, middleware gate.

Two fixtures carry the auth state: ``client`` (auth disabled — the legacy
default) and ``auth_client`` (auth enabled and already logged in).  Tests
that need auth on with *no* cookie start from ``client`` and flip
``AUTH_ENABLED`` with ``monkeypatch`` — the middleware reads the flag per
request, so the toggle takes effect immediately.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from auth_config import auth_settings
from services.auth_service import create_token


def _credentials() -> dict[str, str]:
    return {
        "username": auth_settings.AUTH_USERNAME,
        "password": auth_settings.AUTH_PASSWORD,
    }


def _expired_token(username: str = "admin") -> str:
    """Manually build a correctly signed but already-expired token."""
    payload = {"u": username, "exp": int(time.time()) - 10}
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
    signature = hmac.new(
        auth_settings.AUTH_SECRET_KEY.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{payload_b64}.{signature_b64}"


def test_login_success_sets_cookie_and_me_returns_user(auth_client):
    """Login 200 + Set-Cookie; the persisted cookie authenticates /me."""
    response = auth_client.post("/api/auth/login", json=_credentials())
    assert response.status_code == 200
    assert response.json() == {"user": {"username": auth_settings.AUTH_USERNAME}}
    set_cookie = response.headers.get("set-cookie", "")
    assert auth_settings.AUTH_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()

    me = auth_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"user": {"username": auth_settings.AUTH_USERNAME}}


def test_login_wrong_password(auth_client):
    """A wrong password is rejected without leaking which field was wrong."""
    response = auth_client.post(
        "/api/auth/login",
        json={"username": auth_settings.AUTH_USERNAME, "password": "nope"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_unauthenticated_protected_path_is_401(client, monkeypatch):
    """No cookie on a data endpoint -> the middleware's standard 401.

    The ``client`` fixture starts with auth off; flipping it per-request
    proves the flag is read live, not captured at middleware install time.
    """
    monkeypatch.setattr(auth_settings, "AUTH_ENABLED", True)
    response = client.get("/api/records")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_tampered_token_is_rejected(client, monkeypatch):
    """Flipping a signature character invalidates the session."""
    monkeypatch.setattr(auth_settings, "AUTH_ENABLED", True)
    token = create_token(auth_settings.AUTH_USERNAME)
    payload_b64, signature_b64 = token.split(".")
    flipped = ("A" if signature_b64[0] != "A" else "B") + signature_b64[1:]
    tampered = f"{payload_b64}.{flipped}"

    response = client.get(
        "/api/auth/me",
        headers={"Cookie": f"{auth_settings.AUTH_COOKIE_NAME}={tampered}"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_expired_token_is_rejected(client, monkeypatch):
    """A correctly signed token past its exp is still refused."""
    monkeypatch.setattr(auth_settings, "AUTH_ENABLED", True)
    response = client.get(
        "/api/auth/me",
        headers={
            "Cookie": f"{auth_settings.AUTH_COOKIE_NAME}={_expired_token()}",
        },
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_unknown_path_401_when_auth_enabled(client, monkeypatch):
    """Even non-existent paths are gated — middleware runs before routing,
    so an unknown path with no cookie is 401, not a routing 404."""
    monkeypatch.setattr(auth_settings, "AUTH_ENABLED", True)
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_unknown_path_404_when_auth_disabled(client):
    """With AUTH_ENABLED False the middleware steps aside: routing decides."""
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 404


def test_logout_clears_cookie(auth_client):
    """Logout returns ok, drops the cookie, and /me 401s afterwards."""
    response = auth_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    me = auth_client.get("/api/auth/me")
    assert me.status_code == 401
    assert me.json() == {"detail": "Not authenticated"}
