"""Store-scoped identities and a single effective staff reception session."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.core.database import get_db
from app.models import User, Tenant, ChannelAccount, utcnow

bearer = HTTPBearer(auto_error=False)


def fail(status, code, message, **data):
    raise HTTPException(status, detail={'code': code, 'message': message, **data})


@dataclass(frozen=True)
class Identity:
    user_id: int
    tenant_id: int
    kind: str
    session_id: str | None = None
    session_version: int | None = None


def store_for(db: Session, tenant_id: int):
    tenant = db.get(Tenant, tenant_id)
    store = db.scalar(select(ChannelAccount).where(ChannelAccount.tenant_id == tenant_id,
                                                  ChannelAccount.active.is_(True)))
    if not tenant or not tenant.active or not store:
        fail(403, 'STORE_UNAVAILABLE', '店铺不可用或尚未绑定')
    return store


def decode(raw: str) -> Identity:
    try:
        value = jwt.decode(raw, settings().jwt_secret, algorithms=['HS256'],
                           options={'require': ['sub', 'kind', 'tenant_id', 'exp', 'iat', 'identity_schema']})
        if value['identity_schema'] != 'store-user-v2' or value['kind'] not in ('staff', 'customer'):
            raise ValueError()
        if not isinstance(value['tenant_id'], int) or isinstance(value['tenant_id'], bool):
            raise ValueError()
        identity = Identity(int(value['sub']), value['tenant_id'], value['kind'],
                            value.get('sid'), value.get('sv'))
        if identity.user_id <= 0 or identity.tenant_id <= 0:
            raise ValueError()
        if identity.kind == 'staff' and (not isinstance(identity.session_id, str)
                or not isinstance(identity.session_version, int)):
            raise ValueError()
        return identity
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        fail(401, 'INVALID_IDENTITY', '登录已失效，请重新登录')


def issue(user: User) -> str:
    now = datetime.now(timezone.utc)
    kind = 'staff' if user.kind == 'STAFF' else 'customer'
    value = {'sub': str(user.id), 'kind': kind, 'tenant_id': user.tenant_id,
             'identity_schema': 'store-user-v2', 'iat': now,
             'exp': now + timedelta(minutes=settings().jwt_minutes)}
    if kind == 'staff':
        value.update(sid=user.session_id, sv=user.session_version)
    return jwt.encode(value, settings().jwt_secret, algorithm='HS256')


def validate(db: Session, identity: Identity, *, locked=False) -> User:
    query = select(User).where(User.id == identity.user_id).execution_options(populate_existing=True)
    if locked:
        # A write obtains SQLite's writer lock too; MySQL also holds the row lock
        # until the business transaction commits, preventing late old-session writes.
        db.execute(update(User).where(User.id == identity.user_id)
                   .values(session_version=User.session_version))
        query = query.with_for_update()
    user = db.scalar(query)
    if not user or not user.active or user.tenant_id != identity.tenant_id:
        fail(401, 'INVALID_IDENTITY', '登录已失效，请重新登录')
    if identity.kind == 'staff':
        if user.kind != 'STAFF' or user.user_type != 'B' or user.role != 'CUSTOMER_SERVICE':
            fail(403, 'STAFF_REQUIRED', '需要客服身份')
        if user.session_id != identity.session_id or user.session_version != identity.session_version:
            fail(401, 'SESSION_REPLACED', '该账号已在其他接待端登录，请重新登录')
    elif user.kind not in ('CUSTOMER', 'GUEST') or user.user_type != 'C':
        fail(403, 'CUSTOMER_REQUIRED', '需要客户身份')
    store_for(db, identity.tenant_id)
    return user


def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
              db: Session = Depends(get_db)) -> Identity:
    if not credentials:
        fail(401, 'AUTH_REQUIRED', '请先登录')
    identity = decode(credentials.credentials)
    validate(db, identity)
    return identity


def staff(identity: Identity = Depends(principal)) -> Identity:
    if identity.kind != 'staff':
        fail(403, 'STAFF_REQUIRED', '需要客服身份')
    return identity


def customer(identity: Identity = Depends(principal)) -> Identity:
    if identity.kind != 'customer':
        fail(403, 'CUSTOMER_REQUIRED', '需要客户身份')
    return identity


def login_session(db: Session, user: User):
    sid = secrets.token_hex(16)
    db.execute(update(User).where(User.id == user.id, User.active.is_(True))
               .values(session_id=sid, session_version=User.session_version + 1,
                       last_heartbeat_at=utcnow()))
    db.flush()
    db.refresh(user)
    return user
