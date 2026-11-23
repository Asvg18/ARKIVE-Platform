"""Create one demo user per role for local testing. Safe to re-run — an
existing email is left untouched rather than duplicated or overwritten.

Usage (from backend/, with the venv active):
    python -m scripts.seed_demo_users

For demos and testing only. Every account it makes shares one password
that is written in this file and in the docs -- a real installation
starts with scripts/create_first_admin.py instead.
"""

from datetime import datetime, timezone
from sqlalchemy import select

from app.infra.db import SessionLocal
from app.infra.security import hash_password
from app.models.enums import UserRole
from app.models.user import User

DEMO_PASSWORD = "demo-password-123"

# evaluator accounts have no type/category -- HR assigns specific named
# evaluators to specific interview rounds via a per-job pool, not a
# fixed dept_head/vp classification. three accounts here so there's a
# real pool to demo, not just one-per-round.
DEMO_USERS = [
    dict(email="applicant@arkive.demo", full_name="Ada Applicant", role=UserRole.applicant),
    dict(email="hr@arkive.demo", full_name="Harper Administrator", role=UserRole.hr_admin),
    dict(email="depthead@arkive.demo", full_name="Devon Depthead", role=UserRole.evaluator),
    dict(email="vp@arkive.demo", full_name="Val Veep", role=UserRole.evaluator),
    dict(email="kenneth.villabroza@arkive.demo", full_name="Kenneth Villabroza", role=UserRole.evaluator),
]


def seed() -> None:
    db = SessionLocal()
    try:
        for spec in DEMO_USERS:
            existing = db.scalar(select(User).where(User.email == spec["email"]))
            if existing is not None:
                print(f"skip (already exists): {spec['email']}")
                continue

            user = User(
                email=spec["email"],
                hashed_password=hash_password(DEMO_PASSWORD),
                full_name=spec["full_name"],
                role=spec["role"],
                auth_provider="local",
                provisioning_source="seed",
                email_verified_at=datetime.now(timezone.utc),
                # The demo's one HR admin plays the organization's first
                # HR admin, who is always a super admin -- otherwise the
                # demo would have nobody able to open User Management.
                is_super_admin=spec["role"] == UserRole.hr_admin,
            )
            db.add(user)
            print(f"created: {spec['email']} ({spec['role'].value})")

        db.commit()
    finally:
        db.close()

    print(f"\nAll demo users share the password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    seed()
