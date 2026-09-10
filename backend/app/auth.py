import json
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AppUser, OrganizationMembership


@lru_cache(maxsize=1)
def _jwks_client():
    if settings.oidc_jwks_url:
        return PyJWKClient(settings.oidc_jwks_url)
    if not settings.oidc_issuer:
        raise RuntimeError("OIDC_ISSUER or OIDC_JWKS_URL must be configured")
    discovery = httpx.get(f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration", timeout=10).json()
    return PyJWKClient(discovery["jwks_uri"])


def _identity_email(request: Request, demo_email: str | None):
    if settings.auth_mode.lower() == "demo":
        return demo_email or "steward@demo.gov"

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = auth.split(" ", 1)[1]
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
        raise HTTPException(status_code=401, detail=f"Invalid identity token: {exc}")

    email = claims.get(settings.oidc_email_claim)
    if not email:
        raise HTTPException(status_code=401, detail=f"Token missing {settings.oidc_email_claim} claim")
    return email


def current_context(
    request: Request,
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    db: Session = Depends(get_db),
):
    email = _identity_email(request, x_user_email)
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    if not user:
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
    return {
        "user": user,
        "membership": membership,
        "organization_id": membership.organization_id,
        "role": membership.role,
    }


def require_roles(*roles):
    def _dependency(ctx=Depends(current_context)):
        if ctx["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(roles)}")
        return ctx
    return _dependency
