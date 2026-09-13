import argparse
import getpass

from sqlalchemy import select

from .auth import hash_password
from .db import Base, SessionLocal, engine
from .models import AppUser, LocalAuthCredential, Organization, OrganizationMembership


def main():
    parser = argparse.ArgumentParser(description="Create or update the initial AI Data Steward organization administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--org-code", default="DEFAULT")
    parser.add_argument("--org-name", required=True)
    args = parser.parse_args()

    password = getpass.getpass("New administrator password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc))

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        email = args.email.strip().lower()
        org = db.scalar(select(Organization).where(Organization.code == args.org_code))
        if not org:
            org = Organization(code=args.org_code, name=args.org_name)
            db.add(org)
            db.flush()

        user = db.scalar(select(AppUser).where(AppUser.email == email))
        if not user:
            user = AppUser(email=email, display_name=args.name.strip(), is_active=True)
            db.add(user)
            db.flush()
        else:
            user.display_name = args.name.strip()
            user.is_active = True

        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == org.id,
            )
        )
        if not membership:
            membership = OrganizationMembership(
                user_id=user.id,
                organization_id=org.id,
                role="ORG_ADMIN",
                is_active=True,
            )
            db.add(membership)
        else:
            membership.role = "ORG_ADMIN"
            membership.is_active = True

        credential = db.scalar(
            select(LocalAuthCredential).where(LocalAuthCredential.user_id == user.id)
        )
        if not credential:
            credential = LocalAuthCredential(
                user_id=user.id,
                password_hash=password_hash,
                must_change_password=False,
            )
            db.add(credential)
        else:
            credential.password_hash = password_hash
            credential.must_change_password = False

        db.commit()

    print(f"Administrator ready: {email}")
    print(f"Organization: {args.org_name} ({args.org_code})")


if __name__ == "__main__":
    main()
