from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ChannelAccount(Base):
    __tablename__ = 'channel_account'
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey('tenant.id'), nullable=True)
    entry_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    platform_code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    external_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str] = mapped_column(String(16))  # SELF, ECOMMERCE, MEDIA
    commerce_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('platform_code', 'name'),
                      UniqueConstraint('tenant_id', name='uq_channel_tenant'),
                      UniqueConstraint('entry_code', name='uq_channel_entry'))


class StaffAccountAccess(Base):
    __tablename__ = 'staff_account_access'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user.id'), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'), index=True)
    __table_args__ = (UniqueConstraint('user_id', 'account_id'),)


class ExternalCustomerIdentity(Base):
    __tablename__ = 'external_customer_identity'
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('channel_account.id'), index=True)
    external_user_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[int] = mapped_column(ForeignKey('user.id'), index=True)
    __table_args__ = (UniqueConstraint('account_id', 'external_user_id'),)
