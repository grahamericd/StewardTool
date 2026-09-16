import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_context, hash_password, issue_local_token, verify_password
from ..config import settings
from ..db import get_db
from ..models import AppUser, LocalAuthCredential, OrganizationMembership
from ..schemas import ChangePasswordRequest, LoginRequest

router = APIRouter(prefix="/auth", tags=["authentication"])

_LOGIN_FAILURES: dict[str, list[datetime]] = {}
_LOGIN_FAILURES_LOCK = Lock()


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """A hash no password can match, used to keep failed sign-ins constant time."""
    return hash_password(secrets.token_urlsafe(32))


def _client_address(request: Request) -> str:
    """The caller's address, trusting only as many proxies as are configured.

    Taking the first X-Forwarded-For entry trusted whatever the client sent:
    Caddy and nginx both append to the header rather than replacing it, so a
    caller could defeat the throttle entirely by varying that value. Each
    trusted proxy appends exactly one entry, so with N proxies the address the
    innermost trusted proxy observed is the Nth from the end.
    """
    peer = request.client.host if request.client else "unknown"
    hops = settings.auth_trusted_proxy_hops
    if hops <= 0:
        return peer
    forwarded = [
        part.strip()
        for part in request.headers.get("x-forwarded-for", "").split(",")
        if part.strip()
    ]
    if len(forwarded) >= hops:
        return forwarded[-hops]
    return peer


def _login_keys(request: Request, email: str) -> list[str]:
    """Throttle per source address and, independently, per account.

    The account key cannot be influenced by any request header, so rotating
    addresses no longer gives an attacker unlimited attempts against one user.
    """
    return [f"ip:{_client_address(request)}|{email.lower()}", f"account:{email.lower()}"]


def _prune_failures(key: str, now: datetime) -> list[datetime]:
    cutoff = now - timedelta(minutes=settings.auth_login_window_minutes)
    failures = [ts for ts in _LOGIN_FAILURES.get(key, []) if ts >= cutoff]
    if failures:
        _LOGIN_FAILURES[key] = failures
    else:
        _LOGIN_FAILURES.pop(key, None)
    return failures


def _check_login_throttle(keys: list[str]):
    now = datetime.now(timezone.utc)
    with _LOGIN_FAILURES_LOCK:
        for key in keys:
            failures = _prune_failures(key, now)
            if len(failures) >= settings.auth_login_max_failures:
                raise HTTPException(
                    status_code=429,
                    detail="Too many sign-in attempts. Try again later.",
                    headers={"Retry-After": str(settings.auth_login_window_minutes * 60)},
                )


def _record_login_failure(keys: list[str]):
    now = datetime.now(timezone.utc)
    with _LOGIN_FAILURES_LOCK:
        for key in keys:
            failures = _prune_failures(key, now)
            failures.append(now)
            _LOGIN_FAILURES[key] = failures


def _clear_login_failures(keys: list[str]):
    with _LOGIN_FAILURES_LOCK:
        for key in keys:
            _LOGIN_FAILURES.pop(key, None)


@router.get("/config")
def auth_config():
    return {
        "mode": settings.auth_mode.lower(),
        "password_min_length": settings.auth_password_min_length,
        "token_hours": settings.auth_token_hours,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    if settings.auth_mode.lower() != "local":
        raise HTTPException(status_code=400, detail="Local sign-in is not enabled")

    email = payload.email.strip().lower()
    login_keys = _login_keys(request, email)
    _check_login_throttle(login_keys)
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    credential = (
        db.scalar(select(LocalAuthCredential).where(LocalAuthCredential.user_id == user.id))
        if user
        else None
    )

    # Verify against a dummy hash for unknown accounts so that the response
    # time does not reveal whether the email exists, and use the same outward
    # error for unknown accounts and incorrect passwords.
    password_ok = (
        verify_password(payload.password, credential.password_hash)
        if credential
        else verify_password(payload.password, _dummy_password_hash())
    )
    if not user or not user.is_active or not credential or not password_ok:
        _record_login_failure(login_keys)
        raise HTTPException(status_code=401, detail="Email or password is incorrect")

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active.is_(True),
        )
    )
    if not membership:
        raise HTTPException(status_code=403, detail="This account does not have an active organization membership")

    _clear_login_failures(login_keys)
    return {
        "access_token": issue_local_token(user),
        "token_type": "bearer",
        "expires_in": settings.auth_token_hours * 3600,
        "must_change_password": credential.must_change_password,
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    ctx=Depends(current_context),
    db: Session = Depends(get_db),
):
    if settings.auth_mode.lower() != "local":
        raise HTTPException(status_code=400, detail="Password management is not enabled for this authentication mode")

    credential = db.scalar(
        select(LocalAuthCredential).where(LocalAuthCredential.user_id == ctx["user"].id)
    )
    if not credential or not verify_password(payload.current_password, credential.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    try:
        credential.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    credential.must_change_password = False
    credential.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok"}


@router.post("/logout")
def logout():
    # Local tokens are short-lived and stored client-side. Removing the token
    # from the browser completes logout. Server-side revocation can be added
    # later without changing the API contract.
    return {"status": "ok"}
