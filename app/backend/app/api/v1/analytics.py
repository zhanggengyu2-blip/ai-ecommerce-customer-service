from fastapi import APIRouter
from fastapi import Depends, HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased
from app.core.database import get_db
from app.models import User, Conversation, Message, Feedback, AuditLog, QuestionTrace, QuestionTraceNode
from app.core.security import role_required

router = APIRouter(tags=["analytics"])


@router.get('/api/admin/feedback')
def feedback_list(account_id: int | None = None, user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER')), db: Session = Depends(get_db)):
    rows = db.execute(select(Feedback, Message).join(Message, Feedback.message_id == Message.id)
                      .join(Conversation, Message.conversation_id == Conversation.id)
                      .where(Conversation.tenant_id == user.tenant_id,
                             *([Conversation.account_id == account_id] if account_id else []))
                      .order_by(Feedback.id.desc()).limit(200)).all()
    return [{'id': f.id, 'rating': f.rating, 'reason': f.reason, 'conversation_id': m.conversation_id, 'answer': m.content} for f, m in rows]


@router.get('/api/admin/popular-questions')
def popular_questions(account_id: int | None = None, user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER')), db: Session = Depends(get_db)):
    rows = db.execute(select(QuestionTrace.query, func.count(QuestionTrace.id).label('count'))
                      .where(QuestionTrace.tenant_id == user.tenant_id, QuestionTrace.kind == 'question',
                             *([QuestionTrace.account_id == account_id] if account_id else [])).group_by(QuestionTrace.query)
                      .order_by(func.count(QuestionTrace.id).desc()).limit(50)).all()
    return [{'query': query, 'count': count} for query, count in rows]


@router.get('/api/admin/unresolved-questions')
def unresolved_questions(keyword: str = '', account_id: int | None = None,
                         page: int = 1, page_size: int = 20,
                         user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER')),
                         db: Session = Depends(get_db)):
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(422, 'Invalid pagination')
    later_question = aliased(QuestionTrace)
    latest_question = ~select(later_question.id).where(
        later_question.conversation_id == QuestionTrace.conversation_id,
        later_question.kind == 'question', later_question.id > QuestionTrace.id).exists()
    negative_feedback = select(Feedback.id).where(
        Feedback.message_id == QuestionTrace.reply_message_id, Feedback.rating < 0).exists()
    needs_followup = or_(
        negative_feedback,
        and_(latest_question, or_(
            and_(QuestionTrace.outcome == 'CLARIFY', Conversation.status == 'AI_ACTIVE'),
            and_(QuestionTrace.outcome.in_(['HANDOFF', 'ERROR', 'UNCERTAIN']),
                 Conversation.status == 'WAITING_USER'))))
    q = select(QuestionTrace, Conversation.status, User.display_name, User.username,
               negative_feedback.label('negative_feedback')).join(
        Conversation, Conversation.id == QuestionTrace.conversation_id).join(
        User, User.id == QuestionTrace.user_id).where(
        QuestionTrace.tenant_id == user.tenant_id, QuestionTrace.kind == 'question', needs_followup)
    if account_id is not None:
        q = q.where(QuestionTrace.account_id == account_id)
    if keyword.strip():
        term = keyword.strip()
        q = q.where(or_(QuestionTrace.query.contains(term, autoescape=True),
                        User.username.contains(term, autoescape=True),
                        User.display_name.contains(term, autoescape=True)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(QuestionTrace.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for trace, conversation_status, display_name, username, negative in rows:
        reason = ('客户差评（待核实）' if negative else '待客户补充信息' if trace.outcome == 'CLARIFY'
                  else '等待人工接管' if trace.outcome in ('HANDOFF', 'HUMAN_PENDING')
                  else '处理异常待人工接管')
        items.append({'trace_id': trace.trace_id, 'conversation_id': trace.conversation_id,
                      'customer_name': display_name or username, 'query': trace.query,
                      'final_reply': trace.final_reply, 'started_at': trace.started_at,
                      'reason': reason, 'conversation_status': conversation_status})
    return {'items': items, 'total': total, 'page': page, 'page_size': page_size}


@router.get("/api/admin/dashboard")
def dashboard(account_id: int | None = None, user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER", "VIEWER")), db: Session = Depends(get_db)):
    conv_scope = [Conversation.account_id == account_id] if account_id else []
    trace_scope = [QuestionTrace.account_id == account_id] if account_id else []
    total = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.tenant_id == user.tenant_id, *conv_scope))
    handoff = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.tenant_id == user.tenant_id,
                                                                          Conversation.handoff_reason.is_not(None), *conv_scope))
    negatives = db.scalar(select(func.count()).select_from(Feedback).join(Message, Feedback.message_id == Message.id)
                          .join(Conversation, Message.conversation_id == Conversation.id)
                          .where(Conversation.tenant_id == user.tenant_id, Feedback.rating < 0, *conv_scope))
    rated = db.scalar(select(func.count()).select_from(Feedback).join(Message, Feedback.message_id == Message.id)
                      .join(Conversation, Message.conversation_id == Conversation.id)
                      .where(Conversation.tenant_id == user.tenant_id, *conv_scope)) or 0
    message_counts = (select(Message.conversation_id.label('conversation_id'),
                             func.sum(case((Message.sender_type == 'CUSTOMER', 1), else_=0)).label('customer_turns'),
                             func.sum(case((Message.sender_type == 'AI', 1), else_=0)).label('ai_replies'))
                      .group_by(Message.conversation_id).subquery())
    engaged, customer_turns, first_question_resolved, closed_eligible = db.execute(
        select(func.count(), func.coalesce(func.sum(message_counts.c.customer_turns), 0),
               func.coalesce(func.sum(case((
                   (Conversation.closed_at.is_not(None)) &
                   (Conversation.handoff_reason.is_(None)) &
                   (message_counts.c.customer_turns == 1) &
                   (message_counts.c.ai_replies > 0), 1), else_=0)), 0),
               func.coalesce(func.sum(case((Conversation.closed_at.is_not(None), 1), else_=0)), 0))
        .select_from(Conversation).join(message_counts, message_counts.c.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == user.tenant_id, message_counts.c.customer_turns > 0, *conv_scope)).one()
    engaged_handoffs = db.scalar(select(func.count()).select_from(Conversation)
        .join(message_counts, message_counts.c.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == user.tenant_id, Conversation.handoff_reason.is_not(None),
               message_counts.c.customer_turns > 0, *conv_scope)) or 0
    failures = db.scalar(select(func.count()).select_from(QuestionTrace)
                         .where(QuestionTrace.tenant_id == user.tenant_id, QuestionTrace.status == "FAILED", *trace_scope))
    tools = select(func.count()).select_from(QuestionTraceNode).join(QuestionTrace, QuestionTraceNode.trace_id == QuestionTrace.trace_id).where(
        QuestionTrace.tenant_id == user.tenant_id, QuestionTraceNode.node_type == 'business.tool', *trace_scope)
    tool_total = db.scalar(tools)
    tool_ok = db.scalar(tools.where(QuestionTraceNode.status == 'SUCCESS'))
    knowledge_misses = db.scalar(select(func.count()).select_from(Conversation)
                                 .where(Conversation.tenant_id == user.tenant_id,
                                        Conversation.handoff_reason.like("Knowledge%"), *conv_scope))
    return {"conversations": total, "engaged_conversations": engaged,
            "handoffs": handoff, "handoff_rate": round(engaged_handoffs / engaged, 3) if engaged else None,
            "first_question_resolution_rate": round(first_question_resolved / closed_eligible, 3) if closed_eligible else None,
            "negative_feedback_rate": round(negatives / rated, 3) if rated else None,
            "average_customer_turns": round(customer_turns / engaged, 2) if engaged else None,
            "closed_conversations_with_questions": closed_eligible, "rated_answers": rated,
            "negative_feedback": negatives, "ai_failures": failures, "knowledge_misses": knowledge_misses,
            "tool_success_rate": round(tool_ok / tool_total, 3) if tool_total else None}


@router.get("/api/admin/audit")
def audit(user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER", "VIEWER")), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
                      .order_by(AuditLog.id.desc()).limit(100)).all()
    return [{"id": a.id, "actor": a.actor, "action": a.action, "target": a.target,
             "detail": a.detail, "trace_id": a.trace_id, "node_id": a.node_id, "created_at": a.created_at.isoformat()} for a in rows]


