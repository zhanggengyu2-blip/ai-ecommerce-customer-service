from datetime import datetime
from sqlalchemy import ForeignKey, String, Integer, DateTime, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, utcnow


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConfigVersion(Base):
    __tablename__ = "config_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    value: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "version"),)


class PromptTemplate(Base):
    __tablename__ = "prompt_template"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_prompt_template_tenant_key"),)
