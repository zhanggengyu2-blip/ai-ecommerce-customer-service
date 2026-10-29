from fastapi import APIRouter
import logging
import re
import uuid
from datetime import date
from pathlib import Path
from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
import httpx
from sqlalchemy import func, select, delete
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.core.database import get_db
from app.models import User, Document, DocumentVersion, Chunk, AuditLog, utcnow
from app.core.security import role_required
from app.services.knowledge import (parse_file, save_original, delete_original, search_headers,
                                    index_chunks, retrieve, reindex_published_knowledge)
from app.services.knowledge_lifecycle import active_version, utc_naive
from app.services.knowledge_editor import suggest_chunks
from app.services.runtime_config import active_prompt_values
from app.providers.ai import embed, ProviderError
from app.core.rate_limit import check_rate_limit
from app.services.documents import create_version
from app.schemas.knowledge import FAQRequest, ChunkSuggestion, ChunkSave, PublicationRequest
from app.services.accounts import PLATFORMS, require_account
from app.services.runtime_config import active_config

router = APIRouter(tags=["knowledge"])


@router.post("/api/admin/knowledge/reindex")
def reindex_knowledge(user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER")),
                      db: Session = Depends(get_db)):
    check_rate_limit(f"knowledge-reindex:{user.id}", 2, 300)
    if not settings().opensearch_url:
        raise HTTPException(503, "尚未配置 OpenSearch，无法同步知识索引")
    try:
        result = reindex_published_knowledge(db, user.tenant_id)
    except Exception as exc:
        db.rollback()
        logging.exception("Knowledge index synchronization failed for tenant %s", user.tenant_id)
        raise HTTPException(503, "OpenSearch 同步失败，请查看后端日志后重试") from exc

    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}",
                    action="knowledge_reindex", target="opensearch:knowledge_chunks",
                    detail=result))
    db.commit()
    return result


@router.get('/api/admin/knowledge/test-search')
def test_search(q: str, account_id: int, type: str | None = None, category: str | None = None,
                user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER')),
                db: Session = Depends(get_db)):
    require_account(db, account_id, user)
    if not q.strip() or len(q) > 500:
        raise HTTPException(422, '请输入 1–500 字的测试问题')
    filters = {key: value for key, value in {'type': type, 'category': category}.items() if value}
    matches = retrieve(db, user.tenant_id, q.strip(), account_id, filters)
    return [{'chunk_id': chunk.id, 'document_version_id': chunk.document_version_id,
             'section': chunk.section, 'content': chunk.content, 'tags': chunk.tags or {},
             'source': source, 'score': score} for chunk, source, score in matches[:10]]


@router.get("/api/admin/documents")
def documents(account_id: int | None = None, user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER", "VIEWER")), db: Session = Depends(get_db)):
    query = select(Document).where(Document.tenant_id == user.tenant_id)
    if account_id is not None:
        require_account(db, account_id, user)
        query = query.where(Document.account_id == account_id)
    rows = db.scalars(query.order_by(Document.id.desc())).all()
    return [{"id": d.id, "title": d.title, "account_id": d.account_id,
             "platform_code": d.platform_code,
             "is_active": d.is_active,
             "current_version_id": active.id if (active := active_version(db, d.id)) else None} for d in rows]


def check_scope(db, user, account_id, platform_code):
    if account_id is not None and platform_code is not None:
        raise HTTPException(422, '账号和平台范围不能同时指定')
    if account_id is not None:
        require_account(db, account_id, user)
    if platform_code is not None and platform_code not in PLATFORMS:
        raise HTTPException(422, '不支持的平台')


@router.post("/api/admin/documents/upload")
async def upload_document(file: UploadFile = File(...), account_id: int | None = Form(default=None),
                          platform_code: str | None = Form(default=None),
                          document_id: int | None = Form(default=None),
                          prepare_only: bool = Form(default=False),
                          user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER")),
                          db: Session = Depends(get_db)):
    if document_id is not None:
        document = db.get(Document, document_id)
        if not document or document.tenant_id != user.tenant_id:
            raise HTTPException(404, 'Document not found')
        account_id, platform_code = document.account_id, document.platform_code
    check_scope(db, user, account_id, platform_code)
    check_rate_limit(f"upload:{user.id}", 20, 3600)
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(422, "Filename required")
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/{name}"
    save_original(key, data, file.content_type or "application/octet-stream")
    if document_id is not None:
        result = create_version(db, user.tenant_id, document.title, parse_file(name, data), key,
                                account_id, platform_code, prepare_only=prepare_only)
    elif settings().async_ingestion and not prepare_only:
        document = db.scalar(select(Document).where(Document.tenant_id == user.tenant_id,
            Document.account_id == account_id, Document.platform_code == platform_code, Document.title == name))
        if not document:
            document = Document(tenant_id=user.tenant_id, account_id=account_id,
                                platform_code=platform_code, title=name)
            db.add(document)
            db.flush()
        version_no = db.scalar(select(func.coalesce(func.max(DocumentVersion.version), 0)).where(DocumentVersion.document_id == document.id)) + 1
        version = DocumentVersion(document_id=document.id, version=version_no, original_key=key, status="PROCESSING")
        db.add(version)
        db.commit()
        from app.tasks.ingestion import process_document_task
        process_document_task.delay(version.id, name)
        result = {"document_id": document.id, "version_id": version.id, "version": version_no, "status": "PROCESSING"}
    else:
        result = create_version(db, user.tenant_id, name, parse_file(name, data), key,
                                account_id, platform_code, prepare_only=prepare_only)
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="document_upload",
                    target=f"document:{result['document_id']}", detail={"version_id": result["version_id"]}))
    db.commit()
    return result


@router.post("/api/admin/faq")
def create_faq(body: FAQRequest, user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER")), db: Session = Depends(get_db)):
    title, account_id, platform_code = body.title, body.account_id, body.platform_code
    if body.document_id is not None:
        document = db.get(Document, body.document_id)
        if not document or document.tenant_id != user.tenant_id:
            raise HTTPException(404, 'Document not found')
        title, account_id, platform_code = document.title, document.account_id, document.platform_code
    check_scope(db, user, account_id, platform_code)
    result = create_version(db, user.tenant_id, title, f"问：{body.question}\n答：{body.answer}",
                            account_id=account_id, platform_code=platform_code)
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="faq_create",
                    target=f"document:{result['document_id']}", detail={"version_id": result["version_id"]}))
    db.commit()
    return result


@router.get("/api/admin/documents/{document_id}/versions")
def versions(document_id: int, user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER", "VIEWER")),
             db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Document not found")
    rows = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id).order_by(DocumentVersion.version.desc())).all()
    active = active_version(db, d.id)
    now = utc_naive()
    result = []
    for v in rows:
        chunks = db.scalars(select(Chunk).where(Chunk.document_version_id == v.id)).all()
        result.append({"id": v.id, "version": v.version, "status": v.status, "error": v.error,
                       "chunk_count": len(chunks),
                       "vectorized_chunks": sum(c.embedding is not None for c in chunks),
                       "effective_from": utc_naive(v.effective_from).isoformat() + 'Z' if v.effective_from else None,
                       "effective_until": utc_naive(v.effective_until).isoformat() + 'Z' if v.effective_until else None,
                       "auto_revert_on_expiry": v.auto_revert_on_expiry,
                       "activation_state": 'ACTIVE' if active and active.id == v.id else
                           'SCHEDULED' if v.status == 'PUBLISHED' and v.effective_from and utc_naive(v.effective_from) > now else
                           'INACTIVE',
                       "created_at": v.created_at.isoformat()})
    return result


@router.put('/api/admin/documents/{document_id}/active')
def set_document_active(document_id: int, active: bool = Body(embed=True),
                        user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER')),
                        db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document or document.tenant_id != user.tenant_id:
        raise HTTPException(404, 'Document not found')
    document.is_active = active
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f'staff:{user.id}', action='knowledge_document_active',
                    target=f'document:{document.id}', detail={'active': active}))
    db.commit()
    return {'id': document.id, 'is_active': document.is_active}


@router.delete('/api/admin/documents/{document_id}')
def delete_document(document_id: int,
                    user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER')),
                    db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document or document.tenant_id != user.tenant_id:
        raise HTTPException(404, 'Document not found')
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)).all()
    original_keys = [version.original_key for version in versions if version.original_key]
    search_url = settings().opensearch_url
    if search_url:
        try:
            response = httpx.post(search_url.rstrip('/') + '/knowledge_chunks/_delete_by_query?refresh=true',
                                  headers=search_headers(), json={'query': {'term': {'document_id': document.id}}},
                                  timeout=15)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(503, 'OpenSearch index cleanup failed; document was not deleted') from exc
    for version in versions:
        db.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
    for version in versions:
        db.delete(version)
    db.delete(document)
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f'staff:{user.id}', action='knowledge_document_delete',
                    target=f'document:{document_id}', detail={'versions': len(versions)}))
    db.commit()
    for key in original_keys:
        try:
            delete_original(key)
        except HTTPException:
            logging.getLogger(__name__).exception('Failed to remove original knowledge file %s', key)
    return {'id': document_id, 'deleted': True, 'versions_deleted': len(versions)}


@router.get("/api/admin/versions/{version_id}/chunks")
def preview_chunks(version_id: int, user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER", "VIEWER")),
                   db: Session = Depends(get_db)):
    v = db.get(DocumentVersion, version_id)
    d = db.get(Document, v.document_id) if v else None
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Version not found")
    return [{"id": c.id, "ordinal": c.ordinal, "section": c.section, "content": c.content,
             "tags": c.tags or {},
             "has_embedding": c.embedding is not None} for c in db.scalars(select(Chunk).where(Chunk.document_version_id == v.id).order_by(Chunk.ordinal)).all()]


def editable_version(db, version_id: int, tenant_id: int):
    version = db.get(DocumentVersion, version_id)
    document = db.get(Document, version.document_id) if version else None
    if not document or document.tenant_id != tenant_id:
        raise HTTPException(404, 'Version not found')
    if version.status != 'DRAFT':
        raise HTTPException(409, 'Only draft versions can be edited')
    return version, document


@router.post('/api/admin/versions/{version_id}/chunks/suggest')
def suggest_version_chunks(version_id: int, body: ChunkSuggestion,
                           user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER')),
                           db: Session = Depends(get_db)):
    version, _ = editable_version(db, version_id, user.tenant_id)
    if body.strategy == 'ai':
        check_rate_limit(f'knowledge-ai-suggest:{user.id}', 30, 3600)
    prompts = active_prompt_values(db, user.tenant_id)
    return suggest_chunks(version.content, body.strategy, body.target_chars,
                          instruction=prompts.get('knowledge_chunking_instruction'),
                          overlap_chars=body.overlap_chars)


@router.put('/api/admin/versions/{version_id}/chunks')
def save_version_chunks(version_id: int, body: ChunkSave,
                        user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER')),
                        db: Session = Depends(get_db)):
    version, document = editable_version(db, version_id, user.tenant_id)
    normalized_source = re.sub(r'\s+', ' ', version.content).strip()
    for item in body.chunks:
        if re.sub(r'\s+', ' ', item.content).strip() not in normalized_source:
            raise HTTPException(422, '切片内容必须来自文档原文；修改规则请上传新版本')
        if len(item.tags) > 10 or any(len(k) > 32 or len(v) > 100 for k, v in item.tags.items()):
            raise HTTPException(422, '切片标签过多或过长')
        for key in ('valid_from', 'valid_until'):
            if item.tags.get(key):
                try:
                    date.fromisoformat(item.tags[key])
                except ValueError as exc:
                    raise HTTPException(422, f'{key} 应为 YYYY-MM-DD') from exc
        if (item.tags.get('valid_from') and item.tags.get('valid_until') and
                item.tags['valid_until'] < item.tags['valid_from']):
            raise HTTPException(422, '切片标签失效日期不能早于生效日期')
    db.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
    db.add_all(Chunk(tenant_id=document.tenant_id, account_id=document.account_id,
                     platform_code=document.platform_code, document_version_id=version.id,
                     ordinal=index, section=item.section, content=item.content.strip(), tags=item.tags)
               for index, item in enumerate(body.chunks))
    version.error = None
    db.commit()
    return {'chunks': len(body.chunks), 'vectorized_chunks': 0}


@router.post('/api/admin/versions/{version_id}/embed')
def embed_version(version_id: int, user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER')),
                  db: Session = Depends(get_db)):
    check_rate_limit(f'knowledge-embed:{user.id}', 60, 3600)
    version, _ = editable_version(db, version_id, user.tenant_id)
    chunks = db.scalars(select(Chunk).where(Chunk.document_version_id == version.id).order_by(Chunk.ordinal)).all()
    if not chunks:
        raise HTTPException(409, '请先保存切片')
    try:
        vectors = embed([chunk.content for chunk in chunks], active_config(db, user.tenant_id, "model"))
    except ProviderError as exc:
        raise HTTPException(503, f'Embedding 不可用：{exc.code}') from exc
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector
    version.error = None
    db.commit()
    return {'chunks': len(chunks), 'vectorized_chunks': len(chunks)}


@router.post("/api/admin/versions/{version_id}/retry")
def retry_version(version_id: int, user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER")),
                  db: Session = Depends(get_db)):
    v = db.get(DocumentVersion, version_id)
    d = db.get(Document, v.document_id) if v else None
    if not d or d.tenant_id != user.tenant_id or v.status != "FAILED" or not v.original_key:
        raise HTTPException(409, "Version cannot be retried")
    v.status, v.error = "PROCESSING", None
    db.commit()
    from app.tasks.ingestion import process_document_task
    process_document_task.delay(v.id, Path(v.original_key).name)
    return {"status": "PROCESSING"}


@router.post("/api/admin/versions/{version_id}/publish")
def publish(version_id: int, body: PublicationRequest | None = None,
            user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER")), db: Session = Depends(get_db)):
    v = db.get(DocumentVersion, version_id)
    d = db.get(Document, v.document_id) if v else None
    if not d or d.tenant_id != user.tenant_id:
        raise HTTPException(404, "Version not found")
    if v.status != "DRAFT":
        raise HTTPException(409, "Only drafts can be published")
    version_chunks = db.scalars(select(Chunk).where(Chunk.document_version_id == v.id)).all()
    if not version_chunks:
        raise HTTPException(409, '请先保存切片')
    body = body or PublicationRequest()
    if not body.allow_lexical_only and any(chunk.embedding is None for chunk in version_chunks):
        raise HTTPException(409, '部分切片尚未向量化；请先向量化或明确允许仅关键词发布')
    now = utc_naive()
    begins = utc_naive(body.effective_from) if body.effective_from else now
    ends = utc_naive(body.effective_until) if body.effective_until else None
    if ends and ends <= begins:
        raise HTTPException(422, '失效时间必须晚于生效时间')
    if ends and ends <= now:
        raise HTTPException(422, '失效时间必须晚于当前时间')
    if body.auto_revert_on_expiry:
        if not ends:
            raise HTTPException(422, '启用到期回退必须设置失效时间')
        previous_exists = db.scalar(select(DocumentVersion.id).where(
            DocumentVersion.document_id == d.id,
            DocumentVersion.version < v.version,
            DocumentVersion.status.in_(('PUBLISHED', 'ARCHIVED')),
        ).limit(1))
        if not previous_exists:
            raise HTTPException(422, '没有可回退的历史发布版本')
    try:
        index_chunks(db, v, d)
    except Exception as exc:
        raise HTTPException(503, f"Search index unavailable: {exc}") from exc
    old = active_version(db, d.id, now)
    others = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id,
                                                       DocumentVersion.status == 'PUBLISHED')).all()
    for other in others:
        if begins <= now or (other.effective_from and utc_naive(other.effective_from) > now):
            other.status = 'ARCHIVED'
    v.status, v.published_at = 'PUBLISHED', utcnow()
    v.effective_from, v.effective_until = begins, ends
    v.auto_revert_on_expiry = body.auto_revert_on_expiry
    if begins <= now:
        d.current_version_id = v.id
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="knowledge_publish",
                    target=f"document:{d.id}", detail={"version_id": v.id, "previous_version_id": old.id if old else None}))
    db.commit()
    return {"status": "SCHEDULED" if begins > now else "PUBLISHED", "document_id": d.id, "version_id": v.id}


@router.post('/api/admin/versions/{version_id}/rollback')
def rollback_version(version_id: int, user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER')),
                     db: Session = Depends(get_db)):
    version = db.get(DocumentVersion, version_id)
    document = db.get(Document, version.document_id) if version else None
    if not document or document.tenant_id != user.tenant_id or version.status not in ('PUBLISHED', 'ARCHIVED'):
        raise HTTPException(404, 'Published historical version not found')
    if not db.scalar(select(Chunk.id).where(Chunk.document_version_id == version.id).limit(1)):
        raise HTTPException(409, 'Historical version has no chunks')
    try:
        index_chunks(db, version, document)
    except Exception as exc:
        raise HTTPException(503, f'Search index unavailable: {exc}') from exc
    for other in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id,
                                                            DocumentVersion.status == 'PUBLISHED')).all():
        if other.id != version.id:
            other.status = 'ARCHIVED'
    version.status, version.effective_from, version.effective_until = 'PUBLISHED', utc_naive(), None
    document.current_version_id = version.id
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f'staff:{user.id}', action='knowledge_rollback',
                    target=f'document:{document.id}', detail={'version_id': version.id}))
    db.commit()
    return {'status': 'PUBLISHED', 'document_id': document.id, 'version_id': version.id}
