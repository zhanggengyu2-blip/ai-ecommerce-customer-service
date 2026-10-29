"""Persistent demo commerce adapter. It enforces the same customer boundary as a real API."""
import uuid
from decimal import Decimal
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.models import EshopOperation, EshopOrder, EshopProduct, EshopPayment, EshopShipment, EshopRefund, User
from app.services import eshop


class MockBusinessError(RuntimeError):
    pass


def _result(data: dict, request_id: str | None = None) -> dict:
    return {"success": True, "code": "OK", "message": "", "data": data,
            "request_id": request_id or "mock-" + uuid.uuid4().hex[:12]}


def run_mock_tool(db: Session, user_id: int, name: str, identifier: str,
                  idempotency_key: str | None = None, tenant_id: int = 1, account_id: int = 1) -> dict:
    owner=db.get(User,user_id)
    if not owner or not owner.active or owner.user_type!='C' or owner.tenant_id!=tenant_id:
        raise MockBusinessError('ORDER_NOT_FOUND_OR_FORBIDDEN')
    owner_filter = EshopOrder.user_id == user_id
    if name == "search_products":
        query = identifier.strip()
        rows = db.scalars(select(EshopProduct).where(EshopProduct.tenant_id == tenant_id,
            EshopProduct.account_id == account_id,
            EshopProduct.status == "ON_SALE", or_(EshopProduct.name.contains(query, autoescape=True),
            EshopProduct.sku.contains(query, autoescape=True))).order_by(EshopProduct.id.desc()).limit(6)).all()
        return _result({"products": [{"sku": row.sku, "name": row.name} for row in rows[:5]], "has_more": len(rows) > 5})
    if name == "list_orders":
        rows = db.scalars(select(EshopOrder).where(owner_filter, EshopOrder.tenant_id == tenant_id,
            EshopOrder.account_id == account_id)
                          .order_by(EshopOrder.id.desc()).limit(10)).all()
        return _result({"orders": [{"order_id": row.order_id, "status": row.status} for row in rows]})

    if name in ("get_product", "get_inventory"):
        product = db.scalar(select(EshopProduct).where(EshopProduct.sku == identifier,
            EshopProduct.tenant_id == tenant_id, EshopProduct.account_id == account_id))
        if not product:
            raise MockBusinessError("PRODUCT_NOT_FOUND")
        if name == "get_inventory":
            return _result({"inventory": product.inventory, "name": product.name})
        return _result({"name": product.name, "price": str(product.price), "inventory": product.inventory, "status": product.status})

    order = db.scalar(select(EshopOrder).where(EshopOrder.order_id == identifier,
                                              owner_filter,
                                              EshopOrder.tenant_id == tenant_id,
                                              EshopOrder.account_id == account_id).with_for_update())
    if not order:
        raise MockBusinessError("ORDER_NOT_FOUND_OR_FORBIDDEN")

    if name == "get_order":
        payment = db.scalar(select(EshopPayment).where(EshopPayment.order_id == order.id))
        return _result({"status": order.status, "cancellable": order.status in ("UNPAID", "PAID") and order.refund_status == "NONE",
                        "amount": str(order.amount), "quantity": order.quantity, "product_sku": order.product_sku,
                        "payment_status": payment.status if payment else "UNPAID",
                        "requires_human_approval": False})
    if name == "get_shipping":
        shipment = db.scalar(select(EshopShipment).where(EshopShipment.order_id == order.id))
        return _result({"status": order.shipping_status, "carrier": order.carrier,
                        "tracking_number": order.tracking_number, "events": shipment.events if shipment else []})
    if name == "get_refund_status":
        latest_refund = db.scalar(select(EshopRefund).where(EshopRefund.order_id == order.id)
                                  .order_by(EshopRefund.created_at.desc(), EshopRefund.id.desc()).limit(1))
        return _result({"refund_status": latest_refund.status if latest_refund else order.refund_status,
                        "updated_at": latest_refund.updated_at.isoformat() if latest_refund and latest_refund.updated_at else None})
    if name == "get_refund_eligibility":
        payment = db.scalar(select(EshopPayment).where(EshopPayment.order_id == order.id))
        eligible = (order.status in ("PAID", "SHIPPED", "DELIVERED") and order.refund_status == "NONE"
                    and payment is not None and payment.status == 'SUCCESS' and eshop.money(payment.amount) == eshop.money(order.amount))
        return _result({"eligible": eligible,
                        "refundable_amount": str(order.amount) if eligible else None,
                        "requires_human_approval": False})

    if name not in ("cancel_order", "apply_refund"):
        raise MockBusinessError("UNKNOWN_TOOL")
    if not idempotency_key:
        raise MockBusinessError("IDEMPOTENCY_KEY_REQUIRED")
    previous = db.scalar(select(EshopOperation).where(EshopOperation.idempotency_key == idempotency_key))
    if previous:
        if (previous.action, previous.order_id, previous.user_id) != (name, identifier, user_id):
            raise MockBusinessError("IDEMPOTENCY_KEY_CONFLICT")
        return previous.response

    try:
        if name == "cancel_order":
            eshop.cancel(db, order, f"customer:{user_id}")
        else:
            eshop.request_refund(db, order, "客服聊天确认申请退款", f"customer:{user_id}")
    except eshop.CommerceError as exc:
        db.rollback()
        raise MockBusinessError(str(exc)) from exc
    response = _result({"status": order.status, "refund_status": order.refund_status})
    db.add(EshopOperation(idempotency_key=idempotency_key, action=name, order_id=identifier,
                         user_id=user_id, response=response))
    db.flush()
    return response
