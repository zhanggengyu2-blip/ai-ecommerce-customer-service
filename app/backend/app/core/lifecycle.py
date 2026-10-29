from contextlib import asynccontextmanager
from sqlalchemy import select
from app.config.settings import settings
from app.core.database import engine, SessionLocal
from app.models import Base, Tenant, User, ChannelAccount
from app.core.security import hash_password


def startup():
    if settings().foundation_enabled:
        from app.foundation.migrate import assert_ready
        if len(settings().jwt_secret) < 32 or settings().jwt_secret == 'change-me-before-production':
            raise RuntimeError('Set a unique JWT_SECRET of at least 32 characters')
        assert_ready(engine)
        return
    if not settings().database_url.startswith("sqlite") and (settings().jwt_secret == "change-me-before-production" or len(settings().jwt_secret) < 32):
        raise RuntimeError("Set a unique JWT_SECRET of at least 32 characters")
    if settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(Tenant, 1):
            db.add(Tenant(id=1, name="Default"))
            db.commit()
        if not db.get(ChannelAccount, 1):
            db.add(ChannelAccount(id=1, platform_code='SELF', name='官网商城',
                                  category='SELF', commerce_enabled=True))
            db.commit()
        s = settings()
        if s.bootstrap_admin_password and not db.scalar(select(User).where(User.email == s.bootstrap_admin_email)):
            db.add(User(tenant_id=1, username=s.bootstrap_admin_email, email=s.bootstrap_admin_email,
                        password_hash=hash_password(s.bootstrap_admin_password), role="SUPER_ADMIN"))
            db.commit()


@asynccontextmanager
async def lifespan(app):
    startup()
    worker=None
    if settings().foundation_enabled and settings().model_worker_enabled:
        from app.foundation.workers import Worker
        worker=Worker(SessionLocal);worker.start()
    try:
        yield
    finally:
        if worker:worker.stop()
