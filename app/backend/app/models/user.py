from datetime import datetime
from sqlalchemy import ForeignKey, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, utcnow


class Tenant(Base):
    __tablename__ = "tenant"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="Default")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="STAFF", index=True)
    user_type: Mapped[str] = mapped_column(String(1), default="B", index=True)
    username: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    visitor_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    visitor_secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browser_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), default="CUSTOMER_SERVICE")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_version: Mapped[int] = mapped_column(default=0, server_default="0")
    work_status: Mapped[str] = mapped_column(String(16), default="OFFLINE", server_default="OFFLINE")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
