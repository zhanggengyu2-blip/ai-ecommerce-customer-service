"""Durable reception transitions; all mutations use user -> thread -> conversation locks."""
import hashlib
import json
from contextlib import contextmanager
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.models import ChatThread, Conversation, Message, ReceptionRequest, AuditLog, utcnow
from .security import fail, validate, store_for
from .views import conversation_view, message_view


@contextmanager
def writing(db, identity=None):
    try:
        user = validate(db, identity, locked=True) if identity else None
        if identity:
            from .model_runtime import lock_tenant
            lock_tenant(db, identity.tenant_id)
        yield user
        db.commit()
    except (IntegrityError, OperationalError):
        db.rollback()
        fail(409, 'WRITE_CONFLICT', '记录已变化或正在被处理，请刷新后重试')
    except Exception:
        db.rollback()
        raise


def thread_for(db, identity, ident, *, locked=False):
    query = select(ChatThread).where(ChatThread.id == ident, ChatThread.tenant_id == identity.tenant_id)
    if identity.kind == 'customer':
        query = query.where(ChatThread.customer_id == identity.user_id)
    if locked:
        query = query.with_for_update().execution_options(populate_existing=True)
    thread = db.scalar(query)
    store = store_for(db, identity.tenant_id)
    if not thread or thread.account_id != store.id:
        fail(404, 'THREAD_NOT_FOUND', '会话入口不存在')
    return thread


def conversation_for(db, identity, ident, *, locked=False):
    c = db.scalar(select(Conversation).where(Conversation.id == ident,
                                            Conversation.tenant_id == identity.tenant_id))
    if not c or c.thread_id is None:
        fail(404, 'CONVERSATION_NOT_FOUND', '接待记录不存在')
    thread = thread_for(db, identity, c.thread_id, locked=locked)
    if locked:
        c = db.scalar(select(Conversation).where(Conversation.id == ident).with_for_update()
                      .execution_options(populate_existing=True))
    if c.tenant_id != thread.tenant_id or c.thread_id != thread.id or c.user_id != thread.customer_id or c.account_id != thread.account_id:
        fail(404, 'CONVERSATION_NOT_FOUND', '接待记录不存在')
    return thread, c


def current_reception(db, thread):
    if thread.active_conversation_id is None:
        return new_conversation(db, thread)
    c = db.scalar(select(Conversation).where(Conversation.id == thread.active_conversation_id)
                  .with_for_update().execution_options(populate_existing=True))
    if not c or (c.tenant_id, c.thread_id, c.user_id, c.account_id) != (
            thread.tenant_id, thread.id, thread.customer_id, thread.account_id) or c.status == 'CLOSED':
        fail(409, 'INVALID_RECEPTION', '接待关联异常，请联系店铺客服')
    return c


def new_conversation(db, thread, *, agent=None):
    if thread.active_conversation_id is not None:
        fail(409, 'ACTIVE_CONVERSATION', '该客户已有进行中的接待', conversation_id=thread.active_conversation_id)
    from .model_runtime import current_locked
    policy=current_locked(db,thread.tenant_id,'reception')
    automatic=bool(not agent and policy and policy.value.get('enabled'))
    c = Conversation(tenant_id=thread.tenant_id, user_id=thread.customer_id,
                     account_id=thread.account_id, thread_id=thread.id,
                     status='HUMAN_ACTIVE' if agent else 'AI_ACTIVE' if automatic else 'WAITING_USER',
                     current_agent_id=agent.id if agent else None,
                     handoff_reason=None if agent or automatic else 'AI 自动接待尚未开启',
                     handoff_requested_at=None if agent or automatic else utcnow(),
                     ever_handoff_requested=not agent and not automatic, ever_human_claimed=agent is not None,
                     last_message_at=thread.last_message_at or utcnow())
    db.add(c); db.flush()
    thread.active_conversation_id = c.id
    thread.revision += 1
    return c


def open_chat(db, identity):
    with writing(db, identity):
        store = store_for(db, identity.tenant_id)
        thread = db.scalar(select(ChatThread).where(ChatThread.tenant_id == identity.tenant_id,
                ChatThread.account_id == store.id, ChatThread.customer_id == identity.user_id).with_for_update())
        if thread is None:
            thread = ChatThread(tenant_id=identity.tenant_id, account_id=store.id, customer_id=identity.user_id)
            db.add(thread); db.flush()
        c = current_reception(db, thread) if thread.active_conversation_id else db.scalar(
            select(Conversation).where(Conversation.thread_id == thread.id, Conversation.tenant_id == thread.tenant_id,
                Conversation.account_id == thread.account_id, Conversation.user_id == thread.customer_id)
            .order_by(Conversation.id.desc()).limit(1).with_for_update()
            .execution_options(populate_existing=True)) or new_conversation(db, thread)
        result = {'thread_id': thread.id, 'conversation': conversation_view(db, c)}
    return result


def previous_message(db, identity, thread, body):
    row = db.scalar(select(Message).where(Message.tenant_id == identity.tenant_id,
        Message.thread_id == thread.id, Message.sender_user_id == identity.user_id,
        Message.client_message_id == body.client_message_id).with_for_update()
        .execution_options(populate_existing=True))
    if row is not None and row.content != body.content:
        fail(409, 'IDEMPOTENCY_MISMATCH', '同一消息标识不能用于不同内容')
    return row


def save_message(db, identity, thread, c, body):
    now = utcnow()
    row = Message(tenant_id=identity.tenant_id, thread_id=thread.id, conversation_id=c.id,
                  sender_user_id=identity.user_id,
                  sender_type='AGENT' if identity.kind == 'staff' else 'CUSTOMER',
                  client_message_id=body.client_message_id, content=body.content, created_at=now)
    db.add(row); db.flush()
    thread.last_message_id, thread.last_message_at = row.id, now
    thread.revision += 1
    c.last_message_at, c.revision = now, c.revision + 1
    if identity.kind == 'customer':
        c.last_customer_message_at = now
    return row


def send_customer(db, identity, ident, body):
    with writing(db, identity):
        thread = thread_for(db, identity, ident, locked=True)
        row = previous_message(db, identity, thread, body)
        if row is None:
            c = current_reception(db, thread)
            if c.status == 'CLOSED' or c.user_id != identity.user_id:
                fail(409, 'INVALID_RECEPTION', '当前接待已变化，请刷新后重试')
            row = save_message(db, identity, thread, c, body)
            if c.status=='AI_ACTIVE':
                from .workers import enqueue_reply
                enqueue_reply(db,c,row)
        c = db.scalar(select(Conversation).where(Conversation.id == row.conversation_id,
            Conversation.tenant_id == thread.tenant_id, Conversation.thread_id == thread.id,
            Conversation.user_id == thread.customer_id, Conversation.account_id == thread.account_id)
            .with_for_update().execution_options(populate_existing=True))
        if c is None:
            fail(409, 'INVALID_RECEPTION', '消息关联异常，请联系店铺客服')
        result = {'message': message_view(db, row), 'conversation': conversation_view(db, c), 'reply': None}
    return result


def send_staff(db, identity, ident, body):
    with writing(db, identity):
        thread, c = conversation_for(db, identity, ident, locked=True)
        row = previous_message(db, identity, thread, body)
        if row is None:
            if c.status != 'HUMAN_ACTIVE' or c.current_agent_id != identity.user_id or thread.active_conversation_id != c.id:
                fail(403, 'NOT_RECEPTION_OWNER', '只有当前接待客服可以发送')
            row = save_message(db, identity, thread, c, body)
        elif row.conversation_id != c.id:
            fail(409, 'IDEMPOTENCY_MISMATCH', '消息标识属于该客户的另一段接待')
        result = message_view(db, row)
    return result


def audit(db, identity, action, c):
    db.add(AuditLog(tenant_id=identity.tenant_id, actor=f'{identity.kind}:{identity.user_id}',
                   action=action, target=f'conversation:{c.id}',
                   detail={'conversation_id': c.id, 'thread_id': c.thread_id, 'epoch': c.reception_epoch}))


def require_online(user):
    if user.work_status != 'ONLINE':
        fail(409, 'STAFF_OFFLINE', '请先切换为在线，再接入新会话')
    # Sessions also emit heartbeats while staff work on history or settings.
    from datetime import timezone
    if user.last_heartbeat_at is None or (utcnow() - user.last_heartbeat_at.replace(tzinfo=user.last_heartbeat_at.tzinfo or timezone.utc)).total_seconds() > 30:
        fail(409, 'HEARTBEAT_EXPIRED', '连接已失效，请恢复连接后再接入')


def claim(db, identity, ident, body):
    with writing(db, identity) as user:
        thread, c = conversation_for(db, identity, ident, locked=True)
        if c.status != 'HUMAN_ACTIVE' or c.current_agent_id != identity.user_id:
            require_online(user)
            if c.status not in ('WAITING_USER','AI_ACTIVE') or c.current_agent_id is not None or c.reception_epoch != body.expected_epoch:
                fail(409, 'RECEPTION_CHANGED', '该接待已被接入或状态已变化')
            if thread.active_conversation_id != c.id:
                fail(409, 'RECEPTION_CHANGED', '该接待已不是当前接待')
            c.status, c.current_agent_id = 'HUMAN_ACTIVE', identity.user_id
            c.ever_human_claimed = True
            c.reception_epoch += 1; c.revision += 1; thread.revision += 1
            audit(db, identity, 'claim', c)
        result = conversation_view(db, c)
    return result


def finish(db, identity, thread, c, expected_epoch):
    if c.status == 'CLOSED':
        return
    if c.reception_epoch != expected_epoch or thread.active_conversation_id != c.id:
        fail(409, 'RECEPTION_CHANGED', '接待状态已变化，请刷新后确认')
    c.status, c.closed_at = 'CLOSED', utcnow()
    c.reception_epoch += 1; c.revision += 1
    thread.active_conversation_id = None; thread.revision += 1
    # Real summary generation is a later phase; no fabricated summary or usage.
    c.summary_status = 'NONE'
    audit(db, identity, 'close', c)


def close_staff(db, identity, ident, body):
    with writing(db, identity):
        thread, c = conversation_for(db, identity, ident, locked=True)
        if c.current_agent_id != identity.user_id:
            fail(403, 'NOT_RECEPTION_OWNER', '只有当前接待客服可以完结')
        finish(db, identity, thread, c, body.expected_epoch)
        result = conversation_view(db, c)
    return result


def end_customer(db, identity, ident, body):
    with writing(db, identity):
        thread, c = conversation_for(db, identity, body.conversation_id, locked=True)
        if thread.id != ident:
            fail(404, 'CONVERSATION_NOT_FOUND', '接待记录不存在')
        finish(db, identity, thread, c, body.expected_epoch)
        result = conversation_view(db, c)
    return result


def handoff_customer(db, identity, ident, body):
    with writing(db,identity):
        thread,c=conversation_for(db,identity,body.conversation_id,locked=True)
        if thread.id!=ident or thread.active_conversation_id!=c.id:
            fail(409,'RECEPTION_CHANGED','当前接待已变化，请刷新后重试')
        if c.status=='AI_ACTIVE':
            if c.reception_epoch!=body.expected_epoch:fail(409,'RECEPTION_CHANGED','接待状态已变化，请刷新')
            c.status='WAITING_USER';c.reception_epoch+=1;c.revision+=1;thread.revision+=1
            c.handoff_requested_at=utcnow();c.handoff_reason='客户请求人工';c.ever_handoff_requested=True
            audit(db,identity,'handoff',c)
        result=conversation_view(db,c)
    return result


def reopen(db, identity, ident, body):
    with writing(db, identity) as user:
        thread, c = conversation_for(db, identity, ident, locked=True)
        scope = f'reopen:{c.id}'
        fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
        old = db.scalar(select(ReceptionRequest).where(ReceptionRequest.tenant_id == identity.tenant_id,
            ReceptionRequest.actor_id == identity.user_id, ReceptionRequest.scope == scope,
            ReceptionRequest.request_key == body.request_id).with_for_update()
            .execution_options(populate_existing=True))
        if old:
            if old.fingerprint != fingerprint:
                fail(409, 'IDEMPOTENCY_MISMATCH', '同一请求标识不能用于不同操作')
            result = old.result
        else:
            require_online(user)
            if c.status != 'CLOSED' or c.reception_epoch != body.expected_epoch:
                fail(409, 'RECEPTION_CHANGED', '只能从当前版本的已完结接待重新发起')
            fresh = new_conversation(db, thread, agent=user)
            audit(db, identity, 'reopen', fresh)
            result = conversation_view(db, fresh)
            db.add(ReceptionRequest(tenant_id=identity.tenant_id, actor_id=identity.user_id,
                scope=scope, request_key=body.request_id, fingerprint=fingerprint, result=result))
    return result
