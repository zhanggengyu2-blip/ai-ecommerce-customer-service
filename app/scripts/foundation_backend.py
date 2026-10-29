"""Run the foundation API on an isolated development database; retain the old preview."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'var' / 'foundation'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize-only', action='store_true')
    parser.add_argument('--port', type=int, default=8002)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True); DATA.chmod(0o700)
    os.chdir(DATA)
    sys.path.insert(0, str(ROOT / 'backend'))
    secrets_file = DATA / 'local-access.json'
    if secrets_file.exists():
        access = json.loads(secrets_file.read_text())
    else:
        access = {'jwt_secret': secrets.token_urlsafe(48), 'staff_account': 'qinghe-service',
                  'staff_password': secrets.token_urlsafe(18), 'entry_code': 'qinghe'}
        descriptor = os.open(secrets_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as file:
            json.dump(access, file, ensure_ascii=False, indent=2)
    login_file = DATA / 'local-login.txt'
    descriptor = os.open(login_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(login_file, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        file.write('本机基础改造工作台\n入口：http://127.0.0.1:6174/?mode=live\n账号：' + access['staff_account']
                   + '\n密码：' + access['staff_password'] + '\n')
    from cryptography.fernet import Fernet
    key_file = DATA / 'model-encryption.key'
    if not key_file.exists():
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as file:
            file.write(Fernet.generate_key())
    os.environ['MODEL_ENCRYPTION_KEY'] = key_file.read_text().strip()
    os.environ.update(FOUNDATION_ENABLED='true', DATABASE_URL='sqlite:///' + str(DATA / 'service.db'),
        JWT_SECRET=access['jwt_secret'], BOOTSTRAP_ADMIN_PASSWORD='', LLM_MODE='remote', BUSINESS_MODE='mock',
        DEMO_ENABLED='false', OPENSEARCH_URL='', MINIO_ENDPOINT='', ASYNC_INGESTION='false')
    from app.core.database import engine, SessionLocal
    from app.foundation.migrate import upgrade
    from app.scripts.bootstrap_foundation import create_store
    from app.models import ChannelAccount
    from sqlalchemy import select
    upgrade(engine)
    with SessionLocal.begin() as db:
        if not db.scalar(select(ChannelAccount.id).where(ChannelAccount.entry_code == access['entry_code'])):
            create_store(db, name='青禾服饰', entry_code=access['entry_code'],
                         username=access['staff_account'], password=access['staff_password'])
    (DATA / 'service.db').chmod(0o600)
    print('Foundation API: http://127.0.0.1:' + str(args.port), flush=True)
    print('Local login details: ' + str(login_file), flush=True)
    if not args.initialize_only:
        import uvicorn
        uvicorn.run('app.main:app', host='127.0.0.1', port=args.port, log_level='info')

if __name__ == '__main__':
    main()
