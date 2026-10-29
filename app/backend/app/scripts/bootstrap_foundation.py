"""Initialize one explicitly requested local store in an already migrated database."""
import argparse
from sqlalchemy import select, or_
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Tenant, ChannelAccount, User


def create_store(db, *, name, entry_code, username, password):
    if not name.strip() or len(password) < 12:
        raise ValueError('Store name and a password of at least 12 characters are required')
    import re
    if not re.fullmatch(r'[a-z0-9_-]{3,32}', entry_code):
        raise ValueError('Invalid store entry code')
    if db.scalar(select(ChannelAccount.id).where(ChannelAccount.entry_code == entry_code)):
        raise ValueError('Store entry already exists; existing records were not reset')
    if db.scalar(select(User.id).where(or_(User.username == username, User.email == username))):
        raise ValueError('Staff account already exists')
    tenant = Tenant(name=name.strip()); db.add(tenant); db.flush()
    store = ChannelAccount(tenant_id=tenant.id, entry_code=entry_code, name=name.strip(),
                           platform_code='SELF', category='SELF', commerce_enabled=True, active=True)
    db.add(store)
    user = User(tenant_id=tenant.id, kind='STAFF', user_type='B', role='CUSTOMER_SERVICE',
                username=username, display_name='客服小林', password_hash=hash_password(password))
    db.add(user); db.flush()
    return {'tenant_id': tenant.id, 'account_id': store.id, 'user_id': user.id, 'entry_code': entry_code}


def main():
    import getpass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--entry-code', required=True)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Initial staff password (at least 12 characters): ')
    with SessionLocal.begin() as db:
        result = create_store(db, name=args.name, entry_code=args.entry_code,
                              username=args.username, password=password)
    print('Created store and staff identity: ' + str(result))

if __name__ == '__main__':
    main()
