"""Explicit migrations. Legacy SQLite adoption checks the frozen schema first."""
from datetime import datetime, timezone
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import sqlite3
from sqlalchemy import create_engine, inspect, text
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models import Base

ROOT = Path(__file__).resolve().parents[2]
HEAD = '20261021_03'


def configuration(engine):
    config = Config(str(ROOT / 'alembic.ini'))
    config.attributes['database_url'] = engine.url.render_as_string(hide_password=False)
    return config


def schema_shape(connection):
    inspector = inspect(connection)
    def shape(name):
        return {
            'columns': {c['name']: (str(c['type']).upper(), bool(c['nullable']), bool(c['primary_key']))
                        for c in inspector.get_columns(name)},
            'uniques': {tuple(u['column_names']) for u in inspector.get_unique_constraints(name)},
            'foreign_keys': {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns']))
                             for f in inspector.get_foreign_keys(name)},
            'indexes': {(tuple(i['column_names']), bool(i['unique'])) for i in inspector.get_indexes(name)},
        }
    return {name: shape(name) for name in inspector.get_table_names() if name != 'alembic_version'}


def baseline_tables(*, current=False):
    engine = create_engine('sqlite://')
    spec = spec_from_file_location('frozen_baseline', ROOT / 'migrations/versions/20261021_01_legacy_baseline.py')
    module = module_from_spec(spec); spec.loader.exec_module(module)
    with engine.begin() as connection:
        if current:
            Base.metadata.create_all(connection)
        else:
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
        tables = schema_shape(connection)
    engine.dispose()
    return tables


def backup_sqlite(engine):
    if engine.dialect.name != 'sqlite' or not engine.url.database or engine.url.database == ':memory:':
        return None
    source = Path(engine.url.database)
    if not source.exists():
        return None
    destination = source.with_name(source.name + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    destination.chmod(0o600)
    return destination


def upgrade(engine, *, adopt_legacy=False):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {'alembic_version'}
    config = configuration(engine)
    if 'alembic_version' in inspector.get_table_names():
        with engine.connect() as connection:
            if connection.scalar(text('SELECT version_num FROM alembic_version')) == HEAD:
                if engine.dialect.name == 'sqlite' and connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone():
                    raise RuntimeError('Foreign-key audit failed; reconcile source data before continuing.')
                return HEAD
    if tables and 'alembic_version' not in inspector.get_table_names():
        if not adopt_legacy:
            raise RuntimeError('Unversioned database: audit and explicitly adopt the legacy schema before migrating.')
        if engine.dialect.name != 'sqlite':
            raise RuntimeError('Legacy adoption requires a separately reviewed database-specific migration.')
        actual = schema_shape(engine)
        current = baseline_tables(current=True)
        frozen = baseline_tables()
        if actual != frozen and actual != current:
            raise RuntimeError('Unrecognized schema; adoption stopped without changing tables or data.')
        backup_sqlite(engine)
        command.stamp(config, HEAD if actual == current else '20261021_01')
    elif tables:
        backup_sqlite(engine)
    command.upgrade(config, 'head')
    with engine.connect() as connection:
        if engine.dialect.name == 'sqlite' and connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Foreign-key audit failed; keep the backup and reconcile source data.')
    return HEAD


def assert_ready(engine):
    inspector = inspect(engine)
    if 'alembic_version' not in inspector.get_table_names():
        raise RuntimeError('Run the foundation database migrations before starting this mode.')
    with engine.connect() as connection:
        version = connection.scalar(text('SELECT version_num FROM alembic_version'))
    if version != HEAD:
        raise RuntimeError('Foundation database migration is not current.')
    with engine.connect() as connection:
        # A foundation runtime must not silently inherit the old global account list.
        count = connection.scalar(text('SELECT COUNT(*) FROM channel_account WHERE tenant_id IS NULL OR entry_code IS NULL'))
        if count:
            raise RuntimeError('Legacy store ownership needs an explicit mapping; no store was guessed or reassigned.')
