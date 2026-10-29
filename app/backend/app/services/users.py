from fastapi import HTTPException
from datetime import timezone
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session
from app.models import User, AuditLog
from app.core.security import hash_password
from app.schemas.users import StaffCreateRequest, StaffUpdateRequest


def _utc_iso(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def list_users(*, user: User, db: Session):
    rows = db.scalars(select(User).where(User.tenant_id == 1).order_by(User.id)).all()
    return [{"id": row.id, "email": row.email, "role": row.role, "kind": row.kind, "user_type":row.user_type,
             "display_name": row.display_name,"username": row.username or row.email, "visitor_id": row.visitor_id,
             "active": row.active, "created_at": _utc_iso(row.created_at), "updated_at": _utc_iso(row.updated_at)} for row in rows]


def page_users(page: int=1, page_size: int=20, keyword: str='', user_type: str='', role: str='', active: bool | None=None, *, user: User, db: Session):
    filters = [User.tenant_id == user.tenant_id]
    if keyword.strip():
        filters.append(or_(User.username.contains(keyword.strip(), autoescape=True),
                           User.email.contains(keyword.strip(), autoescape=True),
                           User.display_name.contains(keyword.strip(), autoescape=True)))
    if user_type:
        if user_type not in ("B", "C"):
            raise HTTPException(422, "Invalid user type")
        filters.append(User.user_type == user_type)
    if role:
        filters.append(User.role == role)
    if active is not None:
        filters.append(User.active == active)
    total = db.scalar(select(func.count()).select_from(User).where(*filters))
    rows = db.scalars(select(User).where(*filters).order_by(User.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {"id": row.id, "email": row.email, "username": row.username or row.email,
         "display_name": row.display_name, "user_type": row.user_type, "kind": row.kind,
         "role": row.role, "active": row.active, "created_at": _utc_iso(row.created_at),
         "updated_at": _utc_iso(row.updated_at)} for row in rows]}


def create_user(body: StaffCreateRequest, *, user: User, db: Session):
    allowed_roles = ("ADMIN", "KNOWLEDGE_MANAGER", "CUSTOMER_SERVICE", "VIEWER") if body.user_type == "B" else ("CUSTOMER",)
    if body.user_type not in ("B", "C") or body.role not in allowed_roles:
        raise HTTPException(422, "Invalid role")
    username = (body.username or body.email or "").strip()
    if not username:
        raise HTTPException(422, "Username is required")
    identifiers = [username] + ([body.email] if body.email else [])
    if db.scalar(select(User).where(or_(User.username.in_(identifiers), User.email.in_(identifiers)))):
        raise HTTPException(409, "Username or email already exists")
    row = User(tenant_id=user.tenant_id, username=username, email=body.email,
               display_name=body.display_name.strip(), user_type=body.user_type,
               kind="STAFF" if body.user_type == "B" else "CUSTOMER",
               password_hash=hash_password(body.password), role=body.role)
    db.add(row)
    db.flush()
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="user_create",
                    target=f"user:{row.id}", detail={"role": body.role}))
    db.commit()
    return {"id": row.id, "email": row.email, "role": row.role}


def update_user(user_id: int, body: StaffUpdateRequest, *, user: User, db: Session):
    row = db.get(User, user_id)
    if not row or row.tenant_id != user.tenant_id:
        raise HTTPException(404, "User not found")
    if row.role == "SUPER_ADMIN" or (row.id == user.id and body.active is False):
        raise HTTPException(403, "This account cannot be changed")
    if body.role is not None:
        if row.kind != 'STAFF':
            raise HTTPException(422,'顾客与游客不能通过角色编辑升级为员工')
        if body.role not in ("ADMIN", "KNOWLEDGE_MANAGER", "CUSTOMER_SERVICE", "VIEWER"):
            raise HTTPException(422, "Invalid role")
        row.role = body.role
    if body.active is not None:
        row.active = body.active
    if body.display_name is not None:
        row.display_name = body.display_name.strip()
    if body.password is not None:
        if row.kind == 'GUEST':
            raise HTTPException(422,'游客使用浏览器凭证，不能设置账号密码')
        row.password_hash=hash_password(body.password)
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="user_update",
                    target=f"user:{row.id}", detail={"role": row.role, "active": row.active}))
    db.commit()
    return {"id": row.id, "email": row.email, "role": row.role, "active": row.active}
