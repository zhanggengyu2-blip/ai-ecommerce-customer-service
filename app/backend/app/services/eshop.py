"""Transactional local commerce simulator. No payment or carrier is contacted."""
import uuid
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User, ExternalCustomerIdentity, EshopCustomer, EshopProduct, EshopOrder, EshopOrderItem, EshopPayment, EshopShipment, EshopRefund, EshopInventoryLog, AuditLog, utcnow


class CommerceError(ValueError):
    pass


def number(prefix):
    return prefix + '-' + uuid.uuid4().hex[:16].upper()


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))


def find(db, model, tenant_id, ident, lock=False):
    query = select(model).where(model.id == ident, model.tenant_id == tenant_id)
    row = db.scalar(query.with_for_update() if lock else query)
    if not row:
        raise CommerceError('数据不存在或无权访问')
    return row


def order_by_number(db, tenant_id, order_no, user_id=None, account_id=None):
    query = select(EshopOrder).where(EshopOrder.tenant_id == tenant_id, EshopOrder.order_id == order_no)
    if account_id is not None:
        query = query.where(EshopOrder.account_id == account_id)
    if user_id is not None:
        query = query.where(EshopOrder.user_id == user_id)
    row = db.scalar(query.with_for_update())
    if not row:
        raise CommerceError('订单不存在或不属于当前客户')
    return row


def audit(db, tenant_id, actor, action, target, detail=None):
    db.add(AuditLog(tenant_id=tenant_id, actor=actor, action='eshop_' + action,
                    target=target, detail=detail or {}))


def stock(db, product, available_delta, reserved_delta, actor, reason, order=None):
    available, reserved = product.inventory + available_delta, product.reserved + reserved_delta
    if available < 0 or reserved < 0:
        raise CommerceError('库存不足或占用库存不一致')
    product.inventory, product.reserved = available, reserved
    db.add(EshopInventoryLog(product_id=product.id, order_id=order.id if order else None,
                            delta=available_delta, reserved_delta=reserved_delta,
                            available_after=available, reserved_after=reserved, actor=actor, reason=reason))


def create_customer(db, tenant_id, body, actor, account_id=1):
    if body.user_id is not None:
        existing=db.get(User,body.user_id)
        if not existing:
            raise CommerceError('用户不存在')
    else:
        existing=db.scalar(select(User).where(User.username==body.username))
    if existing is None:
        existing = User(tenant_id=1, kind='CUSTOMER', user_type='C', role='CUSTOMER', username=body.username, display_name=body.name)
        db.add(existing)
    db.flush()
    if existing.tenant_id!=tenant_id or existing.user_type!='C' or not existing.active:
        raise CommerceError('客户档案只能关联启用的 C 端用户')
    if account_id != 1 and existing.kind == 'GUEST':
        raise CommerceError('第三方平台买家不能关联自营游客身份')
    other_profile = db.scalar(select(EshopCustomer.id).where(EshopCustomer.user_id == existing.id,
        EshopCustomer.account_id != account_id))
    other_link = db.scalar(select(ExternalCustomerIdentity.id).where(
        ExternalCustomerIdentity.user_id == existing.id,
        ExternalCustomerIdentity.account_id != account_id))
    if other_profile or other_link:
        raise CommerceError('不同账号的买家默认分开，请创建独立客户用户')
    if db.scalar(select(EshopCustomer.id).where(EshopCustomer.user_id==existing.id,
                                                 EshopCustomer.account_id==account_id)):
        raise CommerceError('该账号下用户已有客户档案')
    row=EshopCustomer(tenant_id=tenant_id,account_id=account_id,user_id=existing.id,
                      name=body.name,phone=body.phone,address=body.address)
    db.add(row);db.flush()
    if account_id != 1 and not db.scalar(select(ExternalCustomerIdentity.id).where(
            ExternalCustomerIdentity.account_id == account_id,
            ExternalCustomerIdentity.user_id == existing.id)):
        db.add(ExternalCustomerIdentity(account_id=account_id,
            external_user_id=f'mock-{account_id}-{existing.id}', user_id=existing.id))
    audit(db, tenant_id, actor, 'customer_create', f'eshop_customer:{row.id}')
    return row


def create_product(db, tenant_id, body, actor, account_id=1):
    if db.scalar(select(EshopProduct).where(EshopProduct.account_id == account_id,
                                            EshopProduct.sku == body.sku)):
        raise CommerceError('SKU 已存在')
    data = body.model_dump()
    initial = data.pop('inventory')
    row = EshopProduct(tenant_id=tenant_id, account_id=account_id, inventory=0, reserved=0, **data)
    db.add(row)
    db.flush()
    stock(db, row, initial, 0, actor, '商品初始入库')
    audit(db, tenant_id, actor, 'product_create', f'eshop_product:{row.id}')
    return row


def create_order(db, tenant_id, body, actor, account_id=1):
    customer=db.scalar(select(EshopCustomer).where(EshopCustomer.user_id==body.user_id,
        EshopCustomer.tenant_id==tenant_id, EshopCustomer.account_id==account_id))
    if not customer:
        raise CommerceError('请先为此 C 端用户创建收货档案')
    product = find(db, EshopProduct, tenant_id, body.product_id, True)
    if product.account_id != account_id:
        raise CommerceError('商品不属于当前账号')
    if product.status != 'ON_SALE':
        raise CommerceError('商品未上架，不能下单')
    if product.inventory < body.quantity:
        raise CommerceError('可售库存不足')
    amount = money(product.price) * body.quantity
    if amount > Decimal('9999999999.99'):
        raise CommerceError('订单金额超出可处理范围，请减少购买数量')
    receiver = body.receiver or {'name': customer.name, 'phone': customer.phone, 'address': customer.address}
    if not all(str(receiver.get(key, '')).strip() for key in ('name', 'phone', 'address')):
        raise CommerceError('请先填写完整的收件人、电话和地址')
    owner = db.get(User, customer.user_id)
    if not owner or not owner.active or owner.user_type != 'C':
        raise CommerceError('客户账号不可用')
    order = EshopOrder(tenant_id=tenant_id, account_id=account_id, user_id=customer.user_id,
                       order_id=number('ESH'), product_sku=product.sku,
                       quantity=body.quantity, amount=amount,
                       status='UNPAID', stock_reserved=True, receiver=receiver)
    db.add(order)
    db.flush()
    db.add(EshopOrderItem(order_id=order.id, product_id=product.id, sku=product.sku,
                          name=product.name, unit_price=product.price, quantity=body.quantity))
    stock(db, product, -body.quantity, body.quantity, actor, '下单占用库存', order)
    audit(db, tenant_id, actor, 'order_create', order.order_id, {'amount': str(order.amount), 'quantity': body.quantity})
    return order


def pay(db, order, method, actor):
    existing = db.scalar(select(EshopPayment).where(EshopPayment.order_id == order.id))
    if existing and existing.status == 'SUCCESS' and order.status in ('PAID', 'SHIPPED', 'DELIVERED'):
        return existing
    if order.status != 'UNPAID' or existing:
        raise CommerceError('只有待支付订单可以支付')
    payment = EshopPayment(order_id=order.id, payment_no=number('PAY'), method=method, amount=order.amount)
    db.add(payment)
    order.status = 'PAID'
    audit(db, order.tenant_id, actor, 'pay', order.order_id, {'amount': str(order.amount), 'method': method})
    return payment


def order_product(db, order):
    product = db.scalar(select(EshopProduct).where(EshopProduct.tenant_id == order.tenant_id,
                                                  EshopProduct.account_id == order.account_id,
                                                  EshopProduct.sku == order.product_sku).with_for_update())
    if not product:
        raise CommerceError('订单关联商品不存在')
    return product


def cancel(db, order, actor):
    if order.status not in ('UNPAID', 'PAID') or order.refund_status != 'NONE':
        raise CommerceError('仅未发货且没有售后申请的订单可以取消')
    payment = db.scalar(select(EshopPayment).where(EshopPayment.order_id == order.id))
    if order.status == 'PAID' and (not payment or payment.status != 'SUCCESS' or money(payment.amount) != money(order.amount)):
        raise CommerceError('支付记录或金额不一致，不能取消已支付订单')
    if order.stock_reserved:
        stock(db, order_product(db, order), order.quantity, -order.quantity, actor, '取消订单释放占用', order)
        order.stock_reserved = False
    if payment:
        payment.status, payment.refunded_amount = 'REFUNDED', order.amount
        db.add(EshopRefund(order_id=order.id, refund_no=number('REF'), amount=order.amount,
                           reason='取消已支付订单，模拟原路退款', original_status=order.status, status='COMPLETED'))
        order.refund_status = 'COMPLETED'
    order.status, order.shipping_status = 'CANCELLED', 'CANCELLED'
    audit(db, order.tenant_id, actor, 'cancel', order.order_id)


def ship(db, order, carrier, tracking_number, actor):
    if order.status != 'PAID' or order.refund_status != 'NONE':
        raise CommerceError('只有已支付且无售后的订单可以发货')
    if db.scalar(select(EshopShipment).where(EshopShipment.tracking_number == tracking_number)):
        raise CommerceError('运单号已使用')
    if not order.stock_reserved:
        raise CommerceError('订单没有对应的占用库存，不能发货')
    payment = db.scalar(select(EshopPayment).where(EshopPayment.order_id == order.id))
    if not payment or payment.status != 'SUCCESS' or money(payment.amount) != money(order.amount):
        raise CommerceError('支付记录或金额不一致，不能发货')
    stock(db, order_product(db, order), 0, -order.quantity, actor, '发货出库', order)
    order.stock_reserved = False
    shipment = EshopShipment(order_id=order.id, carrier=carrier, tracking_number=tracking_number,
                             events=[{'time': utcnow().isoformat(), 'status': 'IN_TRANSIT', 'description': '商家已发货，快递已揽收'}])
    db.add(shipment)
    order.status, order.shipping_status = 'SHIPPED', 'IN_TRANSIT'
    order.carrier, order.tracking_number = carrier, tracking_number
    audit(db, order.tenant_id, actor, 'ship', order.order_id, {'carrier': carrier, 'tracking_number': tracking_number})
    return shipment


def logistics(db, order, status, description, actor):
    shipment = db.scalar(select(EshopShipment).where(EshopShipment.order_id == order.id).with_for_update())
    if not shipment or order.status != 'SHIPPED' or shipment.status == 'DELIVERED':
        raise CommerceError('只有运输中的订单可以更新物流')
    if shipment.status == 'OUT_FOR_DELIVERY' and status == 'IN_TRANSIT':
        raise CommerceError('派送中的包裹不能退回运输中状态')
    shipment.status = order.shipping_status = status
    shipment.events = [*shipment.events, {'time': utcnow().isoformat(), 'status': status, 'description': description}]
    if status == 'DELIVERED':
        order.status = 'DELIVERED'
    audit(db, order.tenant_id, actor, 'logistics', order.order_id, {'status': status})
    return shipment


def request_refund(db, order, reason, actor):
    if order.status not in ('PAID', 'SHIPPED', 'DELIVERED') or order.refund_status != 'NONE':
        raise CommerceError('当前订单不满足全额退款条件，或已有售后申请')
    payment = db.scalar(select(EshopPayment).where(EshopPayment.order_id == order.id))
    if not payment or payment.status != 'SUCCESS' or money(payment.amount) != money(order.amount):
        raise CommerceError('支付记录或金额不一致，不能申请退款')
    refund = EshopRefund(order_id=order.id, refund_no=number('REF'), amount=order.amount,
                         reason=reason, original_status=order.status)
    db.add(refund)
    order.status, order.refund_status = 'REFUNDING', 'REQUESTED'
    audit(db, order.tenant_id, actor, 'refund_request', order.order_id, {'amount': str(order.amount)})
    return refund


def process_refund(db, tenant_id, refund_id, action, tracking, actor):
    # Always lock the order first, matching checkout/cancellation lock order.
    candidate = db.scalar(select(EshopRefund).join(EshopOrder, EshopRefund.order_id == EshopOrder.id)
                           .where(EshopRefund.id == refund_id, EshopOrder.tenant_id == tenant_id))
    if not candidate:
        raise CommerceError('退款单不存在或无权访问')
    order = find(db, EshopOrder, tenant_id, candidate.order_id, True)
    refund = db.scalar(select(EshopRefund).where(EshopRefund.id == refund_id).with_for_update())
    if action == 'approve' and refund.status == 'REQUESTED':
        refund.status = 'APPROVED'
    elif action == 'reject' and refund.status == 'REQUESTED':
        refund.status = 'REJECTED'
        order.status, order.refund_status = refund.original_status, 'NONE'
    elif action == 'receive' and refund.status == 'APPROVED' and refund.original_status in ('SHIPPED', 'DELIVERED'):
        if not tracking.strip():
            raise CommerceError('请填写客户退货运单号后验收入库')
        refund.status, refund.return_tracking = 'RECEIVED', tracking
        stock(db, order_product(db, order), order.quantity, 0, actor, '退货验收回库', order)
    elif action == 'complete' and (refund.status == 'RECEIVED' or refund.status == 'APPROVED' and refund.original_status == 'PAID'):
        payment = db.scalar(select(EshopPayment).where(EshopPayment.order_id == order.id).with_for_update())
        if not payment or payment.status != 'SUCCESS' or money(payment.amount) != money(refund.amount):
            raise CommerceError('支付记录或退款金额不一致，不能完成退款')
        if order.stock_reserved:
            stock(db, order_product(db, order), order.quantity, -order.quantity, actor, '未发货退款释放占用', order)
            order.stock_reserved = False
        payment.status, payment.refunded_amount = 'REFUNDED', refund.amount
        refund.status, order.status = 'COMPLETED', 'REFUNDED'
        if refund.original_status == 'PAID':
            order.shipping_status = 'CANCELLED'
    else:
        raise CommerceError('退款状态不允许此操作；已发货订单需先验收退货，再完成退款')
    if action != 'reject':
        order.refund_status = refund.status
    audit(db, tenant_id, actor, 'refund_' + action, order.order_id, {'refund_no': refund.refund_no})
    return refund


def order_view(db, order):
    items = db.scalars(select(EshopOrderItem).where(EshopOrderItem.order_id == order.id)).all()
    owner=db.get(User,order.user_id)
    return {'id': order.id, 'order_id': order.order_id, 'user_id': order.user_id,
            'customer_username': owner.username, 'product_sku': order.product_sku,
            'quantity': order.quantity, 'amount': str(order.amount), 'status': order.status,
            'shipping_status': order.shipping_status, 'refund_status': order.refund_status,
            'carrier': order.carrier, 'tracking_number': order.tracking_number, 'receiver': order.receiver,
            'created_at': order.created_at.isoformat(), 'stock_reserved': order.stock_reserved,
            'items': [{'sku': item.sku, 'name': item.name, 'unit_price': str(item.unit_price), 'quantity': item.quantity} for item in items]}


def product_view(product):
    return {key: getattr(product, key) for key in ('id', 'sku', 'name', 'inventory', 'reserved', 'status', 'description')} | {'price': str(product.price)}
