from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Integer, DateTime, JSON, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import LONGTEXT
from app.models.base import Base, utcnow


class KnowledgeCategory(Base):
    __tablename__ = 'knowledge_category'
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenant.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default='')
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey('user.id'))
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey('user.id'))
    revision: Mapped[int] = mapped_column(default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint('tenant_id', 'name', name='uq_knowledge_category_name'),)


class Document(Base):
    __tablename__ = "document"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey('channel_account.id'), nullable=True, index=True)
    platform_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey('knowledge_category.id'), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(default=1, server_default='1')
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('user.id'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.current_timestamp(), onupdate=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", "title"),)


class DocumentVersion(Base):
    __tablename__ = "document_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    original_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_revert_on_expiry: Mapped[bool] = mapped_column(default=False, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default='', server_default=text("('')"))
    chunk_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint("document_id", "version"),)


class Chunk(Base):
    __tablename__ = "chunk"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey('channel_account.id'), nullable=True, index=True)
    platform_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_version.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding_space: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
