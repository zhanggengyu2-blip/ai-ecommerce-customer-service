import copy
import uuid
from sqlalchemy import select
from app.models import ConfigVersion, KnowledgeJob, Chunk, Document, DocumentVersion, utcnow
from . import model_runtime as M, providers as P
from .reception import writing
from .security import fail, store_for
from .trace_store import Trace
from .views import iso


def resolve_role(tenant_id, role, body, old=None):
    if body.provider not in M.CATALOG[role] or body.model_id not in M.CATALOG[role][body.provider]:
        fail(422,'MODEL_NOT_SUPPORTED','该用途暂不支持所选服务商或模型')
    dimension=body.dimension
    if role=='embedding':
        allowed=[64,128,256,512,768,1024]+([1536,2048] if body.model_id=='text-embedding-v4' else [])
        if dimension not in allowed:fail(422,'EMBEDDING_DIMENSION','请选择该向量化模型支持的维度')
    elif dimension is not None:fail(422,'MODEL_DIMENSION','只有向量化模型设置维度')
    supplied=body.api_key.get_secret_value().strip() if body.api_key else ''
    if not supplied and old and old.get('provider')!=body.provider:
        fail(422,'PROVIDER_KEY_REQUIRED','更换服务商时，请填写该服务商的 Key')
    key=supplied or (M.unseal(tenant_id,role,old['key_ciphertext']) if old and old.get('key_ciphertext') else '')
    if not key:fail(422,'MODEL_KEY_REQUIRED','请补充模型 API Key')
    return {'provider':body.provider,'model_id':body.model_id,'dimension':dimension,'endpoint':M.endpoint(body.provider),'api_key':key}


def configuration(db, identity):
    row=M.current(db,identity.tenant_id)
    pending=db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id==identity.tenant_id,
        ConfigVersion.kind=='model',ConfigVersion.status=='PREPARING').order_by(ConfigVersion.version.desc()).limit(1))
    operation=db.scalar(select(KnowledgeJob).where(KnowledgeJob.tenant_id==identity.tenant_id,
        KnowledgeJob.kind=='REBUILD').order_by(KnowledgeJob.created_at.desc()).limit(1))
    return M.safe_config(row)|{'catalog':M.CATALOG,'preparing':bool(pending),
        'operation':job_view(operation) if operation else None}


def job_view(job):
    return {'id':job.id,'kind':job.kind,'status':job.status,'error':job.error,'trace_id':job.trace_id,
            'attempts':job.attempts,'created_at':iso(job.created_at),'updated_at':iso(job.updated_at)}


def verify_role(db, identity, body):
    old=M.current(db,identity.tenant_id)
    role=resolve_role(identity.tenant_id,body.role,body.config,(old.value if old else {}).get(body.role))
    trace=Trace(db.get_bind(),tenant_id=identity.tenant_id,account_id=store_for(db,identity.tenant_id).id,
                user_id=identity.user_id,kind='config_check',query='检查'+body.role+'模型配置',secrets=[role['api_key']])
    try:
        P.check(body.role,role,trace)
        trace.finish(outcome='VERIFIED',model=role['model_id'])
        return {'verified':True,'trace_id':trace.id,'checked_at':iso(utcnow())}
    except P.ProviderError as exc:
        trace.finish(status='FAILED',outcome='FAILED',error=exc.code)
        fail(502,'MODEL_CHECK_FAILED','模型配置校验失败，请检查 Key、模型权限或连接',trace_id=trace.id,provider_code=exc.code)


def save_models(db, identity, body):
    old=M.current(db,identity.tenant_id);old_value=old.value if old else {}
    if (old.version if old else 0)!=body.expected_version:fail(409,'CONFIG_CHANGED','模型配置已被修改，请刷新')
    roles={name:resolve_role(identity.tenant_id,name,getattr(body,name),old_value.get(name)) for name in M.ROLES}
    trace=Trace(db.get_bind(),tenant_id=identity.tenant_id,account_id=store_for(db,identity.tenant_id).id,
                user_id=identity.user_id,kind='config_check',query='保存并校验店铺模型配置',secrets=[r['api_key'] for r in roles.values()])
    try:
        for name,role in roles.items():
            if old_value.get(name,{}).get('verified_fingerprint')!=M.fingerprint(role):P.check(name,role,trace)
        value={'schema_version':2}
        for name,role in roles.items():
            value[name]={k:role[k] for k in ('provider','model_id','dimension','endpoint')}
            value[name].update(key_ciphertext=M.seal(identity.tenant_id,name,role['api_key']),key_hint=role['api_key'][-4:],
                verified_fingerprint=M.fingerprint(role),verified_at=iso(utcnow()))
        changed=not old or M.vector_space(identity.tenant_id,roles['embedding'])!=M.vector_space(identity.tenant_id,old_value['embedding'])
        with writing(db,identity):
            M.lock_tenant(db,identity.tenant_id)
            latest=M.current_locked(db,identity.tenant_id)
            if (latest.version if latest else 0)!=body.expected_version:fail(409,'CONFIG_CHANGED','模型配置已被修改，请刷新')
            if db.scalar(select(ConfigVersion.id).where(ConfigVersion.tenant_id==identity.tenant_id,
                    ConfigVersion.kind=='model',ConfigVersion.status=='PREPARING').with_for_update()):
                fail(409,'MODEL_PREPARING','模型更新正在处理中，请等待完成')
            has_chunks=db.scalar(select(Chunk.id).where(Chunk.tenant_id==identity.tenant_id).limit(1).with_for_update()) is not None
            preparing=changed and has_chunks
            row=ConfigVersion(tenant_id=identity.tenant_id,kind='model',version=M.next_version(db,identity.tenant_id,'model'),
                              value=value,status='PREPARING' if preparing else 'PUBLISHED')
            db.add(row);db.flush()
            if preparing:
                job=KnowledgeJob(id=str(uuid.uuid4()),tenant_id=identity.tenant_id,kind='REBUILD',
                    config_id=row.id,created_by_user_id=identity.user_id,based_on_config=body.expected_version)
                db.add(job);db.flush();result={'preparing':True,'job':job_view(job),'version':body.expected_version}
            else:
                if latest:latest.status='ARCHIVED'
                result=M.safe_config(row)|{'preparing':False}
        trace.finish(outcome='PREPARING' if preparing else 'SAVED')
        return result|{'trace_id':trace.id}
    except P.ProviderError as exc:
        trace.finish(status='FAILED',outcome='FAILED',error=exc.code)
        fail(502,'MODEL_CHECK_FAILED','模型配置校验失败，原配置仍保留',trace_id=trace.id,provider_code=exc.code)
    except Exception:
        trace.finish(status='FAILED',outcome='CONFLICT')
        raise


def retrieval_config(db, tenant_id):
    row=M.current(db,tenant_id,'rag');value=row.value if row else {}
    return {'version':row.version if row else 0,'final_top_k':value.get('final_top_k',5),'min_score':value.get('min_score',0.30)}


def save_retrieval(db, identity, body):
    with writing(db,identity):
        M.lock_tenant(db,identity.tenant_id);old=M.current_locked(db,identity.tenant_id,'rag')
        if (old.version if old else 0)!=body.expected_version:fail(409,'CONFIG_CHANGED','检索设置已被修改，请刷新')
        row=ConfigVersion(tenant_id=identity.tenant_id,kind='rag',version=M.next_version(db,identity.tenant_id,'rag'),
            status='PUBLISHED',value=body.model_dump(exclude={'expected_version'}))
        if old:old.status='ARCHIVED'
        db.add(row)
    return retrieval_config(db,identity.tenant_id)
