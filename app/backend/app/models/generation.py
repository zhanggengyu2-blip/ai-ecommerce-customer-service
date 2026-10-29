from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, utcnow


class JobColumns:
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenant.id'), index=True)
    status: Mapped[str] = mapped_column(String(16), default='PENDING', index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AiGeneration(JobColumns, Base):
    __tablename__ = 'ai_generation'
    conversation_id: Mapped[int] = mapped_column(ForeignKey('conversation.id'), index=True)
    source_message_id: Mapped[int] = mapped_column(ForeignKey('message.id'))
    reception_epoch: Mapped[int] = mapped_column()
    mode: Mapped[str] = mapped_column(String(16), default='REPLY')
    config_version: Mapped[int | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint('tenant_id', 'conversation_id', 'source_message_id', 'mode', name='uq_generation_source'),)


class KnowledgeJob(JobColumns, Base):
    __tablename__ = 'knowledge_job'
    kind: Mapped[str] = mapped_column(String(16))
    document_version_id: Mapped[int | None] = mapped_column(ForeignKey('document_version.id'), nullable=True)
    config_id: Mapped[int | None] = mapped_column(ForeignKey('config_version.id'), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey('user.id'))
    expected_revision: Mapped[int] = mapped_column(default=1)
    based_on_config: Mapped[int] = mapped_column(default=0)
    source_revisions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
