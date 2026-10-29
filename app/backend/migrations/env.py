from alembic import context
from sqlalchemy import create_engine, pool
from app.config.settings import settings
from app.models import Base

config = context.config
url = config.attributes.get('database_url') or settings().database_url

def run_offline():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True,
                      dialect_opts={'paramstyle': 'named'}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_online():
    connection = config.attributes.get('connection')
    if connection is not None:
        configure(connection)
    else:
        engine = create_engine(url, poolclass=pool.NullPool)
        with engine.connect() as connection:
            configure(connection)
        engine.dispose()

def configure(connection):
    sqlite = connection.dialect.name == 'sqlite'
    # Batch migrations replace referenced tables. Disable enforcement only on
    # this migration connection, then audit the resulting data before returning.
    previous = connection.exec_driver_sql('PRAGMA foreign_keys').scalar() if sqlite else None
    if sqlite:
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
        connection.commit()
    context.configure(connection=connection, target_metadata=Base.metadata,
                      render_as_batch=sqlite, compare_type=True)
    try:
        with context.begin_transaction():
            context.run_migrations()
        if sqlite and connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Foreign-key audit failed after migration; restore the verified backup.')
    finally:
        if sqlite:
            connection.commit()
            connection.exec_driver_sql('PRAGMA foreign_keys=' + str(previous))

if context.is_offline_mode():
    run_offline()
else:
    run_online()
