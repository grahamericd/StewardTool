from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import AppUser, OrganizationMembership

def current_context(x_user_email: str = Header(default="steward@demo.gov", alias="X-User-Email"), db: Session = Depends(get_db)):
    user=db.scalar(select(AppUser).where(AppUser.email==x_user_email))
    if not user: raise HTTPException(401,"Unknown demo user")
    m=db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id==user.id, OrganizationMembership.is_active.is_(True)))
    if not m: raise HTTPException(403,"No active organization membership")
    return {"user":user,"membership":m,"organization_id":m.organization_id,"role":m.role}

def require_roles(*roles):
    def dep(ctx=Depends(current_context)):
        if ctx["role"] not in roles: raise HTTPException(403,f"Requires one of: {', '.join(roles)}")
        return ctx
    return dep
