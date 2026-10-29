from app.schemas.auth import GuestRequest
import hashlib
import hmac
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User, EshopCustomer, EshopOrder, ChannelAccount
from app.core.security import principal, customer_required, token, decode_token
from app.core.rate_limit import check_rate_limit
from app.services.eshop import order_view
from app.services.accounts import account_view, require_customer_account, customer_account_ids

router = APIRouter(tags=['统一用户'])


def user_view(user):
    return {'id':user.id,'kind':user.kind,'user_type':user.user_type,'role':user.role,
            'username':user.username or user.email or str(user.id),'display_name':user.display_name or user.email or '用户',
            'active':user.active}




@router.post('/api/auth/guest-session')
def guest_session(body: GuestRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    check_rate_limit(f'guest:{request.client.host if request.client else "unknown"}',60,60)
    visitor_id = body.visitor_id.lower()
    user = db.scalar(select(User).where(User.visitor_id == visitor_id))
    proof = request.cookies.get('agentserve_visitor','')
    cookie_hash=hashlib.sha256(proof.encode()).hexdigest() if proof else ''
    # Recover the browser identity if localStorage was lost but its cookie remains.
    if proof:
        cookie_user=db.scalar(select(User).where(User.kind=='GUEST',User.visitor_secret_hash==cookie_hash))
        if cookie_user:
            user=cookie_user
    client_proof=body.visitor_proof or ''
    if user:
        if user.kind != 'GUEST' or not user.active:
            raise HTTPException(403,'访客账号不可用')
        cookie_valid=bool(proof) and hmac.compare_digest(cookie_hash,user.visitor_secret_hash or '')
        client_valid=bool(client_proof) and hmac.compare_digest(hashlib.sha256(client_proof.encode()).hexdigest(),user.visitor_secret_hash or '')
        bearer_valid=False
        authorization=request.headers.get('authorization','')
        if authorization.startswith('Bearer '):
            try:
                claims=decode_token(authorization[7:])
                bearer_valid=claims['kind']=='customer' and int(claims['sub'])==user.id
            except HTTPException:
                pass
        if not (cookie_valid or client_valid or bearer_valid):
            raise HTTPException(409,'已有游客凭证不可用，请恢复浏览器凭证；系统不会自动创建重复游客')
        proof=client_proof or proof or secrets.token_urlsafe(32)
        user.visitor_secret_hash=hashlib.sha256(proof.encode()).hexdigest()
        if body.fingerprint:
            user.browser_fingerprint=body.fingerprint
        db.commit()
    else:
        proof = client_proof or secrets.token_urlsafe(32)
        user = User(tenant_id=1,kind='GUEST',user_type='C',role='GUEST',visitor_id=visitor_id,
                    username='visitor-'+visitor_id,display_name='游客 '+visitor_id[:8],
                    visitor_secret_hash=hashlib.sha256(proof.encode()).hexdigest(),browser_fingerprint=body.fingerprint)
        db.add(user)
        try:
            db.commit();db.refresh(user)
        except IntegrityError:
            db.rollback()
            raise HTTPException(409,'访客标识冲突，请重试')
    response.set_cookie('agentserve_visitor',proof,max_age=365*24*3600,httponly=True,samesite='lax',secure=request.url.scheme=='https',path='/')
    return {'access_token':token(str(user.id),'customer',1),'visitor_id':user.visitor_id,'user':user_view(user)}


@router.get('/api/auth/me')
def me(p=Depends(principal)):
    return user_view(p[1])


@router.get('/api/customer/orders')
def customer_orders(account_id: int = 1, user: User = Depends(customer_required), db: Session = Depends(get_db)):
    account = require_customer_account(db, account_id, user)
    if not account.commerce_enabled:
        raise HTTPException(409, '此账号没有电商能力')
    orders = db.scalars(select(EshopOrder).where(EshopOrder.user_id==user.id,
        EshopOrder.account_id==account_id).order_by(EshopOrder.id.desc()).limit(50)).all()
    return [order_view(db,order) for order in orders]


@router.get('/api/customer/accounts')
def customer_accounts(user: User = Depends(customer_required), db: Session = Depends(get_db)):
    return [account_view(row) for row in db.scalars(select(ChannelAccount)
        .where(ChannelAccount.active.is_(True), ChannelAccount.id.in_(customer_account_ids(db, user)))
        .order_by(ChannelAccount.id))]
