from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import Conversation, Message, ChannelAccount


def message_view(m: Message):
    return {"id": m.id, "conversation_id": m.conversation_id, "sender_type": m.sender_type,
            "content": m.content, "citations": m.citations, "created_at": m.created_at.isoformat()}


def conversation_view(c: Conversation):
    account = c.account_id
    return {"id": c.id, "status": c.status, "user_id": c.user_id,
            "account_id": account,
            "current_agent_id": c.current_agent_id, "handoff_reason": c.handoff_reason,
            "last_message_at": c.last_message_at.isoformat()}


def checked_conversation(db: Session, conversation_id: int, tenant_id: int) -> Conversation:
    c = db.get(Conversation, conversation_id)
    if not c or c.tenant_id != tenant_id:
        raise HTTPException(404, "Conversation not found")
    return c
