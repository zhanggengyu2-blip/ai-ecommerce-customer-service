from fastapi import APIRouter
from fastapi import Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User, Conversation, Message, AuditLog, QuestionTrace, ChannelAccount, utcnow
from app.core.security import role_required
from app.services.conversations import message_view, conversation_view, checked_conversation
from app.services.accounts import require_account, visible_account_ids, account_view
from app.schemas.conversation import MessageRequest

router = APIRouter(tags=["support"])


@router.get("/api/agent/conversations")
def agent_conversations(status: str | None = None, user: User = Depends(role_required("ADMIN", "CUSTOMER_SERVICE")), db: Session = Depends(get_db)):
    q = select(Conversation).where(Conversation.tenant_id == user.tenant_id,
                                   Conversation.account_id.in_(visible_account_ids(db, user)))
    if status:
        q = q.where(Conversation.status == status)
    rows = db.scalars(q.order_by(Conversation.last_message_at.desc()).limit(100)).all()
    return [conversation_view(c) | {'account_name': db.get(ChannelAccount, c.account_id).name,
            'platform_code': db.get(ChannelAccount, c.account_id).platform_code} for c in rows]


@router.get("/api/agent/conversations/{conversation_id}/messages")
def agent_messages(conversation_id: int, after_id: int = 0, user: User = Depends(role_required("ADMIN", "CUSTOMER_SERVICE")), db: Session = Depends(get_db)):
    c = checked_conversation(db, conversation_id, user.tenant_id)
    require_account(db, c.account_id, user)
    return [message_view(m) for m in db.scalars(select(Message).where(Message.conversation_id == c.id,
                               Message.id > after_id).order_by(Message.id).limit(200)).all()]


@router.post("/api/agent/conversations/{conversation_id}/claim")
def claim(conversation_id: int, user: User = Depends(role_required("ADMIN", "CUSTOMER_SERVICE")), db: Session = Depends(get_db)):
    c = checked_conversation(db, conversation_id, user.tenant_id)
    require_account(db, c.account_id, user)
    if c.status == "HUMAN_ACTIVE" and c.current_agent_id == user.id:
        return conversation_view(c)
    if c.status != "WAITING_USER" or c.current_agent_id is not None:
        raise HTTPException(409, "Conversation unavailable")
    result = db.execute(update(Conversation).where(Conversation.id == c.id,
                                                   Conversation.status == "WAITING_USER",
                                                   Conversation.current_agent_id.is_(None))
                        .values(status="HUMAN_ACTIVE", current_agent_id=user.id))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Conversation already claimed")
    origin = db.scalar(select(QuestionTrace.trace_id).where(QuestionTrace.conversation_id == c.id,
        QuestionTrace.outcome == 'HANDOFF').order_by(QuestionTrace.id.desc()).limit(1))
    db.add(AuditLog(tenant_id=c.tenant_id, actor=f"staff:{user.id}", action="claim",
                    target=f"conversation:{c.id}", detail={'agent_id': user.id}, trace_id=origin))
    db.commit()
    db.refresh(c)
    return conversation_view(c)


@router.post("/api/agent/conversations/{conversation_id}/messages")
def agent_send(conversation_id: int, body: MessageRequest, user: User = Depends(role_required("ADMIN", "CUSTOMER_SERVICE")), db: Session = Depends(get_db)):
    c = checked_conversation(db, conversation_id, user.tenant_id)
    require_account(db, c.account_id, user)
    if c.status != "HUMAN_ACTIVE" or c.current_agent_id != user.id:
        raise HTTPException(403, "Claim conversation first")
    m = Message(conversation_id=c.id, sender_type="AGENT", content=body.content.strip())
    c.last_message_at = utcnow()
    db.add(m)
    db.commit()
    db.refresh(m)
    return message_view(m)


@router.post("/api/agent/conversations/{conversation_id}/close")
def close(conversation_id: int, user: User = Depends(role_required("ADMIN", "CUSTOMER_SERVICE")), db: Session = Depends(get_db)):
    c = checked_conversation(db, conversation_id, user.tenant_id)
    require_account(db, c.account_id, user)
    if c.current_agent_id != user.id:
        raise HTTPException(403, "Assigned agent required")
    c.status, c.closed_at = "CLOSED", utcnow()
    db.commit()
    return conversation_view(c)


@router.get('/api/admin/conversations')
def admin_conversations(account_id: int | None = None,
                        user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER', 'CUSTOMER_SERVICE')),
                        db: Session = Depends(get_db)):
    rows = db.execute(select(Conversation, User.display_name, User.username, ChannelAccount.name, ChannelAccount.platform_code)
                      .join(User, Conversation.user_id == User.id)
                      .join(ChannelAccount, Conversation.account_id == ChannelAccount.id)
                      .where(Conversation.tenant_id == user.tenant_id,
                             Conversation.account_id.in_(visible_account_ids(db, user)),
                             *([Conversation.account_id == account_id] if account_id else []))
                      .order_by(Conversation.last_message_at.desc()).limit(200)).all()
    return [conversation_view(c) | {'customer_name': name, 'customer_username': username,
                                   'account_name': account_name, 'platform_code': platform,
                                   'can_reply': c.status == 'HUMAN_ACTIVE' and c.current_agent_id == user.id}
            for c, name, username, account_name, platform in rows]


@router.get('/api/admin/conversations/{conversation_id}/messages')
def admin_messages(conversation_id: int, user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER', 'CUSTOMER_SERVICE')), db: Session = Depends(get_db)):
    c = checked_conversation(db, conversation_id, user.tenant_id)
    require_account(db, c.account_id, user)
    return [message_view(m) for m in db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.id).limit(200)).all()]
