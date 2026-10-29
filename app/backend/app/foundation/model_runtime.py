"""Explicit tenant configuration and authenticated encryption; no global Key fallback."""
import hashlib
import hmac
import json
import re
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from app.config.settings import settings
from app.models import ConfigVersion, Tenant
from .security import fail

ROLES = ('dialogue', 'embedding', 'rerank')
CATALOG = {
    'dialogue': {'deepseek': ['deepseek-flash','deepseek-v4-pro'], 'dashscope': ['qwen-plus','qwen-max','qwen-turbo']},
    'embedding': {'dashscope': ['text-embedding-v4','text-embedding-v3']},
    'rerank': {'dashscope': ['qwen3.7-text-rerank','qwen3-rerank']},
}


def cipher():
    try:return Fernet(settings().model_encryption_key.encode())
    except (ValueError, TypeError):fail(503,'ENCRYPTION_UNAVAILABLE','模型密钥保护尚未配置')


def seal(tenant_id, role, key):
    return cipher().encrypt(json.dumps({'tenant_id':tenant_id,'role':role,'key':key}).encode()).decode()


def unseal(tenant_id, role, ciphertext):
    try:
        value=json.loads(cipher().decrypt(ciphertext.encode()))
        if value['tenant_id']!=tenant_id or value['role']!=role:raise ValueError()
        return value['key']
    except (InvalidToken, ValueError, KeyError, TypeError):
        fail(503,'KEY_UNAVAILABLE','模型密钥无法读取，请重新保存该店铺的配置')


def endpoint(provider):
    if provider=='deepseek':return 'https://api.deepseek.com'
    value=settings().dashscope_base_url.rstrip('/')
    if not re.fullmatch(r'https://(?:dashscope\.aliyuncs\.com|[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com)/compatible-mode/v1',value):
        fail(503,'PROVIDER_ENDPOINT','百炼服务地址尚未正确配置')
    return value


def current(db, tenant_id, kind='model'):
    return db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id==tenant_id,
        ConfigVersion.kind==kind,ConfigVersion.status=='PUBLISHED').order_by(ConfigVersion.version.desc()).limit(1))


def lock_tenant(db, tenant_id):
    db.execute(update(Tenant).where(Tenant.id==tenant_id).values(active=Tenant.active))
    tenant=db.scalar(select(Tenant).where(Tenant.id==tenant_id).with_for_update().execution_options(populate_existing=True))
    if not tenant or not tenant.active:fail(403,'STORE_UNAVAILABLE','店铺不可用')
    return tenant


def current_locked(db, tenant_id, kind='model'):
    return db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id==tenant_id,
        ConfigVersion.kind==kind,ConfigVersion.status=='PUBLISHED').order_by(ConfigVersion.version.desc())
        .limit(1).with_for_update().execution_options(populate_existing=True))


def next_version(db, tenant_id, kind):
    row=db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id==tenant_id,ConfigVersion.kind==kind)
        .order_by(ConfigVersion.version.desc()).limit(1).with_for_update())
    return (row.version if row else 0)+1


def runtime(tenant_id, value):
    if not value or value.get('schema_version')!=2:fail(409,'MODELS_REQUIRED','请先配置三个模型')
    result={}
    for name in ROLES:
        role=value.get(name,{})
        if role.get('provider') not in CATALOG[name] or role.get('model_id') not in CATALOG[name][role['provider']]:
            fail(503,'MODEL_CONFIG_INVALID','已保存的模型配置无法使用，请重新校验保存')
        configured=role.get('endpoint','')
        allowed=(configured=='https://api.deepseek.com' if role['provider']=='deepseek' else bool(re.fullmatch(
            r'https://(?:dashscope\.aliyuncs\.com|[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com)/compatible-mode/v1',configured)))
        if not allowed:fail(503,'MODEL_CONFIG_INVALID','已保存的模型服务地址不可用')
        result[name]={**role,'api_key':unseal(tenant_id,name,role['key_ciphertext'])}
        if not hmac.compare_digest(fingerprint(result[name]),role.get('verified_fingerprint','')):
            fail(503,'MODEL_CONFIG_INVALID','已保存的配置与校验结果不一致，请重新保存')
    return result


def fingerprint(role):
    return hashlib.sha256(json.dumps({k:role.get(k) for k in ('provider','model_id','dimension','endpoint','api_key')},sort_keys=True).encode()).hexdigest()


def vector_space(tenant_id, role):
    return hashlib.sha256(json.dumps([tenant_id,role['provider'],role['model_id'],role.get('dimension'),role['endpoint']]).encode()).hexdigest()


def automatic_enabled(db, tenant_id):
    row=current(db,tenant_id,'reception')
    return bool(row and row.value.get('enabled'))


def safe_config(row):
    value=row.value if row else {}
    return {'version':row.version if row else 0, 'models':{role:{
        'provider':value.get(role,{}).get('provider','deepseek' if role=='dialogue' else 'dashscope'),
        'model_id':value.get(role,{}).get('model_id',{'dialogue':'deepseek-flash','embedding':'text-embedding-v4','rerank':'qwen3.7-text-rerank'}[role]),
        'dimension':value.get(role,{}).get('dimension',1024 if role=='embedding' else None),
        'has_key':bool(value.get(role,{}).get('key_ciphertext')),
        'key_hint':value.get(role,{}).get('key_hint',''),
        'verified':bool(value.get(role,{}).get('verified_fingerprint')),
        'verified_at':value.get(role,{}).get('verified_at'),
    } for role in ROLES}}
