from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import role_required
from app.models import QuestionTrace, QuestionTraceNode, QuestionTracePayload, User, AuditLog
from app.services.tracing import payload_content

router = APIRouter(tags=['question-traces'])
reader = role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER')


def node_view(row):
    return {c.name: (getattr(row, c.name).replace(tzinfo=timezone.utc).isoformat() if isinstance(getattr(row, c.name), datetime)
                    else getattr(row, c.name)) for c in row.__table__.columns}


def trace_view(row, nodes, user=None):
    value = node_view(row)
    counts = {}
    for n in nodes:
        if n.location == 'remote_ai':
            counts[n.node_type] = counts.get(n.node_type, 0) + 1
    value.update(username=user.username if user else '', customer_name=user.display_name if user else '',
        ai_calls=counts, ai_used=bool(counts), nodes=[{'id': n.id, 'name': n.name, 'type': n.node_type,
        'location': n.location, 'status': n.status} for n in nodes])
    return value


@router.get('/api/admin/question-traces')
def traces(keyword: str = '', conversation_id: int | None = None, account_id: int | None = None,
           route: str = '', outcome: str = '',
           ai_used: bool | None = None, used_context: bool | None = None, fallback: bool | None = None,
           handoff: bool | None = None, node_type: str = '',
           started_from: datetime | None = None, started_to: datetime | None = None,
           page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
           user: User = Depends(reader), db: Session = Depends(get_db)):
    q = select(QuestionTrace).join(User, QuestionTrace.user_id == User.id).where(
        QuestionTrace.tenant_id == user.tenant_id, QuestionTrace.kind != 'diagnostic')
    if account_id is not None:
        q = q.where(QuestionTrace.account_id == account_id)
    if keyword.strip():
        term = keyword.strip()
        q = q.where(or_(QuestionTrace.query.contains(term, autoescape=True), QuestionTrace.trace_id.contains(term, autoescape=True),
                        User.username.contains(term, autoescape=True), User.display_name.contains(term, autoescape=True)))
    if conversation_id is not None:
        q = q.where(QuestionTrace.conversation_id == conversation_id)
    if route:
        q = q.where(QuestionTrace.route == route)
    if outcome:
        q = q.where(QuestionTrace.outcome == outcome)
    for field, value in [('used_context',used_context), ('fallback',fallback), ('handoff',handoff)]:
        if value is not None:
            q = q.where(getattr(QuestionTrace, field) == value)
    external = select(QuestionTraceNode.id).where(QuestionTraceNode.trace_id == QuestionTrace.trace_id,
            QuestionTraceNode.location == 'remote_ai').exists()
    if ai_used is not None:
        q = q.where(external if ai_used else ~external)
    if node_type:
        q = q.where(select(QuestionTraceNode.id).where(QuestionTraceNode.trace_id == QuestionTrace.trace_id,
            QuestionTraceNode.node_type == node_type).exists())
    for bound, lower in [(started_from, True), (started_to, False)]:
        if bound:
            bound = bound.astimezone(timezone.utc).replace(tzinfo=None) if bound.tzinfo else bound
            q = q.where(QuestionTrace.started_at >= bound if lower else QuestionTrace.started_at <= bound)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(QuestionTrace.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    ids = [r.trace_id for r in rows]
    nodes = db.scalars(select(QuestionTraceNode).where(QuestionTraceNode.trace_id.in_(ids)).order_by(QuestionTraceNode.sequence)).all() if ids else []
    by_trace = {}
    for n in nodes:
        by_trace.setdefault(n.trace_id, []).append(n)
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_([r.user_id for r in rows]))).all()} if rows else {}
    return {'items': [trace_view(r, by_trace.get(r.trace_id, []), users.get(r.user_id)) for r in rows],
            'total': total, 'page': page, 'page_size': page_size}


def checked(db, trace_id, user):
    row = db.scalar(select(QuestionTrace).where(QuestionTrace.trace_id == trace_id, QuestionTrace.tenant_id == user.tenant_id))
    if not row:
        raise HTTPException(404, 'Trace not found')
    return row


@router.get('/api/admin/question-traces/{trace_id}')
def detail(trace_id: str, user: User = Depends(reader), db: Session = Depends(get_db)):
    row = checked(db, trace_id, user)
    nodes = db.scalars(select(QuestionTraceNode).where(QuestionTraceNode.trace_id == trace_id).order_by(QuestionTraceNode.sequence)).all()
    result = trace_view(row, nodes, db.get(User, row.user_id))
    payloads = db.scalars(select(QuestionTracePayload).where(QuestionTracePayload.node_id.in_([n.id for n in nodes]))).all() if nodes else []
    result['nodes'] = [node_view(n) | {'payloads': [{'id': p.id, 'kind': p.kind, 'byte_size': p.byte_size,
        'sha256': p.sha256, 'status': p.status, 'storage': 'file' if p.file_key else 'mysql'} for p in payloads if p.node_id == n.id]} for n in nodes]
    result['related'] = [{'trace_id': r.trace_id, 'kind': r.kind, 'outcome': r.outcome} for r in db.scalars(select(QuestionTrace).where(
        QuestionTrace.parent_trace_id == trace_id, QuestionTrace.tenant_id == user.tenant_id).order_by(QuestionTrace.id)).all()]
    result['audit'] = [{'id': a.id, 'action': a.action, 'actor': a.actor, 'detail': a.detail,
        'created_at': a.created_at.isoformat()} for a in db.scalars(select(AuditLog).where(
        AuditLog.trace_id == trace_id, AuditLog.tenant_id == user.tenant_id).order_by(AuditLog.id)).all()]
    return result


@router.get('/api/admin/question-traces/{trace_id}/payloads/{payload_id}')
def payload(trace_id: str, payload_id: int, user: User = Depends(reader), db: Session = Depends(get_db)):
    checked(db, trace_id, user)
    row = db.scalar(select(QuestionTracePayload).join(QuestionTraceNode, QuestionTracePayload.node_id == QuestionTraceNode.id)
        .where(QuestionTracePayload.id == payload_id, QuestionTraceNode.trace_id == trace_id))
    if not row:
        raise HTTPException(404, 'Payload not found')
    try:
        return {'id': row.id, 'kind': row.kind, 'content': payload_content(row)}
    except (OSError, ValueError, EOFError):
        raise HTTPException(410, 'Payload missing or invalid; snapshot unavailable')
