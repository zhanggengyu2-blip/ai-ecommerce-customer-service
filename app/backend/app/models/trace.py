from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Integer, DateTime, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, utcnow


class QuestionTrace(Base):
    __tablename__ = 'question_trace'
    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True)
    tenant_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'), default=1, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey('conversation.id'), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('user.id'), nullable=True, index=True)
    question_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pending_action_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default='question')
    query: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(String(32), default='')
    intent: Mapped[str] = mapped_column(String(32), default='')
    model: Mapped[str] = mapped_column(String(128), default='')
    status: Mapped[str] = mapped_column(String(24), default='RUNNING', index=True)
    outcome: Mapped[str] = mapped_column(String(32), default='PROCESSING', index=True)
    used_context: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    final_reply: Mapped[str] = mapped_column(Text, default='')
    composition: Mapped[list] = mapped_column(JSON, default=list)
    context_sources: Mapped[dict] = mapped_column(JSON, default=dict)
    config_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    capture_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    capture_errors: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class QuestionTraceNode(Base):
    __tablename__ = 'question_trace_node'
    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey('question_trace.trace_id'), index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parent_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    sequence: Mapped[int] = mapped_column(Integer)
    node_type: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128), default='')
    status: Mapped[str] = mapped_column(String(24), default='RUNNING', index=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class QuestionTracePayload(Base):
    __tablename__ = 'question_trace_payload'
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey('question_trace_node.id'), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default='AVAILABLE')
    __table_args__ = (UniqueConstraint('node_id', 'kind'),)
