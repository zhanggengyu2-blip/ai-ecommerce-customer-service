from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.config.settings import settings
from app.models import Base

engine = create_engine(settings().database_url, pool_pre_ping=True, connect_args={"check_same_thread": False} if settings().database_url.startswith("sqlite") else {})
if settings().foundation_enabled and engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def foundation_sqlite(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=15000')
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
