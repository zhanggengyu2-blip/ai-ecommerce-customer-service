"""Tenant-scoped knowledge authoring; only prepared versions become searchable."""
import uuid
from sqlalchemy import select, func
from app.models import KnowledgeCategory, Document, DocumentVersion, Chunk, KnowledgeJob, utcnow
from app.services.knowledge_lifecycle import utc_naive
from . import model_runtime as M
from .reception import writing
from .security import fail, store_for
from .views import iso
from .model_config import job_view
from .ai_schemas import ChunkSettings, PublishInput


def split_text(content, settings):
    rows=[]
    for part in content.split(settings.separator.replace('\\n','\n')):
        start=0
        while start<len(part):
            end=min(start+settings.target_chars,len(part));segment=part[start:end].strip()
            if segment:rows.append(segment)
            if len(rows)>500:fail(422,'TOO_MANY_CHUNKS','切片超过 500 条，请增大分段长度或拆分知识')
            if end==len(part):break
            start=end-settings.overlap_chars
    if not rows:fail(422,'EMPTY_KNOWLEDGE','知识正文不能为空')
    return rows


def category_for(db, tenant_id, ident, *, locked=False):
    query=select(KnowledgeCategory).where(KnowledgeCategory.id==ident,KnowledgeCategory.tenant_id==tenant_id)
    if locked:query=query.with_for_update().execution_options(populate_existing=True)
    row=db.scalar(query)
    if row is None:fail(404,'CATEGORY_NOT_FOUND','知识库不存在')
    return row


def document_for(db, tenant_id, ident, *, locked=False):
    query=select(Document).where(Document.id==ident,Document.tenant_id==tenant_id,
        Document.account_id==store_for(db,tenant_id).id)
    if locked:query=query.with_for_update().execution_options(populate_existing=True)
    row=db.scalar(query)
    if row is None:fail(404,'DOCUMENT_NOT_FOUND','知识不存在')
    return row


def active_version(db, doc, now=None):
    now=utc_naive(now)
    version=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,
        DocumentVersion.status=='PUBLISHED',
        (DocumentVersion.effective_from.is_(None))|(DocumentVersion.effective_from<=now))
        .order_by(DocumentVersion.version.desc()).limit(1))
    if not doc.is_active or not version or (version.effective_until and utc_naive(version.effective_until)<=now):return None
    return version


def version_view(db, version, *, include_content=False):
    if not version:return None
    result={'id':version.id,'version':version.version,'status':version.status,'purpose':version.purpose,
        'effective_from':iso(version.effective_from),'effective_until':iso(version.effective_until),
        'created_at':iso(version.created_at),'published_at':iso(version.published_at),'error':version.error,
        'settings':version.chunk_settings or ChunkSettings().model_dump(),
        'chunk_count':db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_version_id==version.id))}
    if include_content:
        result['content']=version.content
        result['chunks']=[{'id':c.id,'ordinal':c.ordinal,'content':c.content} for c in db.scalars(
            select(Chunk).where(Chunk.document_version_id==version.id).order_by(Chunk.ordinal)).all()]
    return result


def document_view(db, doc, *, detail=False):
    latest=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id).order_by(DocumentVersion.version.desc()).limit(1))
    published=db.get(DocumentVersion,doc.current_version_id) if doc.current_version_id else None
    usable=active_version(db,doc)
    state='已停用' if not doc.is_active else '已发布' if usable else '未发布'
    if not usable and doc.is_active and published:
        state='未生效' if published.effective_from and utc_naive(published.effective_from)>utc_naive() else '已过期'
    job=db.scalar(select(KnowledgeJob).where(KnowledgeJob.tenant_id==doc.tenant_id,
        KnowledgeJob.document_version_id==latest.id).order_by(KnowledgeJob.created_at.desc()).limit(1)) if latest else None
    result={'id':doc.id,'title':doc.title,'category_id':doc.category_id,'enabled':doc.is_active,'revision':doc.revision,
        'updated_at':iso(doc.updated_at),'state':state,'active_version_id':usable.id if usable else None,
        'published':version_view(db,published,include_content=detail),
        'candidate':version_view(db,latest,include_content=detail) if latest and latest.status!='PUBLISHED' else None,
        'operation':job_view(job) if job else None}
    if detail:
        result['versions']=[version_view(db,v) for v in db.scalars(select(DocumentVersion)
            .where(DocumentVersion.document_id==doc.id,DocumentVersion.status=='PUBLISHED').order_by(DocumentVersion.version.desc())).all()]
        if job and latest and latest.status!='PUBLISHED':result['candidate_metadata']=job.source_revisions or {}
    return result


def publish(db, identity, body, *, restore_of=None):
    chunks=split_text(body.content,body.settings)
    with writing(db,identity):
        M.lock_tenant(db,identity.tenant_id)
        model=M.current_locked(db,identity.tenant_id)
        if not model or model.value.get('schema_version')!=2:fail(409,'MODELS_REQUIRED','请先完成三个模型的配置')
        M.runtime(identity.tenant_id,model.value)
        category_for(db,identity.tenant_id,body.category_id,locked=True)
        if body.document_id:
            doc=document_for(db,identity.tenant_id,body.document_id,locked=True)
            if doc.revision!=body.expected_revision:fail(409,'DOCUMENT_CHANGED','知识已被修改，请刷新后再发布')
        else:
            if body.expected_revision!=0:fail(409,'DOCUMENT_CHANGED','新知识的初始版本应为 0')
            if db.scalar(select(Document.id).where(Document.tenant_id==identity.tenant_id,
                    Document.account_id==store_for(db,identity.tenant_id).id,Document.title==body.title).with_for_update()):
                fail(409,'DOCUMENT_EXISTS','本店已有同名知识，请在原知识上编辑')
            doc=Document(tenant_id=identity.tenant_id,account_id=store_for(db,identity.tenant_id).id,
                title=body.title,category_id=body.category_id,updated_by_user_id=identity.user_id)
            db.add(doc);db.flush()
        pending=db.scalar(select(KnowledgeJob.id).join(DocumentVersion,KnowledgeJob.document_version_id==DocumentVersion.id)
            .where(DocumentVersion.document_id==doc.id,KnowledgeJob.status.in_(('PENDING','RUNNING'))).with_for_update())
        if pending:fail(409,'PUBLISH_RUNNING','这篇知识正在发布，请等待处理完成')
        last=db.scalar(select(DocumentVersion).where(DocumentVersion.document_id==doc.id)
            .order_by(DocumentVersion.version.desc()).limit(1).with_for_update())
        version=DocumentVersion(document_id=doc.id,version=(last.version if last else 0)+1,status='PROCESSING',
            content=body.content,purpose=body.purpose or '',chunk_settings=body.settings.model_dump(),
            effective_from=utc_naive(body.effective_from) if body.effective_from else None,
            effective_until=utc_naive(body.effective_until) if body.effective_until else None,auto_revert_on_expiry=False)
        db.add(version);db.flush()
        doc.revision+=1;doc.updated_by_user_id=identity.user_id;doc.updated_at=utcnow()
        job=KnowledgeJob(id=str(uuid.uuid4()),tenant_id=identity.tenant_id,kind='PUBLISH',document_version_id=version.id,
            created_by_user_id=identity.user_id,expected_revision=doc.revision,based_on_config=model.version,
            source_revisions={'title':body.title,'category_id':body.category_id,
                              'generate_purpose':body.purpose is None or (not doc.current_version_id and not (body.purpose or '').strip()),
                              'restore_of':restore_of})
        db.add(job);db.flush()
        result={'document_id':doc.id,'revision':doc.revision,'job':job_view(job),'chunk_count':len(chunks)}
    return result


def restore(db, identity, ident, body):
    doc=document_for(db,identity.tenant_id,ident)
    previous=db.scalars(select(DocumentVersion).where(DocumentVersion.document_id==doc.id,
        DocumentVersion.status=='PUBLISHED').order_by(DocumentVersion.version.desc()).limit(2)).all()
    if len(previous)<2:fail(409,'NO_PREVIOUS_VERSION','没有上一已发布版本可以恢复')
    source=previous[1]
    request=PublishInput(document_id=doc.id,expected_revision=body.expected_revision,category_id=doc.category_id,
        title=doc.title,content=source.content,purpose=source.purpose,
        settings=source.chunk_settings or ChunkSettings().model_dump(),
        effective_from=iso(source.effective_from),effective_until=iso(source.effective_until))
    return publish(db,identity,request,restore_of=source.id)


def active_documents(db, tenant_id, category_id=None):
    where=[Document.tenant_id==tenant_id,Document.account_id==store_for(db,tenant_id).id,Document.is_active.is_(True)]
    if category_id:where.append(Document.category_id==category_id)
    result=[]
    for doc in db.scalars(select(Document).where(*where).order_by(Document.id)).all():
        version=active_version(db,doc)
        if version:
            category=category_for(db,tenant_id,doc.category_id)
            result.append((doc,version,category))
    return result
