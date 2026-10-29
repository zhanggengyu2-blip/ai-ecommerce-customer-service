import json
from pathlib import Path
from fastapi import APIRouter, Depends, File, UploadFile, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.models import (KnowledgeCategory, Document, DocumentVersion, KnowledgeJob, Conversation, ChatThread,
                        ConfigVersion, QuestionTrace, QuestionTraceNode, QuestionTracePayload, utcnow)
from . import ai_schemas as S, model_config as C, model_runtime as M, knowledge as K, retrieval as Q, providers as P
from .security import Identity, staff, fail, store_for
from .reception import writing, conversation_for
from .trace_store import Trace, conversation_usage
from .views import iso

router=APIRouter(tags=['模型与知识'])


@router.get('/api/admin/settings/models')
def models(identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    return C.configuration(db,identity)


@router.post('/api/admin/settings/models/check')
def check_model(body:S.ModelCheck,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    check_rate_limit('model-check:'+identity.session_id,20,60)
    return C.verify_role(db,identity,body)


@router.put('/api/admin/settings/models')
def save_models(body:S.ModelsSave,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    check_rate_limit('model-save:'+identity.session_id,10,60)
    return C.save_models(db,identity,body)


@router.get('/api/admin/settings/retrieval')
def retrieval(identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    return C.retrieval_config(db,identity.tenant_id)


@router.put('/api/admin/settings/retrieval')
def save_retrieval(body:S.RetrievalSave,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    return C.save_retrieval(db,identity,body)


@router.get('/api/admin/settings/reception')
def reception(identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    row=M.current(db,identity.tenant_id,'reception')
    return {'enabled':bool(row and row.value.get('enabled')),'version':row.version if row else 0}


@router.put('/api/admin/settings/reception')
def set_reception(body:S.EnableReception,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    with writing(db,identity):
        M.lock_tenant(db,identity.tenant_id);old=M.current_locked(db,identity.tenant_id,'reception')
        if (old.version if old else 0)!=body.expected_version:fail(409,'CONFIG_CHANGED','接待设置已被修改，请刷新')
        if body.enabled:
            config=M.current_locked(db,identity.tenant_id)
            if not config:fail(409,'MODELS_REQUIRED','请先完成三个模型的配置')
            roles=M.runtime(identity.tenant_id,config.value)
            docs,_=Q.snapshot(db,identity.tenant_id,roles)
            if not any(d['chunks'] for d in docs):fail(409,'KNOWLEDGE_REQUIRED','请先发布至少一篇当前有效、可检索的知识')
        else:
            # Policy and reception state change together. Existing human owners remain.
            threads=db.scalars(select(ChatThread).where(ChatThread.tenant_id==identity.tenant_id)
                .order_by(ChatThread.id).with_for_update().execution_options(populate_existing=True)).all()
            for thread in threads:
                if not thread.active_conversation_id:continue
                c=db.scalar(select(Conversation).where(Conversation.id==thread.active_conversation_id,
                    Conversation.tenant_id==identity.tenant_id,Conversation.thread_id==thread.id)
                    .with_for_update().execution_options(populate_existing=True))
                if c and c.status=='AI_ACTIVE':
                    c.status='WAITING_USER';c.reception_epoch+=1;c.revision+=1;thread.revision+=1
                    c.handoff_requested_at=utcnow();c.ever_handoff_requested=True;c.handoff_reason='店铺关闭自动接待'
        row=ConfigVersion(tenant_id=identity.tenant_id,kind='reception',version=M.next_version(db,identity.tenant_id,'reception'),
            status='PUBLISHED',value={'enabled':body.enabled})
        if old:old.status='ARCHIVED'
        db.add(row);db.flush();result={'enabled':body.enabled,'version':row.version}
    return result


def category_view(db,row):
    return {'id':row.id,'name':row.name,'description':row.description,'revision':row.revision,
        'document_count':db.scalar(select(func.count()).select_from(Document).where(Document.category_id==row.id,
            Document.tenant_id==row.tenant_id))}


@router.get('/api/admin/knowledge-categories')
def categories(identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    return {'items':[category_view(db,c) for c in db.scalars(select(KnowledgeCategory).where(
        KnowledgeCategory.tenant_id==identity.tenant_id).order_by(KnowledgeCategory.id)).all()]}


@router.post('/api/admin/knowledge-categories')
def create_category(body:S.CategoryInput,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    with writing(db,identity):
        M.lock_tenant(db,identity.tenant_id)
        row=KnowledgeCategory(tenant_id=identity.tenant_id,name=body.name,description=body.description,
            created_by_user_id=identity.user_id,updated_by_user_id=identity.user_id)
        db.add(row);db.flush();result=category_view(db,row)
    return result


@router.patch('/api/admin/knowledge-categories/{ident}')
def edit_category(ident:int,body:S.CategoryEdit,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    with writing(db,identity):
        M.lock_tenant(db,identity.tenant_id);row=K.category_for(db,identity.tenant_id,ident,locked=True)
        if row.revision!=body.expected_revision:fail(409,'CATEGORY_CHANGED','知识库已被修改，请刷新')
        row.name,row.description=body.name,body.description;row.revision+=1
        row.updated_by_user_id=identity.user_id
        result=category_view(db,row)
    return result


@router.delete('/api/admin/knowledge-categories/{ident}')
def remove_category(ident:int,expected_revision:int=Query(ge=1),identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    with writing(db,identity):
        M.lock_tenant(db,identity.tenant_id);row=K.category_for(db,identity.tenant_id,ident,locked=True)
        if row.revision!=expected_revision:fail(409,'CATEGORY_CHANGED','知识库已被修改，请刷新')
        if db.scalar(select(Document.id).where(Document.category_id==ident,Document.tenant_id==identity.tenant_id).limit(1).with_for_update()):
            fail(409,'CATEGORY_IN_USE','知识库内还有知识，不能删除')
        db.delete(row)
    return {'ok':True}


@router.get('/api/admin/documents')
def documents(page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),keyword:str='',category_id:int|None=None,
              identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    where=[Document.tenant_id==identity.tenant_id,Document.account_id==store_for(db,identity.tenant_id).id]
    if keyword.strip():where.append(Document.title.contains(keyword.strip(),autoescape=True))
    if category_id:
        K.category_for(db,identity.tenant_id,category_id);where.append(Document.category_id==category_id)
    total=db.scalar(select(func.count()).select_from(Document).where(*where))
    rows=db.scalars(select(Document).where(*where).order_by(Document.updated_at.desc(),Document.id.desc())
        .offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[K.document_view(db,d) for d in rows],'total':total,'page':page,'page_size':page_size}


@router.get('/api/admin/documents/{ident}')
def document(ident:int,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    return K.document_view(db,K.document_for(db,identity.tenant_id,ident),detail=True)


@router.post('/api/admin/knowledge/upload-text')
async def upload(file:UploadFile=File(...),identity:Identity=Depends(staff)):
    if Path(file.filename or '').suffix.lower() not in {'.md','.markdown','.txt','.csv','.tsv','.json','.yaml','.yml','.xml','.log'}:
        fail(415,'TEXT_FILE_REQUIRED','请上传 MD、TXT、CSV、TSV、JSON、YAML、XML 或 LOG 纯文本文件')
    data=await file.read(2*1024*1024+1);await file.close()
    if len(data)>2*1024*1024:fail(422,'FILE_TOO_LARGE','文件不能超过 2 MB')
    try:content=data.decode('utf-8-sig')
    except UnicodeDecodeError:fail(422,'INVALID_ENCODING','请使用 UTF-8 编码的纯文本文件')
    if not content.strip() or '\0' in content:fail(422,'INVALID_TEXT','文件不是有效的知识正文')
    return {'title':Path(file.filename).stem[:255],'content':content}


@router.post('/api/admin/knowledge/previews')
def preview(body:S.PreviewInput,identity:Identity=Depends(staff)):
    return {'chunks':[{'ordinal':i,'content':text} for i,text in enumerate(K.split_text(body.content,body.settings),1)]}


@router.post('/api/admin/documents/publish')
def publish(body:S.PublishInput,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    return K.publish(db,identity,body)


@router.patch('/api/admin/documents/{ident}')
def toggle_document(ident:int,body:S.DocumentToggle,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    with writing(db,identity):
        M.lock_tenant(db,identity.tenant_id);doc=K.document_for(db,identity.tenant_id,ident,locked=True)
        if doc.revision!=body.expected_revision:fail(409,'DOCUMENT_CHANGED','知识已被修改，请刷新')
        doc.is_active=body.enabled;doc.revision+=1;doc.updated_at=utcnow();doc.updated_by_user_id=identity.user_id
        result=K.document_view(db,doc)
    return result


@router.post('/api/admin/documents/{ident}/restore-previous')
def restore(ident:int,body:S.Restore,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    return K.restore(db,identity,ident,body)


@router.get('/api/admin/knowledge/jobs/{ident}')
def operation(ident:str,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    job=db.scalar(select(KnowledgeJob).where(KnowledgeJob.id==ident,KnowledgeJob.tenant_id==identity.tenant_id))
    if not job:fail(404,'JOB_NOT_FOUND','处理记录不存在')
    return C.job_view(job)


@router.post('/api/admin/recall-tests')
def recall(body:S.Recall,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    check_rate_limit('recall:'+identity.session_id,30,60)
    config=M.current(db,identity.tenant_id)
    if not config:fail(409,'MODELS_REQUIRED','请先配置模型')
    roles=M.runtime(identity.tenant_id,config.value)
    if body.category_id:K.category_for(db,identity.tenant_id,body.category_id)
    documents,rag=Q.snapshot(db,identity.tenant_id,roles,body.category_id)
    trace=Trace(db.get_bind(),tenant_id=identity.tenant_id,account_id=store_for(db,identity.tenant_id).id,
        user_id=identity.user_id,kind='recall_test',query=body.query,config_versions={'model':config.version,'rag':rag['version']},
        secrets=[r['api_key'] for r in roles.values()])
    try:
        routed=Q.route(body.query,[],documents,roles['dialogue'],trace)
        results=Q.retrieve(routed.query,documents,roles,trace,rag,routed.document_ids)
        trace.finish(outcome='RETRIEVED',route='KNOWLEDGE',context_sources={'knowledge':results})
        return {'items':results,'trace_id':trace.id,'settings':rag,'query':routed.query,'score_kind':'rerank_relevance'}
    except P.ProviderError as exc:
        trace.finish(status='FAILED',outcome='FAILED',error=exc.code)
        fail(502,'RECALL_FAILED','召回测试未完成，无法确认 Score 阈值',trace_id=trace.id,provider_code=exc.code)


@router.get('/api/agent/conversations/{ident}/usage')
def usage(ident:int,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    conversation_for(db,identity,ident)
    return conversation_usage(db,identity.tenant_id,ident)


@router.get('/api/admin/traces')
def traces(page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),kind:str='',conversation_id:int|None=None,
           identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    where=[QuestionTrace.tenant_id==identity.tenant_id,QuestionTrace.account_id==store_for(db,identity.tenant_id).id]
    if kind:where.append(QuestionTrace.kind==kind)
    if conversation_id is not None:where.append(QuestionTrace.conversation_id==conversation_id)
    total=db.scalar(select(func.count()).select_from(QuestionTrace).where(*where))
    rows=db.scalars(select(QuestionTrace).where(*where).order_by(QuestionTrace.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[trace_view(t) for t in rows],'total':total,'page':page,'page_size':page_size}


def trace_view(t):
    return {k:getattr(t,k) for k in ('trace_id','kind','conversation_id','query','route','status','outcome',
        'model','handoff','fallback','capture_complete','final_reply','error','config_versions')}|{'started_at':iso(t.started_at),'latency_ms':t.latency_ms}


@router.get('/api/admin/traces/{ident}')
def trace_detail(ident:str,identity:Identity=Depends(staff),db:Session=Depends(get_db)):
    row=db.scalar(select(QuestionTrace).where(QuestionTrace.trace_id==ident,QuestionTrace.tenant_id==identity.tenant_id,
        QuestionTrace.account_id==store_for(db,identity.tenant_id).id))
    if not row:fail(404,'TRACE_NOT_FOUND','调用记录不存在')
    nodes=db.scalars(select(QuestionTraceNode).where(QuestionTraceNode.trace_id==ident).order_by(QuestionTraceNode.sequence)).all()
    result=[]
    for node in nodes:
        payloads=db.scalars(select(QuestionTracePayload).where(QuestionTracePayload.node_id==node.id)).all()
        result.append({'id':node.id,'sequence':node.sequence,'type':node.node_type,'name':node.name,'location':node.location,
            'model':node.model,'status':node.status,'usage':node.usage,'attempt':node.attempt,'error':node.error,
            'latency_ms':node.latency_ms,'payloads':{p.kind:json.loads(p.content) for p in payloads if p.content}})
    return trace_view(row)|{'nodes':result,'context_sources':row.context_sources,'capture_errors':row.capture_errors}
