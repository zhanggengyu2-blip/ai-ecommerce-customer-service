from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Integer, DateTime, Boolean, JSON, UniqueConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, utcnow


class EshopCustomer(Base):
    __tablename__ = "eshop_customer"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'), default=1, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), default=1, index=True)
    name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str] = mapped_column(String(32), default="")
    address: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('account_id', 'user_id'),)


class EshopProduct(Base):
    __tablename__ = "eshop_product"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), default=1, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'), default=1, index=True)
    sku: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    inventory: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ON_SALE")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("account_id", "sku"),)


class EshopOrder(Base):
    __tablename__ = "eshop_order"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenant.id"), default=1, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'), default=1, index=True)
    order_id: Mapped[str] = mapped_column(String(128))
    product_sku: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(32))
    stock_reserved: Mapped[bool] = mapped_column(Boolean, default=False)
    receiver: Mapped[dict] = mapped_column(JSON, default=dict)
    shipping_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refund_status: Mapped[str] = mapped_column(String(32), default="NONE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint('account_id', 'order_id'),)


class EshopOrderItem(Base):
    __tablename__ = "eshop_order_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("eshop_order.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("eshop_product.id"))
    sku: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer)


class EshopPayment(Base):
    __tablename__ = "eshop_payment"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("eshop_order.id"), unique=True)
    payment_no: Mapped[str] = mapped_column(String(64), unique=True)
    method: Mapped[str] = mapped_column(String(24), default="MOCK_ALIPAY")
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    refunded_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(24), default="SUCCESS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EshopShipment(Base):
    __tablename__ = "eshop_shipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("eshop_order.id"), unique=True)
    carrier: Mapped[str] = mapped_column(String(64))
    tracking_number: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="IN_TRANSIT")
    events: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EshopRefund(Base):
    __tablename__ = "eshop_refund"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("eshop_order.id"), index=True)
    refund_no: Mapped[str] = mapped_column(String(64), unique=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(512), default="客户申请退款")
    status: Mapped[str] = mapped_column(String(24), default="REQUESTED")
    original_status: Mapped[str] = mapped_column(String(32))
    return_tracking: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EshopInventoryLog(Base):
    __tablename__ = "eshop_inventory_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("eshop_product.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("eshop_order.id"), nullable=True)
    delta: Mapped[int] = mapped_column(Integer)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0)
    available_after: Mapped[int] = mapped_column(Integer)
    reserved_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EshopOperation(Base):
    __tablename__ = "eshop_operation"
    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    action: Mapped[str] = mapped_column(String(32))
    order_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
