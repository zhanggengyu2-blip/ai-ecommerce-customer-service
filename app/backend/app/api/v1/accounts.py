from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import role_required
from app.models import ChannelAccount, StaffAccountAccess, User
from app.services.accounts import PLATFORMS, account_view, visible_account_ids

router = APIRouter(tags=['接入账号'])


class AccountInput(BaseModel):
    platform_code: str
    name: str = Field(min_length=1, max_length=128)
    external_account_id: str | None = Field(default=None, max_length=128)




@router.get('/api/admin/platforms')
def platforms(user: User = Depends(role_required('ADMIN', 'CUSTOMER_SERVICE', 'KNOWLEDGE_MANAGER', 'VIEWER'))):
    return [{'code': code, 'name': label, 'category': category,
             'commerce_enabled': commerce} for code, (label, category, commerce) in PLATFORMS.items()]


@router.get('/api/admin/accounts')
def accounts(user: User = Depends(role_required('ADMIN', 'CUSTOMER_SERVICE', 'KNOWLEDGE_MANAGER', 'VIEWER')),
             db: Session = Depends(get_db)):
    ids = visible_account_ids(db, user)
    if not ids:
        return []
    return [account_view(row) for row in db.scalars(select(ChannelAccount).where(ChannelAccount.id.in_(ids)).order_by(ChannelAccount.id))]


@router.post('/api/admin/accounts')
def create_account(body: AccountInput, user: User = Depends(role_required('ADMIN')),
                   db: Session = Depends(get_db)):
    if body.platform_code not in PLATFORMS:
        raise HTTPException(422, '不支持的平台')
    label, category, commerce = PLATFORMS[body.platform_code]
    if db.scalar(select(ChannelAccount.id).where(ChannelAccount.platform_code == body.platform_code,
                                                  ChannelAccount.name == body.name.strip())):
        raise HTTPException(409, '平台下已存在同名账号')
    row = ChannelAccount(platform_code=body.platform_code, name=body.name.strip(),
                         external_account_id=body.external_account_id, category=category,
                         commerce_enabled=commerce)
    db.add(row); db.commit(); db.refresh(row)
    return account_view(row)



@router.get('/api/admin/users/{staff_id}/accounts')
def staff_accounts(staff_id: int, user: User = Depends(role_required('ADMIN')),
                   db: Session = Depends(get_db)):
    staff = db.get(User, staff_id)
    if not staff or staff.user_type != 'B':
        raise HTTPException(404, '员工不存在')
    return list(db.scalars(select(StaffAccountAccess.account_id).where(StaffAccountAccess.user_id == staff_id)))


@router.put('/api/admin/users/{staff_id}/accounts')
def set_staff_accounts(staff_id: int, account_ids: list[int], user: User = Depends(role_required('ADMIN')),
                       db: Session = Depends(get_db)):
    staff = db.get(User, staff_id)
    if not staff or staff.user_type != 'B':
        raise HTTPException(404, '员工不存在')
    ids = set(account_ids)
    if any(not db.get(ChannelAccount, ident) for ident in ids):
        raise HTTPException(422, '账号不存在')
    db.execute(delete(StaffAccountAccess).where(StaffAccountAccess.user_id == staff_id))
    db.add_all(StaffAccountAccess(user_id=staff_id, account_id=ident) for ident in ids)
    db.commit()
    return {'account_ids': sorted(ids)}
