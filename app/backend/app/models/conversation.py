from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Integer, DateTime, JSON, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, utcnow


class ChatThread(Base):
    __tablename__ = 'chat_thread'
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenant.id'), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'))
    customer_id: Mapped[int] = mapped_column(ForeignKey('user.id'))
    active_conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint('tenant_id', 'account_id', 'customer_id', name='uq_thread_customer'),)


class Conversation(Base):
    __tablename__ = "conversation"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'), default=1, index=True)
    thread_id: Mapped[int | None] = mapped_column(ForeignKey('chat_thread.id'), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(default=1, server_default='1')
    reception_epoch: Mapped[int] = mapped_column(default=1, server_default='1')
    ever_handoff_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    ever_human_claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    last_customer_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handoff_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consultation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_status: Mapped[str] = mapped_column(String(16), default='NONE', server_default='NONE')
    external_conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="AI_ACTIVE")
    current_agent_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    handoff_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.id")


class Message(Base):
    __tablename__ = "message"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation.id"), index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey('tenant.id'), nullable=True, index=True)
    thread_id: Mapped[int | None] = mapped_column(ForeignKey('chat_thread.id'), nullable=True, index=True)
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey('user.id'), nullable=True)
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(32), default="text")
    external_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    delivery_status: Mapped[str] = mapped_column(String(24), default='LOCAL')
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    __table_args__ = (UniqueConstraint('tenant_id', 'thread_id', 'sender_user_id', 'client_message_id', name='uq_message_client'),
                      UniqueConstraint('tenant_id', 'external_message_id', name='uq_message_external'))


class ReceptionRequest(Base):
    __tablename__ = 'reception_request'
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenant.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('user.id'))
    scope: Mapped[str] = mapped_column(String(96))
    request_key: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('tenant_id', 'actor_id', 'scope', 'request_key', name='uq_reception_request'),)


class PendingAction(Base):
    __tablename__ = "pending_action"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    action: Mapped[str] = mapped_column(String(32))
    order_id: Mapped[str] = mapped_column(String(128))
    amount_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    origin_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    origin_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    rating: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32), default="")
    __table_args__ = (UniqueConstraint("message_id", "user_id"),)
