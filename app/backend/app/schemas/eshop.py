from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class CustomerInput(BaseModel):
    user_id: int | None = Field(default=None,gt=0)
    username: str | None = Field(default=None,min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=1, max_length=32)
    address: str = Field(min_length=1, max_length=512)

    @model_validator(mode='after')
    def identity_input(self):
        if (self.user_id is None)==(self.username is None):
            raise ValueError('选择已有用户或填写新用户名，二选一')
        return self

    @field_validator('name', 'phone', 'address')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('字段不能为空')
        return value.strip()


class ProductInput(BaseModel):
    sku: str = Field(min_length=3, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    inventory: int = Field(ge=0, le=1000000)
    status: Literal['ON_SALE', 'OFF_SALE'] = 'ON_SALE'
    description: str = Field(default='', max_length=4000)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    status: Literal['ON_SALE', 'OFF_SALE'] | None = None
    description: str | None = Field(default=None, max_length=4000)


class InventoryInput(BaseModel):
    delta: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=1, max_length=255)


class Receiver(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=1, max_length=32)
    address: str = Field(min_length=1, max_length=512)


class OrderInput(BaseModel):
    user_id: int
    product_id: int
    quantity: int = Field(ge=1, le=1000)
    receiver: dict | None = None

    @field_validator('receiver')
    @classmethod
    def valid_receiver(cls, value):
        return Receiver.model_validate(value).model_dump() if value is not None else None


class PayInput(BaseModel):
    method: Literal['MOCK_ALIPAY', 'MOCK_WECHAT', 'MOCK_BANK'] = 'MOCK_ALIPAY'


class ShipInput(BaseModel):
    carrier: str = Field(min_length=1, max_length=64)
    tracking_number: str = Field(min_length=3, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')


class LogisticsInput(BaseModel):
    status: Literal['IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED']
    description: str = Field(min_length=1, max_length=512)


class RefundInput(BaseModel):
    reason: str = Field(min_length=1, max_length=512)


class RefundAction(BaseModel):
    action: Literal['approve', 'reject', 'receive', 'complete']
    return_tracking: str = Field(default='', max_length=128)
