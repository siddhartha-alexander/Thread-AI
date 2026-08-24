import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend import models
from backend.config import Settings, get_settings
from backend.database import get_db

SESSION_COOKIE = "thread_ai_session"
STATE_COOKIE = "thread_ai_oauth_state"


def auth_configured(settings: Settings) -> bool:
    return bool(settings.google_client_id and settings.google_client_secret and settings.auth_secret != "change-this-before-deployment")


def google_redirect_uri(settings: Settings) -> str:
    return f"{settings.backend_url.rstrip('/')}/api/auth/google/callback"


def google_authorization_url(settings: Settings, state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": google_redirect_uri(settings),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def create_session_token(user_id: str, settings: Settings) -> str:
    payload = {"sub": user_id, "iat": int(time.time())}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.auth_secret.encode(), encoded.encode(), hashlib.sha256).digest()
    signed = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{encoded}.{signed}"


def read_session_token(token: str, settings: Settings) -> str | None:
    try:
        encoded, signed = token.split(".", 1)
        expected = hmac.new(settings.auth_secret.encode(), encoded.encode(), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(signed + "=" * (-len(signed) % 4))
        if not hmac.compare_digest(expected, actual):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if int(time.time()) - int(payload["iat"]) > settings.session_days * 24 * 60 * 60:
            return None
        return str(payload["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


async def exchange_google_code(code: str, settings: Settings) -> dict:
    token_payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": google_redirect_uri(settings),
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post("https://oauth2.googleapis.com/token", data=token_payload)
        token_response.raise_for_status()
        id_token = token_response.json().get("id_token")
        if not id_token:
            raise HTTPException(status_code=502, detail="Google did not return an identity token.")
        info_response = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
        info_response.raise_for_status()
    profile = info_response.json()
    if profile.get("aud") != settings.google_client_id:
        raise HTTPException(status_code=401, detail="Google sign-in audience did not match this app.")
    if profile.get("email_verified") not in {True, "true", "True"}:
        raise HTTPException(status_code=401, detail="Google account email is not verified.")
    return profile


def upsert_google_user(db: Session, profile: dict) -> models.User:
    provider_sub = str(profile["sub"])
    user = db.query(models.User).filter(models.User.provider_sub == provider_sub).first()
    if user is None:
        user = models.User(email=profile["email"], provider_sub=provider_sub)
        db.add(user)
    user.email = profile["email"]
    user.name = profile.get("name")
    user.avatar_url = profile.get("picture")
    user.provider = "google"
    db.commit()
    db.refresh(user)
    return user


def upsert_dev_user(db: Session) -> models.User:
    provider_sub = "thread-ai-local-preview"
    user = db.query(models.User).filter(models.User.provider_sub == provider_sub).first()
    if user is None:
        user = models.User(email="local-preview@thread.ai", provider_sub=provider_sub)
        db.add(user)
    user.name = "Local Preview"
    user.provider = "local"
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> models.User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required.")
    user_id = read_session_token(token, settings)
    if not user_id:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Session user was not found.")
    return user


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)
