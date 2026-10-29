"""Phase-one store and durable reception APIs. No external commerce or model calls."""
import hashlib
import hmac
import secrets
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select, func, or_, desc
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.core.rate_limit import check_rate_limit
from app.models import User, Tenant, ChannelAccount, Conversation, ChatThread, Message, utcnow
from . import schemas as S, reception as R
from .security import Identity, staff, customer, principal, validate, fail, issue, store_for, login_session
from .views import conversation_view, message_view, user_view, iso

router = APIRouter()
Page = Query(1, ge=1)
Size = Query(25, ge=1, le=100)


@router.get('/health')
def health():
    return {'status': 'ok', 'mode': 'foundation', 'taobao_messages': False, 'taobao_orders': False}


@router.post('/api/auth/login')
def login(body: S.Login, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f'foundation-login:{request.client.host if request.client else "unknown"}', 20, 60)
    value = body.account.strip()
    users = db.scalars(select(User).where(or_(User.username == value, User.email == value))).all()
    user = users[0] if len(users) == 1 else None
    if not user or not user.active or user.kind != 'STAFF' or user.role != 'CUSTOMER_SERVICE' or not verify_password(body.password, user.password_hash or ''):
        fail(401, 'INVALID_CREDENTIALS', '账号或密码不正确')
    with R.writing(db):
        # Serialize account replacement with business writes from the previous session.
        user = db.scalar(select(User).where(User.id == user.id).with_for_update()
                         .execution_options(populate_existing=True))
        if not user.active:
            fail(401, 'INVALID_CREDENTIALS', '账号或密码不正确')
        store_for(db, user.tenant_id)
        login_session(db, user)
        result = {'access_token': issue(user), 'role': user.role, 'user': user_view(user)}
    return result


@router.get('/api/auth/me')
def me(identity: Identity = Depends(principal), db: Session = Depends(get_db)):
    return user_view(validate(db, identity))


@router.post('/api/auth/logout')
def logout(identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    with R.writing(db, identity) as user:
        user.session_id = None; user.session_version += 1; user.work_status = 'OFFLINE'
    return {'ok': True}


@router.put('/api/agent/presence')
def presence(body: S.Presence, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    with R.writing(db, identity) as user:
        user.work_status = body.status; user.last_heartbeat_at = utcnow()
        result = user_view(user)
    return result


@router.post('/api/agent/heartbeat')
def heartbeat(identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    with R.writing(db, identity) as user:
        user.last_heartbeat_at = utcnow()
        result = {'server_time': iso(user.last_heartbeat_at), 'work_status': user.work_status}
    return result


@router.get('/api/admin/store')
def store(identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    row = store_for(db, identity.tenant_id)
    from .model_runtime import automatic_enabled
    return {'id': row.id, 'name': row.name, 'entry_code': row.entry_code,
            'platform_code': row.platform_code, 'connection_status': 'NOT_CONNECTED',
            'capabilities': {'taobao_messages': False, 'taobao_orders': False,
                             'automatic_reception': True, 'reception_enabled':automatic_enabled(db,identity.tenant_id),
                             'knowledge':True, 'reply_assist': False,
                             'attachments': False, 'tickets': False}}


@router.get('/api/admin/users/page')
def users(page: int = Page, page_size: int = Size, keyword: str = '',
          identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    where = [User.tenant_id == identity.tenant_id, User.kind == 'STAFF', User.role == 'CUSTOMER_SERVICE']
    if keyword.strip():
        where.append(or_(User.username.contains(keyword.strip(), autoescape=True),
                         User.display_name.contains(keyword.strip(), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(User).where(*where))
    rows = db.scalars(select(User).where(*where).order_by(User.id).offset((page-1)*page_size).limit(page_size)).all()
    return {'items': [user_view(u) for u in rows], 'total': total, 'page': page, 'page_size': page_size}


@router.post('/api/admin/users')
def create_staff(body: S.StaffCreate, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    with R.writing(db, identity):
        username = body.username.strip()
        if not body.display_name.strip() or not username:
            fail(422, 'INVALID_STAFF', '账号和客服名称不能为空')
        # Keep both old identifier namespaces disjoint, including email aliases.
        if db.scalar(select(User.id).where(or_(User.username == username, User.email == username))):
            fail(409, 'ACCOUNT_EXISTS', '账号已被使用')
        user = User(tenant_id=identity.tenant_id, username=username, display_name=body.display_name.strip(),
                    kind='STAFF', user_type='B', role='CUSTOMER_SERVICE', password_hash=hash_password(body.password))
        db.add(user); db.flush()
        result = user_view(user)
    return result


@router.patch('/api/admin/users/{user_id}')
def update_staff(user_id: int, body: S.StaffUpdate, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    # Serialize with login and writes by this account; no role or tenant fields are accepted.
    with R.writing(db, identity):
        user = db.scalar(select(User).where(User.id == user_id, User.tenant_id == identity.tenant_id,
            User.kind == 'STAFF', User.role == 'CUSTOMER_SERVICE').with_for_update().execution_options(populate_existing=True))
        if not user:
            fail(404, 'STAFF_NOT_FOUND', '客服账号不存在')
        if user.id == identity.user_id and body.active is False:
            fail(409, 'CANNOT_DISABLE_SELF', '不能停用当前登录账号')
        if body.display_name is not None:
            user.display_name = body.display_name
        if body.active is not None:
            user.active = body.active
            if not user.active:
                user.session_version += 1; user.session_id = None; user.work_status = 'OFFLINE'
        result = user_view(user)
    return result


@router.post('/api/auth/guest-session')
def guest(body: S.Guest, request: Request, response: Response, db: Session = Depends(get_db)):
    check_rate_limit(f'foundation-guest:{request.client.host if request.client else "unknown"}', 60, 60)
    account = db.scalar(select(ChannelAccount).where(ChannelAccount.entry_code == body.entry_code,
                                                    ChannelAccount.active.is_(True)))
    if account is None or account.tenant_id is None:
        fail(404, 'STORE_NOT_FOUND', '店铺入口不存在')
    store_for(db, account.tenant_id)
    scoped_id = hashlib.sha256(f'{account.tenant_id}:{body.visitor_id}'.encode()).hexdigest()
    user = db.scalar(select(User).where(User.visitor_id == scoped_id))
    cookie_name = 'foundation_visitor_' + body.entry_code
    cookie = request.cookies.get(cookie_name, '')
    supplied = body.visitor_proof or ''
    proof = supplied or cookie or secrets.token_urlsafe(32)
    with R.writing(db):
        if user is not None:
            valid = lambda value: bool(value) and hmac.compare_digest(hashlib.sha256(value.encode()).hexdigest(), user.visitor_secret_hash or '')
            if user.tenant_id != account.tenant_id or user.kind != 'GUEST' or not user.active or not (valid(supplied) or valid(cookie)):
                fail(409, 'VISITOR_PROOF_REQUIRED', '访客凭证不匹配，请恢复该店铺的原凭证')
            proof = supplied if valid(supplied) else cookie
        else:
            user = User(tenant_id=account.tenant_id, visitor_id=scoped_id,
                        visitor_secret_hash=hashlib.sha256(proof.encode()).hexdigest(),
                        kind='GUEST', user_type='C', role='GUEST',
                        username=f'visitor-{account.tenant_id}-{scoped_id[:24]}', display_name='访客 ' + body.visitor_id[:6])
            db.add(user); db.flush()
        result = {'access_token': issue(user), 'visitor_id': body.visitor_id,
                  'visitor_proof': proof, 'user': user_view(user), 'store_name': account.name}
    response.set_cookie(cookie_name, proof, httponly=True, samesite='lax',
                        secure=request.url.scheme == 'https', max_age=365*24*3600)
    return result


@router.post('/api/customer/chat')
def open_chat(identity: Identity = Depends(customer), db: Session = Depends(get_db)):
    return R.open_chat(db, identity)


@router.post('/api/customer/threads/{ident}/messages')
def send_customer(ident: int, body: S.Send, identity: Identity = Depends(customer), db: Session = Depends(get_db)):
    check_rate_limit(f'foundation-chat:{identity.tenant_id}:{identity.user_id}', 60, 60)
    return R.send_customer(db, identity, ident, body)


@router.post('/api/customer/threads/{ident}/end')
def end_customer(ident: int, body: S.End, identity: Identity = Depends(customer), db: Session = Depends(get_db)):
    return R.end_customer(db, identity, ident, body)


@router.post('/api/customer/threads/{ident}/handoff')
def handoff_customer(ident:int,body:S.End,identity:Identity=Depends(customer),db:Session=Depends(get_db)):
    return R.handoff_customer(db,identity,ident,body)


def messages(db, identity, ident, after_id, page_size, *, conversation=False):
    if conversation:
        thread, c = R.conversation_for(db, identity, ident)
    else:
        thread = R.thread_for(db, identity, ident)
    where = [Message.tenant_id == identity.tenant_id, Message.thread_id == thread.id, Message.id > after_id]
    if conversation:
        where.append(Message.conversation_id == c.id)
    where.extend([Conversation.tenant_id == thread.tenant_id, Conversation.thread_id == thread.id,
                  Conversation.account_id == thread.account_id, Conversation.user_id == thread.customer_id])
    rows = db.scalars(select(Message).join(Conversation, Conversation.id == Message.conversation_id)
                      .where(*where).order_by(Message.id).limit(page_size+1)).all()
    items = rows[:page_size]
    return {'items': [message_view(db, m) for m in items], 'has_more': len(rows)>page_size,
            'next_cursor': items[-1].id if items else after_id}


@router.get('/api/customer/threads/{ident}/messages')
def customer_messages(ident: int, after_id: int = Query(0, ge=0), page_size: int = Size,
                      identity: Identity = Depends(customer), db: Session = Depends(get_db)):
    return messages(db, identity, ident, after_id, page_size)


@router.get('/api/customer/threads/{ident}')
def customer_thread(ident: int, identity: Identity = Depends(customer), db: Session = Depends(get_db)):
    thread = R.thread_for(db, identity, ident)
    if thread.active_conversation_id:
        _, c = R.conversation_for(db, identity, thread.active_conversation_id)
        if c.thread_id != ident or c.status == 'CLOSED':
            fail(409, 'INVALID_RECEPTION', '接待关联异常，请联系店铺客服')
    else:
        c = db.scalar(select(Conversation).where(Conversation.thread_id == ident,
                Conversation.tenant_id == identity.tenant_id, Conversation.user_id == identity.user_id,
                Conversation.account_id == thread.account_id).order_by(Conversation.id.desc()).limit(1))
    return {'thread_id': ident, 'conversation': conversation_view(db, c) if c else None}


@router.get('/api/agent/threads/{ident}/messages')
def agent_thread_messages(ident: int, after_id: int = Query(0, ge=0), page_size: int = Size,
                          identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    return messages(db, identity, ident, after_id, page_size)


@router.get('/api/agent/conversations/{ident}/messages')
@router.get('/api/admin/conversations/{ident}/messages')
def reception_messages(ident: int, after_id: int = Query(0, ge=0), page_size: int = Size,
                       identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    return messages(db, identity, ident, after_id, page_size, conversation=True)


@router.get('/api/agent/threads')
def threads(page: int = Page, page_size: int = Size, status: str = '', keyword: str = '',
            identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    latest = select(func.max(Conversation.id)).where(Conversation.thread_id == ChatThread.id).correlate(ChatThread).scalar_subquery()
    query = select(ChatThread, Conversation).join(Conversation, Conversation.id == func.coalesce(ChatThread.active_conversation_id, latest))
    where = [ChatThread.tenant_id == identity.tenant_id, ChatThread.account_id == store_for(db, identity.tenant_id).id,
             Conversation.tenant_id == identity.tenant_id, Conversation.thread_id == ChatThread.id,
             Conversation.account_id == ChatThread.account_id, Conversation.user_id == ChatThread.customer_id]
    if status:
        if status not in ('AI_ACTIVE','WAITING_USER','HUMAN_ACTIVE','CLOSED'):
            fail(422, 'INVALID_STATUS', '接待状态不正确')
        where.append(Conversation.status == status)
    if keyword.strip():
        query = query.join(User, User.id == ChatThread.customer_id)
        where.append(User.display_name.contains(keyword.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.where(*where).subquery()))
    rows = db.execute(query.where(*where).order_by(ChatThread.last_message_at.desc(), ChatThread.id.desc())
                      .offset((page-1)*page_size).limit(page_size)).all()
    return {'items': [conversation_view(db, c) | {'thread_revision': thread.revision} for thread,c in rows],
            'total': total, 'page': page, 'page_size': page_size}


@router.post('/api/agent/conversations/{ident}/claim')
def claim(ident: int, body: S.Transition, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    return R.claim(db, identity, ident, body)


@router.post('/api/agent/conversations/{ident}/messages')
def send_staff(ident: int, body: S.Send, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    return R.send_staff(db, identity, ident, body)


@router.post('/api/agent/conversations/{ident}/close')
def close(ident: int, body: S.Transition, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    return R.close_staff(db, identity, ident, body)


@router.post('/api/agent/conversations/{ident}/reopen')
def reopen(ident: int, body: S.Reopen, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    return R.reopen(db, identity, ident, body)


@router.get('/api/admin/conversations')
def history(page: int = Page, page_size: int = Size, customer_id: int | None = None,
            identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    where = [Conversation.tenant_id == identity.tenant_id, Conversation.status == 'CLOSED',
             Conversation.account_id == store_for(db, identity.tenant_id).id, Conversation.thread_id.is_not(None)]
    if customer_id is not None:
        where.append(Conversation.user_id == customer_id)
    total = db.scalar(select(func.count()).select_from(Conversation).where(*where))
    rows = db.scalars(select(Conversation).where(*where).order_by(Conversation.closed_at.desc(), Conversation.id.desc())
                      .offset((page-1)*page_size).limit(page_size)).all()
    return {'items': [conversation_view(db, c) for c in rows], 'total': total, 'page': page, 'page_size': page_size}


@router.get('/api/admin/conversations/{ident}')
def detail(ident: int, identity: Identity = Depends(staff), db: Session = Depends(get_db)):
    _, c = R.conversation_for(db, identity, ident)
    return conversation_view(db, c)


from .ai_api import router as ai_router
router.include_router(ai_router)
