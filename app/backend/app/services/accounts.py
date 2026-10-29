from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import ChannelAccount, StaffAccountAccess, ExternalCustomerIdentity, User

PLATFORMS = {
    'SELF': ('自营', 'SELF', True),
    'PINDUODUO': ('拼多多', 'ECOMMERCE', True),
    'DOUDIAN': ('抖店', 'ECOMMERCE', True),
    'TIKTOK_SHOP': ('TikTok Shop', 'ECOMMERCE', True),
    'SHOPEE': ('Shopee', 'ECOMMERCE', True),
    'LAZADA': ('Lazada', 'ECOMMERCE', True),
    'ALIEXPRESS': ('速卖通', 'ECOMMERCE', True),
    'WECHAT_OFFICIAL': ('公众号', 'MEDIA', False),
    'DOUYIN_MEDIA': ('抖音', 'MEDIA', False),
    'KUAISHOU': ('快手', 'MEDIA', False),
}


def visible_account_ids(db: Session, user: User) -> list[int]:
    if user.role in ('SUPER_ADMIN', 'ADMIN', 'VIEWER', 'KNOWLEDGE_MANAGER'):
        return list(db.scalars(select(ChannelAccount.id).where(ChannelAccount.active.is_(True))))
    return list(db.scalars(select(StaffAccountAccess.account_id).join(ChannelAccount,
        StaffAccountAccess.account_id == ChannelAccount.id).where(StaffAccountAccess.user_id == user.id,
        ChannelAccount.active.is_(True))))


def require_account(db: Session, account_id: int, user: User | None = None,
                    commerce: bool = False) -> ChannelAccount:
    row = db.get(ChannelAccount, account_id)
    if not row or not row.active:
        raise HTTPException(404, '接入账号不存在或已停用')
    if commerce and not row.commerce_enabled:
        raise HTTPException(409, '此账号没有电商能力')
    if user and user.user_type == 'B' and row.id not in visible_account_ids(db, user):
        raise HTTPException(403, '无权访问此接入账号')
    return row


def customer_account_ids(db: Session, user: User) -> list[int]:
    linked = list(db.scalars(select(ExternalCustomerIdentity.account_id)
                             .where(ExternalCustomerIdentity.user_id == user.id)))
    # Native website identities (including guests) belong to the self account.
    return linked if linked else [1]


def require_customer_account(db: Session, account_id: int, user: User) -> ChannelAccount:
    row = require_account(db, account_id)
    if account_id not in customer_account_ids(db, user):
        raise HTTPException(403, '客户身份不属于此接入账号')
    return row


def account_view(row: ChannelAccount) -> dict:
    return {'id': row.id, 'platform_code': row.platform_code,
            'platform_name': PLATFORMS[row.platform_code][0], 'name': row.name,
            'external_account_id': row.external_account_id, 'category': row.category,
            'commerce_enabled': row.commerce_enabled, 'active': row.active}
