from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import ConfigVersion, PromptTemplate


def active_config_row(db: Session, tenant_id: int, kind: str) -> ConfigVersion | None:
    return db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id == tenant_id,
                                                ConfigVersion.kind == kind,
                                                ConfigVersion.status == "PUBLISHED")
                    .order_by(ConfigVersion.version.desc()).limit(1))


def active_config(db: Session, tenant_id: int, kind: str) -> dict:
    row = active_config_row(db, tenant_id, kind)
    return row.value if row else {}


def active_prompt_values(db: Session, tenant_id: int) -> dict[str, str]:
    rows = db.scalars(select(PromptTemplate).where(PromptTemplate.tenant_id == tenant_id)
                      .order_by(PromptTemplate.key)).all()
    if rows:
        return {row.key: row.value for row in rows}
    # Preserve older prompt settings if a deployment creates the new table before
    # running its Alembic data migration.
    legacy = db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id == tenant_id,
        ConfigVersion.kind == "prompt", ConfigVersion.status == "PUBLISHED")
        .order_by(ConfigVersion.version.desc()).limit(1))
    return {key: value for key, value in (legacy.value if legacy else {}).items()
            if isinstance(key, str) and isinstance(value, str)}
