from fastapi import APIRouter
import json
import logging
import uuid
import queue
import threading
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, get_db
from app.models import User, Conversation, Message, PendingAction, Feedback, AuditLog, QuestionTrace, utcnow
from app.core.security import customer_required
from app.providers.business import business_tool
from app.providers.ai import ProviderError
from app.services.orchestrator import answer
from app.core.rate_limit import check_rate_limit
from app.services.conversations import message_view, conversation_view, checked_conversation
from app.schemas.conversation import ConversationCreate, MessageRequest, FeedbackRequest, ConfirmRequest
from app.services.accounts import require_customer_account, customer_account_ids
from app.services.tracing import trace_scope, active_trace, event, mark

router = APIRouter(tags=["customer"])


def _record_non_ai(db, conversation, customer, message):
    parent = db.scalar(select(QuestionTrace.trace_id).where(QuestionTrace.conversation_id == conversation.id,
        QuestionTrace.outcome == 'HANDOFF').order_by(QuestionTrace.id.desc()).limit(1))
    with trace_scope(db, conversation, customer, message.content, question_message_id=message.id, parent_trace_id=parent) as recorder:
        event('local.human_delivery', '消息交给人工会话', input={'message_id': message.id,
            'content': message.content}, output={'conversation_status': conversation.status,
            'agent_id': conversation.current_agent_id, 'ai_called': False})
        recorder.finish(status='SUCCESS', route='human', intent='human',
            outcome='HUMAN_ACTIVE' if conversation.current_agent_id else 'HUMAN_PENDING',
            handoff=True, handoff_reason=conversation.handoff_reason)
        if db.get_bind().dialect.name == 'sqlite':
            db.commit()


def checked_customer_conversation(db, conversation_id, customer):
    c = checked_conversation(db, conversation_id, customer.tenant_id)
    require_customer_account(db, c.account_id, customer)
    return c


@router.post("/api/customer/conversations")
def create_conversation(body: ConversationCreate = ConversationCreate(), customer: User = Depends(customer_required), db: Session = Depends(get_db)):
    require_customer_account(db, body.account_id, customer)
    c = Conversation(tenant_id=customer.tenant_id, user_id=customer.id, account_id=body.account_id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return conversation_view(c)


@router.get("/api/customer/conversations")
def customer_conversations(customer: User = Depends(customer_required), db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).where(Conversation.user_id == customer.id,
                                                   Conversation.tenant_id == customer.tenant_id,
                                                   Conversation.account_id.in_(customer_account_ids(db, customer)))
                      .order_by(Conversation.id.desc()).limit(50)).all()
    return [conversation_view(c) for c in rows]


@router.get("/api/customer/conversations/{conversation_id}/messages")
def customer_messages(conversation_id: int, after_id: int = 0, customer: User = Depends(customer_required),
                      db: Session = Depends(get_db)):
    c = checked_customer_conversation(db, conversation_id, customer)
    if c.user_id != customer.id:
        raise HTTPException(403, "Forbidden")
    return [message_view(m) for m in db.scalars(select(Message).where(Message.conversation_id == c.id,
                                     Message.id > after_id).order_by(Message.id).limit(200)).all()]


@router.post("/api/customer/conversations/{conversation_id}/messages")
def customer_send(conversation_id: int, body: MessageRequest, customer: User = Depends(customer_required),
                  db: Session = Depends(get_db)):
    check_rate_limit(f"chat:{customer.id}", 30, 60)
    c = checked_customer_conversation(db, conversation_id, customer)
    if c.user_id != customer.id:
        raise HTTPException(403, "Forbidden")
    if c.status == "CLOSED":
        raise HTTPException(409, "Conversation closed")
    m = Message(conversation_id=c.id, sender_type="CUSTOMER", content=body.content.strip())
    c.last_message_at = utcnow()
    db.add(m)
    db.commit()
    db.refresh(m)
    reply = answer(db, c, customer, m.content) if c.status == "AI_ACTIVE" else None
    if reply is None:
        _record_non_ai(db, c, customer, m)
    return {"message": message_view(m), "reply": message_view(reply) if reply else None,
            "conversation": conversation_view(c)}


@router.post("/api/customer/conversations/{conversation_id}/messages/stream")
def customer_send_stream(conversation_id: int, body: MessageRequest, customer: User = Depends(customer_required)):
    check_rate_limit(f"chat:{customer.id}", 30, 60)
    events: queue.Queue[dict | None] = queue.Queue()
    user_id, tenant_id, content = customer.id, customer.tenant_id, body.content.strip()

    def run():
        try:
            with SessionLocal() as db:
                live_customer = db.get(User, user_id)
                c = checked_customer_conversation(db, conversation_id, live_customer)
                if not live_customer or c.user_id != user_id or c.status == "CLOSED":
                    events.put({"type": "error", "detail": "Conversation unavailable"})
                    return
                m = Message(conversation_id=c.id, sender_type="CUSTOMER", content=content)
                c.last_message_at = utcnow()
                db.add(m)
                db.commit()
                db.refresh(m)
                events.put({"type": "message", "message": message_view(m)})
                reply = answer(db, c, live_customer, content,
                               on_delta=lambda delta: events.put({"type": "delta", "content": delta})) if c.status == "AI_ACTIVE" else None
                if reply is None:
                    _record_non_ai(db, c, live_customer, m)
                events.put({"type": "done", "reply": message_view(reply) if reply else None,
                            "conversation": conversation_view(c)})
        except Exception:
            logging.exception("Streaming customer message failed")
            events.put({"type": "error", "detail": "Message processing failed; reload conversation history"})
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            event = events.get()
            if event is None:
                break
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/customer/conversations/{conversation_id}/handoff")
def customer_handoff(conversation_id: int, customer: User = Depends(customer_required), db: Session = Depends(get_db)):
    c = checked_customer_conversation(db, conversation_id, customer)
    if c.user_id != customer.id:
        raise HTTPException(403, "Forbidden")
    if c.status == "WAITING_USER":
        return conversation_view(c)
    if c.status != "AI_ACTIVE":
        raise HTTPException(409, "Conversation already handled by an agent or closed")
    c.status, c.handoff_reason = "WAITING_USER", "User requested human"
    audit = AuditLog(tenant_id=c.tenant_id, actor=f"customer:{customer.id}", action="handoff",
                    target=f"conversation:{c.id}", detail={})
    db.add(audit)
    db.commit()
    parent = db.scalar(select(QuestionTrace.trace_id).where(QuestionTrace.conversation_id == c.id)
        .order_by(QuestionTrace.id.desc()).limit(1))
    with trace_scope(db, c, customer, '客户点击转人工', kind='handoff', parent_trace_id=parent) as recorder:
        event('local.handoff', '客户主动转人工', input={'user_id': customer.id},
              output={'conversation_status': c.status, 'agent_id': None})
        recorder.finish(status='SUCCESS', outcome='HANDOFF', route='human', intent='human',
                        handoff=True, handoff_reason=c.handoff_reason)
        audit.trace_id = recorder.trace_id
        db.commit()
    return conversation_view(c)


@router.post("/api/customer/messages/{message_id}/feedback")
def submit_feedback(message_id: int, body: FeedbackRequest, customer: User = Depends(customer_required),
                    db: Session = Depends(get_db)):
    m = db.get(Message, message_id)
    if not m or m.sender_type != "AI":
        raise HTTPException(404, "AI message not found")
    c = checked_customer_conversation(db, m.conversation_id, customer)
    if c.user_id != customer.id:
        raise HTTPException(403, "Forbidden")
    row = db.scalar(select(Feedback).where(Feedback.message_id == m.id, Feedback.user_id == customer.id))
    if not row:
        row = Feedback(message_id=m.id, user_id=customer.id)
        db.add(row)
    row.rating, row.reason = body.rating, body.reason
    db.commit()
    return {"ok": True}


@router.get("/api/customer/conversations/{conversation_id}/actions")
def pending_actions(conversation_id: int, customer: User = Depends(customer_required), db: Session = Depends(get_db)):
    c = checked_customer_conversation(db, conversation_id, customer)
    if c.user_id != customer.id:
        raise HTTPException(403, "Forbidden")
    return [{"id": a.id, "action": a.action, "order_id": a.order_id, "expires_at": a.expires_at.isoformat()}
            for a in db.scalars(select(PendingAction).where(PendingAction.conversation_id == c.id,
                                                             PendingAction.user_id == customer.id,
                                                             PendingAction.status == "PENDING")).all()]


@router.post("/api/customer/actions/{action_id}/confirm")
def confirm_action(action_id: int, body: ConfirmRequest, customer: User = Depends(customer_required),
                   db: Session = Depends(get_db)):
    action = db.get(PendingAction, action_id)
    if not action or action.user_id != customer.id:
        raise HTTPException(404, 'Action not found')
    c = checked_customer_conversation(db, action.conversation_id, customer)
    with trace_scope(db, c, customer, f"确认动作 {action.action}：{action.order_id}", kind='confirmation',
                     parent_trace_id=action.origin_trace_id, pending_action_id=action.id) as recorder:
        event('local.confirm', '接收客户确认', input={'action_id': action_id, 'confirm': body.confirm,
            'user_id': customer.id, 'origin_trace_id': action.origin_trace_id, 'origin_node_id': action.origin_node_id},
            output={'previous_status': action.status, 'expires_at': action.expires_at})
        result = _confirm_action(action_id, body, customer, db)
        event('local.action_result', '确认操作结果', output=result)
        recorder.finish(status='SUCCESS' if result['status'] != 'UNCERTAIN' else 'FAILED',
                        outcome=result['status'], route='business', intent='business_action')
        if db.get_bind().dialect.name == 'sqlite':
            db.commit()
        return result


def _confirm_action(action_id: int, body: ConfirmRequest, customer: User, db: Session):
    action = db.get(PendingAction, action_id)
    if not action or action.user_id != customer.id:
        raise HTTPException(404, "Action not found")
    c = checked_customer_conversation(db, action.conversation_id, customer)
    event('local.action_guard', '核验待确认动作状态与归属', input={'action_id': action.id, 'user_id': customer.id,
        'status': action.status, 'conversation_status': c.status, 'expires_at': action.expires_at,
        'amount_snapshot': action.amount_snapshot, 'confirm': body.confirm}, output={
        'expired': action.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc),
        'same_user': action.user_id == customer.id, 'already_done': action.status == 'DONE'})
    if c.status == "CLOSED":
        raise HTTPException(409, "Conversation closed")
    if action.status == "DONE":
        return {"status": "DONE", "result": action.result}
    if action.status != "PENDING" or action.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(409, "Action no longer available")
    if not body.confirm:
        action.status = "CANCELLED"
        db.add(AuditLog(tenant_id=c.tenant_id, actor=f'customer:{customer.id}', action='pending_action_cancel',
            target=f'pending_action:{action.id}', trace_id=active_trace.get().trace_id, detail={'status':'CANCELLED'}))
        db.commit()
        return {"status": "CANCELLED"}
    result = db.execute(update(PendingAction).where(PendingAction.id == action.id, PendingAction.status == "PENDING")
                        .values(status="EXECUTING"))
    db.commit()
    event('local.action_claim', '原子认领待确认动作', input={'action_id': action.id, 'expected_status': 'PENDING'},
          output={'claimed': result.rowcount == 1, 'new_status': 'EXECUTING' if result.rowcount == 1 else None})
    if result.rowcount != 1:
        raise HTTPException(409, "Action already being processed")
    trace_id = active_trace.get().trace_id
    try:
        # Revalidate against the business system immediately before the write.
        order = business_tool(db, trace_id, c.id, customer.id, "get_order", action.order_id)
        event('local.action_revalidate', '再次校验订单是否允许操作', input={'action': action.action, 'order': order},
            output={'requires_human_approval': order.get('data', {}).get('requires_human_approval'),
                    'cancellable': order.get('data', {}).get('cancellable')})
        if order.get("data", {}).get("requires_human_approval") or (action.action == "cancel_order" and order.get("data", {}).get("cancellable") is not True):
            action.status = "REJECTED"
            db.add(AuditLog(tenant_id=c.tenant_id, actor=f"customer:{customer.id}", action=action.action,
                            target=f"order:{action.order_id}", trace_id=trace_id, detail={"status": "REJECTED", "trace_id": trace_id}))
            db.commit()
            raise HTTPException(409, "Action no longer permitted")
        if action.action == "apply_refund":
            eligibility = business_tool(db, trace_id, c.id, customer.id,
                                        "get_refund_eligibility", action.order_id)
            data = eligibility.get("data", {})
            event('local.refund_revalidate', '再次校验退款资格与金额快照', input={'eligibility': data,
                'amount_snapshot': action.amount_snapshot}, output={'eligible': data.get('eligible'),
                'requires_human_approval': data.get('requires_human_approval'),
                'amount_unchanged': str(data.get('refundable_amount')) == action.amount_snapshot})
            if (not data.get("eligible") or data.get("requires_human_approval") or
                str(data.get("refundable_amount")) != action.amount_snapshot):
                action.status = "REJECTED"
                db.add(AuditLog(tenant_id=c.tenant_id, actor=f"customer:{customer.id}", action=action.action,
                                target=f"order:{action.order_id}", trace_id=trace_id, detail={"status": "REJECTED", "trace_id": trace_id}))
                db.commit()
                raise HTTPException(409, "Refund no longer eligible")
        output = business_tool(db, trace_id, c.id, customer.id, action.action,
                               action.order_id, action.idempotency_key)
        action.status, action.result = "DONE", {"code": output.get("code"), "request_id": output.get("request_id")}
        db.add(Message(conversation_id=c.id, sender_type="SYSTEM", content=f"{action.action} 已提交，业务请求号：{output.get('request_id', '')}"))
    except ProviderError as exc:
        action.status = "UNCERTAIN"  # Never automatically repeat a possibly accepted write.
        action.result = {"error": str(exc)[:255]}
    db.add(AuditLog(tenant_id=c.tenant_id, actor=f"customer:{customer.id}", action=action.action,
                    target=f"order:{action.order_id}", trace_id=trace_id, detail={"status": action.status, "trace_id": trace_id,
                    "idempotency_key": action.idempotency_key, "request_id": (action.result or {}).get("request_id")}))
    db.commit()
    return {"status": action.status, "result": action.result}
