from app.schemas.eshop import CustomerInput, ProductInput, ProductUpdate, InventoryInput, Receiver, OrderInput, PayInput, ShipInput, LogisticsInput, RefundInput, RefundAction
from decimal import Decimal
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.services import eshop
from app.config.settings import settings
from app.core.database import get_db
from app.models import User, EshopCustomer, EshopProduct, EshopOrder, EshopPayment, EshopShipment, EshopRefund, EshopInventoryLog
from app.core.security import role_required, token
from app.services.accounts import require_account

router = APIRouter(prefix='/api/admin/eshop', tags=['电商管理'])


def enabled():
    if settings().business_mode != 'mock' or not settings().demo_enabled:
        raise HTTPException(404, '电商管理仅在本机演示模式下开放')


router.dependencies.append(Depends(enabled))
read_access = role_required('ADMIN', 'VIEWER')
write_access = role_required('ADMIN')


def commerce_account(account_id: int = 1, user: User = Depends(read_access), db: Session = Depends(get_db)) -> int:
    require_account(db, account_id, user, commerce=True)
    return account_id


def scoped(db, model, user, ident, account_id):
    row = eshop.find(db, model, user.tenant_id, ident, True)
    if row.account_id != account_id:
        raise eshop.CommerceError('数据不属于当前账号')
    return row
























def mutate(db, user, callback, view=lambda row: {'id': row.id}):
    try:
        row = callback(f'staff:{user.id}')
        db.flush()
        result = view(row)
        db.commit()
        return result
    except eshop.CommerceError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '数据重复或状态冲突，请刷新后重试') from exc


@router.get('/customers')
def customers(account_id: int = Depends(commerce_account), user: User = Depends(read_access), db: Session = Depends(get_db)):
    rows = db.scalars(select(EshopCustomer).where(EshopCustomer.tenant_id == user.tenant_id,
        EshopCustomer.account_id == account_id).order_by(EshopCustomer.id.desc()).limit(500)).all()
    return [{key: getattr(row, key) for key in ('id', 'user_id', 'name', 'phone', 'address')} | {'username':db.get(User,row.user_id).username} for row in rows]


@router.post('/customers')
def add_customer(body: CustomerInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    return mutate(db, user, lambda actor: eshop.create_customer(db, user.tenant_id, body, actor, account_id),lambda row:{'id':row.id,'user_id':row.user_id})


@router.patch('/customers/{user_id}')
def edit_customer(user_id: int, body: Receiver, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    def change(actor):
        row = db.scalar(select(EshopCustomer).where(EshopCustomer.user_id == user_id,
                        EshopCustomer.tenant_id == user.tenant_id,
                        EshopCustomer.account_id == account_id).with_for_update())
        if not row:
            raise eshop.CommerceError('客户档案不存在')
        values = {key: value.strip() for key, value in body.model_dump().items()}
        if not all(values.values()):
            raise eshop.CommerceError('姓名、电话和收货地址不能为空')
        for key, value in values.items():
            setattr(row, key, value)
        eshop.audit(db, user.tenant_id, actor, 'customer_update', f'eshop_customer:{row.id}')
        return row
    return mutate(db, user, change, lambda row: {'id': row.id, 'user_id': row.user_id})


@router.post('/customers/{user_id}/session')
def customer_session(user_id: int, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    def create(actor):
        row=db.scalar(select(EshopCustomer).where(EshopCustomer.user_id==user_id,
            EshopCustomer.tenant_id==user.tenant_id,EshopCustomer.account_id==account_id))
        if not row:
            raise eshop.CommerceError('此用户没有客户档案')
        customer = db.get(User, row.user_id) if row.user_id else None
        if not customer or customer.user_type != 'C' or not customer.active:
            raise eshop.CommerceError('客户没有有效的统一用户身份')
        eshop.audit(db, user.tenant_id, actor, 'customer_session', f'eshop_customer:{row.id}')
        return customer
    return mutate(db, user, create, lambda row: {'access_token': token(str(row.id), 'customer', 1), 'display_name': row.display_name, 'user_id': row.id, 'kind': row.kind})


@router.get('/customer-users')
def customer_users(account_id: int = Depends(commerce_account), user: User = Depends(read_access),db: Session=Depends(get_db)):
    rows=db.scalars(select(User).where(User.user_type=='C',User.active.is_(True),User.tenant_id==1,
                  User.kind != 'GUEST',
                  ~User.id.in_(select(EshopCustomer.user_id))).order_by(User.id).limit(500)).all()
    return [{'id':row.id,'username':row.username,'display_name':row.display_name,'kind':row.kind} for row in rows]


@router.get('/products')
def products(account_id: int = Depends(commerce_account), user: User = Depends(read_access), db: Session = Depends(get_db)):
    return [eshop.product_view(row) for row in db.scalars(select(EshopProduct).where(EshopProduct.tenant_id == user.tenant_id,
        EshopProduct.account_id == account_id).order_by(EshopProduct.id.desc()).limit(500)).all()]


@router.post('/products')
def add_product(body: ProductInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    return mutate(db, user, lambda actor: eshop.create_product(db, user.tenant_id, body, actor, account_id), eshop.product_view)


@router.patch('/products/{product_id}')
def update_product(product_id: int, body: ProductUpdate, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    def apply(actor):
        row = scoped(db, EshopProduct, user, product_id, account_id)
        changes = body.model_dump(exclude_none=True)
        for key, value in changes.items():
            setattr(row, key, value)
        eshop.audit(db, user.tenant_id, actor, 'product_update', f'eshop_product:{row.id}', {key: str(value) for key, value in changes.items()})
        return row
    return mutate(db, user, apply, eshop.product_view)


@router.post('/products/{product_id}/inventory')
def inventory(product_id: int, body: InventoryInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    def apply(actor):
        row = scoped(db, EshopProduct, user, product_id, account_id)
        eshop.stock(db, row, body.delta, 0, actor, body.reason)
        eshop.audit(db, user.tenant_id, actor, 'inventory_adjust', f'eshop_product:{row.id}', {'delta': body.delta, 'reason': body.reason})
        return row
    return mutate(db, user, apply, eshop.product_view)


@router.get('/orders')
def orders(account_id: int = Depends(commerce_account), user: User = Depends(read_access), db: Session = Depends(get_db)):
    return [eshop.order_view(db, row) for row in db.scalars(select(EshopOrder).where(EshopOrder.tenant_id == user.tenant_id,
        EshopOrder.account_id == account_id).order_by(EshopOrder.id.desc()).limit(200)).all()]


@router.post('/orders')
def add_order(body: OrderInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    return mutate(db, user, lambda actor: eshop.create_order(db, user.tenant_id, body, actor, account_id), lambda row: eshop.order_view(db, row))


@router.post('/orders/{order_id}/pay')
def payment(order_id: int, body: PayInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    return mutate(db, user, lambda actor: eshop.pay(db, scoped(db, EshopOrder, user, order_id, account_id), body.method, actor))


@router.post('/orders/{order_id}/cancel')
def cancellation(order_id: int, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    def apply(actor):
        row = scoped(db, EshopOrder, user, order_id, account_id)
        eshop.cancel(db, row, actor)
        return row
    return mutate(db, user, apply, lambda row: eshop.order_view(db, row))


@router.post('/orders/{order_id}/ship')
def shipping(order_id: int, body: ShipInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    return mutate(db, user, lambda actor: eshop.ship(db, scoped(db, EshopOrder, user, order_id, account_id), body.carrier, body.tracking_number, actor))


@router.post('/orders/{order_id}/logistics')
def logistics(order_id: int, body: LogisticsInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    return mutate(db, user, lambda actor: eshop.logistics(db, scoped(db, EshopOrder, user, order_id, account_id), body.status, body.description, actor))


@router.post('/orders/{order_id}/refund')
def request_refund(order_id: int, body: RefundInput, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    return mutate(db, user, lambda actor: eshop.request_refund(db, scoped(db, EshopOrder, user, order_id, account_id), body.reason, actor))


@router.post('/refunds/{refund_id}/process')
def refund_action(refund_id: int, body: RefundAction, account_id: int = Depends(commerce_account), user: User = Depends(write_access), db: Session = Depends(get_db)):
    refund = db.get(EshopRefund, refund_id)
    if not refund:
        raise HTTPException(404, '退款单不存在')
    scoped(db, EshopOrder, user, refund.order_id, account_id)
    return mutate(db, user, lambda actor: eshop.process_refund(db, user.tenant_id, refund_id, body.action, body.return_tracking, actor))


@router.get('/payments')
def payments(account_id: int = Depends(commerce_account), user: User = Depends(read_access), db: Session = Depends(get_db)):
    rows = db.execute(select(EshopPayment, EshopOrder.order_id, User.username).join(EshopOrder, EshopPayment.order_id == EshopOrder.id).join(User, EshopOrder.user_id == User.id).where(EshopOrder.tenant_id == user.tenant_id, EshopOrder.account_id == account_id).order_by(EshopPayment.id.desc()).limit(200)).all()
    return [{'id': row.id, 'order_id': order_no, 'customer': customer, 'payment_no': row.payment_no,
             'method': row.method, 'amount': str(row.amount), 'refunded_amount': str(row.refunded_amount), 'status': row.status} for row, order_no, customer in rows]


@router.get('/shipments')
def shipments(account_id: int = Depends(commerce_account), user: User = Depends(read_access), db: Session = Depends(get_db)):
    rows = db.execute(select(EshopShipment, EshopOrder.order_id, User.username).join(EshopOrder, EshopShipment.order_id == EshopOrder.id).join(User, EshopOrder.user_id == User.id).where(EshopOrder.tenant_id == user.tenant_id, EshopOrder.account_id == account_id).order_by(EshopShipment.id.desc()).limit(200)).all()
    return [{'id': row.id, 'order_id': order_no, 'customer': customer, 'carrier': row.carrier, 'tracking_number': row.tracking_number, 'status': row.status, 'events': row.events} for row, order_no, customer in rows]


@router.get('/refunds')
def refunds(account_id: int = Depends(commerce_account), user: User = Depends(read_access), db: Session = Depends(get_db)):
    rows = db.execute(select(EshopRefund, EshopOrder.order_id, User.username).join(EshopOrder, EshopRefund.order_id == EshopOrder.id).join(User, EshopOrder.user_id == User.id).where(EshopOrder.tenant_id == user.tenant_id, EshopOrder.account_id == account_id).order_by(EshopRefund.id.desc()).limit(200)).all()
    return [{'id': row.id, 'order_id': order_no, 'customer': customer, 'refund_no': row.refund_no,
             'amount': str(row.amount), 'reason': row.reason, 'status': row.status, 'original_status': row.original_status, 'return_tracking': row.return_tracking} for row, order_no, customer in rows]


@router.get('/inventory-logs')
def inventory_logs(account_id: int = Depends(commerce_account), user: User = Depends(read_access), db: Session = Depends(get_db)):
    rows = db.execute(select(EshopInventoryLog, EshopProduct.sku).join(EshopProduct, EshopInventoryLog.product_id == EshopProduct.id).where(EshopProduct.tenant_id == user.tenant_id, EshopProduct.account_id == account_id).order_by(EshopInventoryLog.id.desc()).limit(200)).all()
    return [{key: getattr(row, key) for key in ('id', 'delta', 'reserved_delta', 'available_after', 'reserved_after', 'reason', 'actor')} | {'sku': sku, 'created_at': row.created_at.isoformat()} for row, sku in rows]
