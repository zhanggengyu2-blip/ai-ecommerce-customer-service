from fastapi import APIRouter
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.core.database import get_db
from app.models import User
from app.core.security import token, verify_password
from app.core.rate_limit import check_rate_limit
from app.schemas.auth import LoginRequest, CustomerTokenRequest

router = APIRouter(tags=["auth"])


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f"login:{request.client.host if request.client else 'unknown'}", 10, 60)
    account=(body.account or body.email or '').strip()
    matches=db.scalars(select(User).where(or_(User.email == account,User.username == account),User.kind.in_(['STAFF','CUSTOMER']))).all()
    user=matches[0] if len(matches)==1 else None
    if not account or not user or user.tenant_id != 1 or not user.active or not verify_password(body.password, user.password_hash or ''):
        raise HTTPException(401, "Invalid credentials")
    from app.api.v1.identity import user_view
    return {"access_token": token(str(user.id), 'staff' if user.kind=='STAFF' else 'customer',1), "role": user.role,'user':user_view(user)}


@router.post("/api/internal/customer-token")
def customer_token(body: CustomerTokenRequest, request: Request, x_integration_secret: str = Header(default=""), db: Session = Depends(get_db)):
    check_rate_limit(f"integration:{request.client.host if request.client else 'unknown'}", 120, 60)
    import hmac
    if not settings().customer_token_secret or not hmac.compare_digest(x_integration_secret, settings().customer_token_secret):
        raise HTTPException(403, "Invalid integration secret")
    customer = db.scalar(select(User).where(User.tenant_id == 1, User.username == body.username))
    if not customer:
        customer = User(tenant_id=1, kind='CUSTOMER', user_type='C', role='CUSTOMER', username=body.username, display_name=body.display_name)
        db.add(customer)
        db.commit()
        db.refresh(customer)
    if customer.kind != 'CUSTOMER' or not customer.active:
        raise HTTPException(403,'User identity unavailable')
    return {"access_token": token(str(customer.id), "customer", 1)}


@router.post("/api/demo/customer-login")
def demo_customer_login(request: Request, db: Session = Depends(get_db)):
    if not settings().demo_enabled or not request.client or request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(404, "Demo login unavailable")
    customer = db.scalar(select(User).where(User.tenant_id == 1, User.username == "demo-customer"))
    if not customer:
        raise HTTPException(409, "Run demo seed first")
    if customer.kind != 'CUSTOMER' or not customer.active:
        raise HTTPException(403, "User identity unavailable")
    return {"access_token": token(str(customer.id), "customer", customer.tenant_id)}
