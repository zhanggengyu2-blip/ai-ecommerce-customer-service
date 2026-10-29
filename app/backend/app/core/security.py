import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.core.database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt$16384${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, n, salt, digest = encoded.split("$")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def token(subject: str, kind: str, tenant_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": subject, "kind": kind, "tenant_id": tenant_id,
                       "identity_schema": "clean-user-v1", "iat": now, "exp": now + timedelta(minutes=settings().jwt_minutes)},
                      settings().jwt_secret, algorithm="HS256")


def decode_token(raw: str) -> dict:
    try:
        claims = jwt.decode(raw, settings().jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "kind", "tenant_id"]})
        if claims.get('identity_schema') != 'clean-user-v1' or claims['tenant_id'] != 1:
            raise jwt.InvalidTokenError('Identity schema or single-store scope mismatch')
        int(claims['sub'])
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(401, "Authorization required")
    claims = decode_token(credentials.credentials)
    kind = claims["kind"]
    ident = int(claims["sub"])
    entity = db.get(User, ident) if kind in ("customer", "staff") else None
    if (not entity or not entity.active or entity.tenant_id != 1
            or kind == 'staff' and (entity.kind != 'STAFF' or entity.user_type != 'B')
            or kind == 'customer' and (entity.kind not in ('CUSTOMER', 'GUEST') or entity.user_type != 'C')):
        raise HTTPException(401, "Invalid identity")
    return kind, entity


def customer_required(p=Depends(principal)) -> User:
    if p[0] != "customer":
        raise HTTPException(403, "User access required")
    return p[1]


def staff_required(p=Depends(principal)) -> User:
    if p[0] != "staff":
        raise HTTPException(403, "Staff access required")
    return p[1]


def role_required(*roles: str):
    def check(user: User = Depends(staff_required)) -> User:
        if user.role not in roles and user.role != "SUPER_ADMIN":
            raise HTTPException(403, "Insufficient role")
        return user
    return check
