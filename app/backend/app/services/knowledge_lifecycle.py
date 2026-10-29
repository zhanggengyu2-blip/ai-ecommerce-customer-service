"""Knowledge activation is evaluated at query time; no scheduler is required."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import DocumentVersion


def utc_naive(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def active_version(db: Session, document_id: int, now: datetime | None = None) -> DocumentVersion | None:
    moment = utc_naive(now)
    versions = db.scalars(select(DocumentVersion).where(
        DocumentVersion.document_id == document_id,
        DocumentVersion.status == 'PUBLISHED',
        (DocumentVersion.effective_from.is_(None)) | (DocumentVersion.effective_from <= moment),
    )).all()
    if not versions:
        return None
    newest = max(versions, key=lambda row: (utc_naive(row.effective_from or row.published_at or row.created_at), row.id))
    if newest.effective_until and utc_naive(newest.effective_until) <= moment:
        if not newest.auto_revert_on_expiry:
            return None
        previous = db.scalars(select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version < newest.version,
            DocumentVersion.status.in_(('PUBLISHED', 'ARCHIVED')),
            (DocumentVersion.effective_from.is_(None)) | (DocumentVersion.effective_from <= moment),
            (DocumentVersion.effective_until.is_(None)) | (DocumentVersion.effective_until > moment),
        ).order_by(DocumentVersion.version.desc())).first()
        return previous
    return newest
