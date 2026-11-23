from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db import Base
from app.models.enums import UserRole
from app.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))

    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))

    auth_provider: Mapped[str] = mapped_column(String(50), default="local")
    provisioning_source: Mapped[str] = mapped_column(String(50), default="seed")

    is_active: Mapped[bool] = mapped_column(default=True)

    # HR admins only: may also manage accounts. A switch, not a role, so
    # the hiring routes need not care. Nobody can remove their own, so at
    # least one always remains.
    is_super_admin: Mapped[bool] = mapped_column(default=False, server_default="false")

    # last password change or reset; any session begun before it is
    # refused (infra/deps.py). Null means never changed
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Set by the person themselves on their Account Settings page. The
    # photo is a file name under uploads/avatars -- random, so
    # it is also the thing its public URL is built from (see
    # api/account.py) -- and null means "show initials", as everyone had
    # before photos existed.
    avatar_file: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Staff only (HR admins and evaluators): shown beside their name where
    # HR picks evaluators, so "Dean, College of Engineering" is chosen on
    # purpose rather than by guessing from a name. Never set for an
    # applicant -- the API refuses it.
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
