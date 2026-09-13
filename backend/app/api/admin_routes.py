import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_context, hash_password, require_roles
from ..config import settings
from ..db import get_db
from ..models import AppUser, LocalAuthCredential, OrganizationMembership
from ..schemas import OrganizationUserCreate, OrganizationUserUpdate

router = APIRouter(prefix="/admin", tags=["administration"])

ALLOWED_ROLES = {
    "STEWARD",
    "APPROVER",
    "ORG_ADMIN",
    "VIEWER",
    "ENTERPRISE_ADMIN",
}
MANAGEMENT_ROLES = {"ORG_ADMIN", "ENTERPRISE_ADMIN"}


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    return email


def _serialize_membership(membership: OrganizationMembership, db: Session) -> dict:
    user = membership.user
    credential = db.scalar(
        select(LocalAuthCredential).where(LocalAuthCredential.user_id == user.id)
    )
    return {
        "user_id": user.id,
        "membership_id": membership.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": membership.role,
        "membership_active": membership.is_active,
        "account_active": user.is_active,
        "has_local_password": credential is not None,
        "must_change_password": bool(credential.must_change_password) if credential else False,
        "created_at": user.created_at,
    }


def _active_management_admin_count(db: Session, organization_id: int) -> int:
    return db.scalar(
        select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.role.in_(MANAGEMENT_ROLES),
        )
    ) or 0


def _temporary_password() -> str:
    # URL-safe, high-entropy temporary password. The user is forced to change it.
    return secrets.token_urlsafe(18)


@router.get("/users")
def list_users(
    ctx=Depends(require_roles("ORG_ADMIN", "ENTERPRISE_ADMIN")),
    db: Session = Depends(get_db),
):
    memberships = db.scalars(
        select(OrganizationMembership)
        .where(OrganizationMembership.organization_id == ctx["organization_id"])
        .order_by(OrganizationMembership.created_at.asc())
    ).all()
    return {
        "auth_mode": settings.auth_mode.lower(),
        "roles": sorted(ALLOWED_ROLES),
        "current_user_id": ctx["user"].id,
        "users": [_serialize_membership(m, db) for m in memberships],
    }


@router.post("/users")
def create_user(
    payload: OrganizationUserCreate,
    ctx=Depends(require_roles("ORG_ADMIN", "ENTERPRISE_ADMIN")),
    db: Session = Depends(get_db),
):
    role = payload.role.strip().upper()
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Unknown role")

    email = _normalize_email(payload.email)
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    if not user:
        user = AppUser(
            email=email,
            display_name=payload.display_name.strip(),
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        if not user.is_active:
            user.is_active = True
        if payload.display_name.strip():
            user.display_name = payload.display_name.strip()

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == ctx["organization_id"],
        )
    )
    if membership:
        raise HTTPException(
            status_code=409,
            detail="This user already has a membership in your organization",
        )

    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=ctx["organization_id"],
        role=role,
        is_active=True,
    )
    db.add(membership)

    temporary_password = None
    if settings.auth_mode.lower() == "local":
        credential = db.scalar(
            select(LocalAuthCredential).where(LocalAuthCredential.user_id == user.id)
        )
        if not credential:
            temporary_password = _temporary_password()
            credential = LocalAuthCredential(
                user_id=user.id,
                password_hash=hash_password(temporary_password),
                must_change_password=True,
            )
            db.add(credential)

    db.commit()
    db.refresh(membership)

    return {
        "user": _serialize_membership(membership, db),
        "temporary_password": temporary_password,
        "message": (
            "User created. Share the temporary password securely; it is only shown once."
            if temporary_password
            else "User added to the organization."
        ),
    }


@router.patch("/users/{membership_id}")
def update_user(
    membership_id: int,
    payload: OrganizationUserUpdate,
    ctx=Depends(require_roles("ORG_ADMIN", "ENTERPRISE_ADMIN")),
    db: Session = Depends(get_db),
):
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == ctx["organization_id"],
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Organization user not found")

    is_self = membership.user_id == ctx["user"].id

    if payload.role is not None:
        role = payload.role.strip().upper()
        if role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail="Unknown role")
        if is_self and role != membership.role:
            raise HTTPException(
                status_code=400,
                detail="You cannot change your own administrator role",
            )
        if (
            membership.is_active
            and membership.role in MANAGEMENT_ROLES
            and role not in MANAGEMENT_ROLES
            and _active_management_admin_count(db, ctx["organization_id"]) <= 1
        ):
            raise HTTPException(
                status_code=400,
                detail="At least one active organization administrator must remain",
            )
        membership.role = role

    if payload.membership_active is not None:
        if is_self and not payload.membership_active:
            raise HTTPException(
                status_code=400,
                detail="You cannot deactivate your own organization membership",
            )
        if (
            membership.is_active
            and not payload.membership_active
            and membership.role in MANAGEMENT_ROLES
            and _active_management_admin_count(db, ctx["organization_id"]) <= 1
        ):
            raise HTTPException(
                status_code=400,
                detail="At least one active organization administrator must remain",
            )
        membership.is_active = payload.membership_active

    if payload.display_name is not None:
        membership.user.display_name = payload.display_name.strip()

    db.commit()
    db.refresh(membership)
    return _serialize_membership(membership, db)


@router.post("/users/{membership_id}/reset-password")
def reset_password(
    membership_id: int,
    ctx=Depends(require_roles("ORG_ADMIN", "ENTERPRISE_ADMIN")),
    db: Session = Depends(get_db),
):
    if settings.auth_mode.lower() != "local":
        raise HTTPException(
            status_code=400,
            detail="Password reset is only available when local authentication is enabled",
        )

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == ctx["organization_id"],
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Organization user not found")
    if membership.user_id == ctx["user"].id:
        raise HTTPException(
            status_code=400,
            detail="Use Change Password for your own account",
        )
    if not membership.is_active or not membership.user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Reactivate this user before resetting their password",
        )

    temporary_password = _temporary_password()
    credential = db.scalar(
        select(LocalAuthCredential).where(
            LocalAuthCredential.user_id == membership.user_id
        )
    )
    if not credential:
        credential = LocalAuthCredential(
            user_id=membership.user_id,
            password_hash=hash_password(temporary_password),
            must_change_password=True,
        )
        db.add(credential)
    else:
        credential.password_hash = hash_password(temporary_password)
        credential.must_change_password = True
        credential.password_changed_at = datetime.now(timezone.utc)

    db.commit()
    return {
        "temporary_password": temporary_password,
        "message": "Temporary password generated. It is only shown once.",
    }
