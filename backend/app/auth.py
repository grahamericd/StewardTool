import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AppUser, LocalAuthCredential, OrganizationMembership

logger = logging.getLogger("ai_data_steward.auth")


def _utcnow():
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    if len(password) < settings.auth_password_min_length:
        raise ValueError(f"Password must be at least {settings.auth_password_min_length} characters")
    salt = os.urandom(16)
    # scrypt is deliberately memory-hard and available in Python's standard library.
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(hash_b64.encode())
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def issue_local_token(user: AppUser) -> str:
    if not settings.auth_secret_key:
        raise RuntimeError("AUTH_SECRET_KEY is required for local authentication")
    now = _utcnow()
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(hours=settings.auth_token_hours),
        "iss": "ai-data-steward",
        "aud": "ai-data-steward",
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm="HS256")


def decode_local_token(token: str) -> dict:
    if not settings.auth_secret_key:
        raise HTTPException(status_code=500, detail="Local authentication is not configured")
    try:
        return jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=["HS256"],
            issuer="ai-data-steward",
            audience="ai-data-steward",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")


@lru_cache(maxsize=1)
def _jwks_client():
    if settings.oidc_jwks_url:
        return PyJWKClient(settings.oidc_jwks_url)
    if not settings.oidc_issuer:
        raise RuntimeError("OIDC_ISSUER or OIDC_JWKS_URL must be configured")
    response = httpx.get(
        f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        timeout=10,
    )
    response.raise_for_status()
    return PyJWKClient(response.json()["jwks_uri"])


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    return auth.split(" ", 1)[1]


def _identity(request: Request, demo_email: str | None) -> tuple[str | None, int | None]:
    mode = settings.auth_mode.lower()

    if mode == "demo":
        return demo_email or "steward@demo.gov", None

    if mode == "local":
        claims = decode_local_token(_bearer_token(request))
        try:
            user_id = int(claims["sub"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid session identity")
        return claims.get("email"), user_id

    if mode == "oidc":
        token = _bearer_token(request)
        try:
            signing_key = _jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                audience=settings.oidc_audience,
                issuer=settings.oidc_issuer,
                options={"verify_aud": bool(settings.oidc_audience)},
            )
        except Exception as exc:
            # The provider's message can name internal hosts and key ids, so it
            # is logged rather than returned.
            logger.warning("Rejected OIDC token: %s", exc)
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        email = claims.get(settings.oidc_email_claim)
        if not email:
            raise HTTPException(status_code=401, detail=f"Token missing {settings.oidc_email_claim} claim")
        return email, None

    raise HTTPException(status_code=500, detail=f"Unsupported AUTH_MODE: {settings.auth_mode}")


def current_context(
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    db: Session = Depends(get_db),
):
    email, local_user_id = _identity(request, x_user_email)

    if local_user_id is not None:
        user = db.get(AppUser, local_user_id)
        # Also compare the token email to the current account email. This makes
        # a renamed account invalidate old tokens instead of silently changing identity.
        if not user or not user.is_active or user.email.lower() != (email or "").lower():
            raise HTTPException(status_code=401, detail="This account is no longer available")
    else:
        user = db.scalar(select(AppUser).where(AppUser.email == email))
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="Authenticated user is not provisioned in AI Data Steward")

    memberships = db.scalars(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active.is_(True),
        )
    ).all()
    if not memberships:
        raise HTTPException(status_code=403, detail="User has no active organization membership")

    membership = memberships[0]
    credential = None
    if settings.auth_mode.lower() == "local":
        credential = db.scalar(select(LocalAuthCredential).where(LocalAuthCredential.user_id == user.id))

    return {
        "user": user,
        "membership": membership,
        "organization_id": membership.organization_id,
        "role": membership.role,
        "must_change_password": bool(credential.must_change_password) if credential else False,
    }


def require_roles(*roles):
    def _dependency(ctx=Depends(current_context)):
        if ctx["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(roles)}")
        return ctx
    return _dependency
