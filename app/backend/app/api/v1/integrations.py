from fastapi import APIRouter
from fastapi import Depends
from app.config.settings import settings
from app.models import User
from app.core.security import role_required

router = APIRouter(tags=["integrations"])


@router.get('/api/admin/integrations')
def integrations_info(user: User = Depends(role_required('ADMIN', 'KNOWLEDGE_MANAGER', 'VIEWER'))):
    s = settings()
    return {'llm': {'mode': s.llm_mode, 'model': s.llm_model, 'configured': bool(s.llm_api_key)},
            'embedding': {'model': s.embedding_model, 'dimensions': s.embedding_dim, 'configured': bool(s.embedding_api_key)},
            'rerank': {'model': s.rerank_model, 'configured': bool(s.rerank_api_key)},
            'business': {'mode': s.business_mode, 'demo_enabled': s.demo_enabled},
            'search': {'configured': bool(s.opensearch_url)}, 'storage': 'MinIO' if s.minio_endpoint else '本地文件'}
