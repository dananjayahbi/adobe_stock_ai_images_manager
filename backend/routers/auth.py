"""Auth router — login, logout, and session probe for the frontend.

``POST /api/auth/login`` exchanges the local account for a signed session
cookie; ``POST /api/auth/logout`` discards it; ``GET /api/auth/me`` reports
who the cookie belongs to (the frontend calls it to decide between the login
form and the app shell).  ``/me`` is *not* exempt in the middleware: with no
or an invalid cookie the middleware already returns the same
``401 {"detail": "Not authenticated"}`` shape this handler would produce, so
the frontend sees one consistent contract either way.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth_config import auth_settings
from services.auth_service import (
    check_credentials,
    clear_session_cookie,
    create_token,
    set_session_cookie,
    verify_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Body of the login endpoint: the single local account's credentials."""

    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest) -> JSONResponse:
    """Validate credentials and set the signed session cookie.

    401 ``{"detail": "Invalid credentials"}`` on any mismatch; on success the
    cookie is attached to an explicitly constructed JSONResponse so the token
    ships with the very response that confirms the login.
    """
    if not check_credentials(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response = JSONResponse({"user": {"username": payload.username}})
    set_session_cookie(response, create_token(payload.username))
    return response


@router.post("/logout")
def logout() -> JSONResponse:
    """Clear the session cookie. Always succeeds — even with no valid
    session — because the middleware exempts this path."""
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response


@router.get("/me")
def me(request: Request) -> dict:
    """Return the session's user, or 401 when the cookie is missing/invalid."""
    token = request.cookies.get(auth_settings.AUTH_COOKIE_NAME)
    username = verify_token(token) if token is not None else None
    if username is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": {"username": username}}
