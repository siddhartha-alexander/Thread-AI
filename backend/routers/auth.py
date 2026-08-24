import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from backend import models
from backend.auth import (
    SESSION_COOKIE,
    STATE_COOKIE,
    auth_configured,
    create_session_token,
    exchange_google_code,
    get_current_user,
    google_authorization_url,
    new_oauth_state,
    upsert_dev_user,
    upsert_google_user,
)
from backend.config import Settings, get_settings
from backend.database import get_db
from backend.schemas import AuthConfigResponse, AuthStatusResponse, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_read(user: models.User) -> UserRead:
    return UserRead(id=user.id, email=user.email, name=user.name, avatar_url=user.avatar_url)


def cookie_samesite(settings: Settings) -> str:
    value = settings.cookie_samesite.lower()
    return value if value in {"lax", "strict", "none"} else "lax"


@router.get("/me", response_model=AuthStatusResponse)
def me(user: models.User = Depends(get_current_user)) -> AuthStatusResponse:
    return AuthStatusResponse(authenticated=True, user=user_read(user))


@router.get("/config", response_model=AuthConfigResponse)
def config(settings: Settings = Depends(get_settings)) -> AuthConfigResponse:
    return AuthConfigResponse(google_configured=auth_configured(settings), dev_auth_enabled=settings.allow_dev_auth)


@router.post("/dev-login", response_model=AuthStatusResponse)
def dev_login(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    if not settings.allow_dev_auth:
        raise HTTPException(status_code=403, detail="Local preview sign-in is disabled.")
    user = upsert_dev_user(db)
    response = JSONResponse(AuthStatusResponse(authenticated=True, user=user_read(user)).model_dump(mode="json"))
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id, settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=cookie_samesite(settings),
        max_age=settings.session_days * 24 * 60 * 60,
    )
    return response


@router.get("/google/start")
def google_start(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if not auth_configured(settings):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    state = new_oauth_state()
    response = RedirectResponse(google_authorization_url(settings, state), status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        state,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=cookie_samesite(settings),
        max_age=10 * 60,
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    frontend_url = settings.frontend_url.rstrip("/")
    if error:
        return RedirectResponse(f"{frontend_url}/?auth_error=google_cancelled", status_code=302)
    if not code or not state or request.cookies.get(STATE_COOKIE) != state:
        return RedirectResponse(f"{frontend_url}/?auth_error=invalid_oauth_state", status_code=302)
    try:
        profile = await exchange_google_code(code, settings)
        user = upsert_google_user(db, profile)
    except (httpx.HTTPError, HTTPException):
        return RedirectResponse(f"{frontend_url}/?auth_error=google_failed", status_code=302)
    response = RedirectResponse(frontend_url, status_code=302)
    response.delete_cookie(STATE_COOKIE)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id, settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=cookie_samesite(settings),
        max_age=settings.session_days * 24 * 60 * 60,
    )
    return response


@router.post("/logout", status_code=204)
def logout(settings: Settings = Depends(get_settings)) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(STATE_COOKIE)
    return response
