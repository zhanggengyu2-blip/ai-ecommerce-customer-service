from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import Document, DocumentVersion
from app.services.knowledge import process_version


def create_version(db: Session, tenant_id: int, title: str, content: str,
                   original_key: str | None = None, account_id: int | None = None,
                   platform_code: str | None = None, prepare_only: bool = False):
    document = db.scalar(select(Document).where(Document.tenant_id == tenant_id,
        Document.account_id == account_id, Document.platform_code == platform_code,
        Document.title == title))
    if not document:
        document = Document(tenant_id=tenant_id, account_id=account_id,
                            platform_code=platform_code, title=title)
        db.add(document)
        db.flush()
    version_no = db.scalar(select(func.coalesce(func.max(DocumentVersion.version), 0)).where(DocumentVersion.document_id == document.id)) + 1
    version = DocumentVersion(document_id=document.id, version=version_no, content="",
                              original_key=original_key, status="PROCESSING")
    db.add(version)
    db.flush()
    if prepare_only:
        if not content.strip():
            db.rollback()
            raise HTTPException(422, '文档没有可解析的文本')
        version.content, version.status = content, 'DRAFT'
        db.commit()
        count = 0
    else:
        try:
            count = process_version(db, version, content)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(422, str(exc)) from exc
    return {"document_id": document.id, "version_id": version.id, "version": version_no, "chunks": count}
