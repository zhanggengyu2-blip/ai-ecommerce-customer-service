from fastapi import APIRouter
from fastapi import Depends, HTTPException
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User, AuditLog, ConfigVersion, PromptTemplate
from app.core.security import role_required
from app.schemas.configuration import ConfigRequest
from app.config.settings import settings
import re
from pydantic import BaseModel, Field

router = APIRouter(tags=["configuration"])
BUILTIN_PROMPT_KEYS = {
    "routing_instruction", "knowledge_safety_instruction", "knowledge_instruction",
    "knowledge_facts_instruction", "knowledge_chunking_instruction",
}


class PromptRequest(BaseModel):
    value: str = Field(max_length=20000)


@router.get("/api/admin/configs")
def list_configs(user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER", "VIEWER")), db: Session = Depends(get_db)):
    existing = {kind for kind, in db.execute(select(ConfigVersion.kind).where(
        ConfigVersion.tenant_id == user.tenant_id, ConfigVersion.kind.in_(["model", "rag"])).distinct())}
    defaults = {
        "model": {"llm_model": settings().llm_model, "embedding_model": settings().embedding_model,
                  "embedding_dim": settings().embedding_dim, "rerank_model": settings().rerank_model},
        "rag": {"final_top_k": 5, "target_chars": 800, "overlap_chars": 100},
    }
    for kind, value in defaults.items():
        if kind not in existing:
            db.add(ConfigVersion(tenant_id=user.tenant_id, kind=kind, version=1,
                                 value=value, status="PUBLISHED"))
    if set(defaults) - existing:
        db.commit()
    rows = db.scalars(select(ConfigVersion).where(ConfigVersion.tenant_id == user.tenant_id)
                      .where(ConfigVersion.kind.in_(["model", "rag"]))
                      .order_by(ConfigVersion.kind, ConfigVersion.version.desc())).all()
    return [{"id": row.id, "kind": row.kind, "version": row.version,
             "value": row.value,
             "status": row.status} for row in rows]


@router.get("/api/admin/prompts")
def list_prompts(user: User = Depends(role_required("ADMIN", "KNOWLEDGE_MANAGER", "VIEWER")), db: Session = Depends(get_db)):
    rows = db.scalars(select(PromptTemplate).where(PromptTemplate.tenant_id == user.tenant_id)
                      .order_by(PromptTemplate.key)).all()
    if not rows:
        # One-time compatibility import for databases upgraded without the data migration.
        legacy = db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id == user.tenant_id,
            ConfigVersion.kind == "prompt", ConfigVersion.status == "PUBLISHED")
            .order_by(ConfigVersion.version.desc()).limit(1))
        values = legacy.value if legacy and isinstance(legacy.value, dict) else {}
        for key, value in values.items():
            if isinstance(key, str) and isinstance(value, str):
                db.add(PromptTemplate(tenant_id=user.tenant_id, key=key, value=value))
        db.commit()
        rows = db.scalars(select(PromptTemplate).where(PromptTemplate.tenant_id == user.tenant_id)
                          .order_by(PromptTemplate.key)).all()
    return [{"id": row.id, "key": row.key, "value": row.value,
             "updated_at": row.updated_at.isoformat() if row.updated_at else None} for row in rows]


@router.put("/api/admin/prompts/{key}")
def save_prompt(key: str, body: PromptRequest, user: User = Depends(role_required("ADMIN")), db: Session = Depends(get_db)):
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key) or not body.value.strip():
        raise HTTPException(422, "Invalid prompt key or empty prompt")
    row = db.scalar(select(PromptTemplate).where(PromptTemplate.tenant_id == user.tenant_id,
                                               PromptTemplate.key == key))
    if row:
        row.value = body.value
    else:
        row = PromptTemplate(tenant_id=user.tenant_id, key=key, value=body.value)
        db.add(row)
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="prompt_save",
                    target=f"prompt:{key}", detail={"key": key}))
    db.commit()
    return {"id": row.id, "key": row.key, "value": row.value,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


@router.delete("/api/admin/prompts/{key}")
def delete_prompt(key: str, user: User = Depends(role_required("ADMIN")), db: Session = Depends(get_db)):
    if key in BUILTIN_PROMPT_KEYS:
        raise HTTPException(409, "Built-in prompt keys cannot be deleted")
    row = db.scalar(select(PromptTemplate).where(PromptTemplate.tenant_id == user.tenant_id,
                                               PromptTemplate.key == key))
    if not row:
        raise HTTPException(404, "Prompt not found")
    db.delete(row)
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="prompt_delete",
                    target=f"prompt:{key}", detail={"key": key}))
    db.commit()
    return {"ok": True}


@router.post("/api/admin/configs")
def create_config(body: ConfigRequest, user: User = Depends(role_required("ADMIN")), db: Session = Depends(get_db)):
    allowed = {"model": {"llm_model", "embedding_model", "embedding_dim", "rerank_model"},
               "rag": {"final_top_k", "target_chars", "overlap_chars"}}
    if body.kind not in allowed or set(body.value) - allowed[body.kind]:
        raise HTTPException(422, "Unsupported configuration")
    defaults = {
        "model": {"llm_model": settings().llm_model, "embedding_model": settings().embedding_model,
                  "embedding_dim": settings().embedding_dim, "rerank_model": settings().rerank_model},
        "rag": {"final_top_k": 5, "target_chars": 800, "overlap_chars": 100},
    }
    current = db.scalar(select(ConfigVersion).where(ConfigVersion.tenant_id == user.tenant_id,
        ConfigVersion.kind == body.kind, ConfigVersion.status == "PUBLISHED")
        .order_by(desc(ConfigVersion.version)).limit(1))
    effective = {**defaults.get(body.kind, {}), **(current.value if current else {}), **body.value}
    if body.kind == "rag" and (not isinstance(effective.get("final_top_k"), int) or not 1 <= effective["final_top_k"] <= 10):
        raise HTTPException(422, "final_top_k must be 1-10")
    if body.kind == "model" and "embedding_dim" in effective and (not isinstance(effective["embedding_dim"], int) or not 1 <= effective["embedding_dim"] <= 4096):
        raise HTTPException(422, "embedding_dim must be 1-4096")
    if body.kind == "rag":
        target = effective.get("target_chars", 800)
        overlap = effective.get("overlap_chars", 100)
        if not isinstance(target, int) or not 200 <= target <= 4000:
            raise HTTPException(422, "target_chars must be 200-4000")
        if not isinstance(overlap, int) or not 0 <= overlap < target // 2:
            raise HTTPException(422, "overlap_chars must be less than half target_chars")
    version = db.scalar(select(func.coalesce(func.max(ConfigVersion.version), 0)).where(ConfigVersion.tenant_id == user.tenant_id,
                                                                                      ConfigVersion.kind == body.kind)) + 1
    row = ConfigVersion(tenant_id=user.tenant_id, kind=body.kind, version=version, value=effective)
    db.add(row)
    db.commit()
    return {"id": row.id, "kind": row.kind, "version": version, "status": row.status}


@router.post("/api/admin/configs/{config_id}/publish")
def publish_config(config_id: int, user: User = Depends(role_required("ADMIN")), db: Session = Depends(get_db)):
    row = db.get(ConfigVersion, config_id)
    if not row or row.tenant_id != user.tenant_id:
        raise HTTPException(404, "Config not found")
    if row.kind == "prompt":
        raise HTTPException(409, "Prompts are managed separately")
    if row.status != "DRAFT":
        raise HTTPException(409, "Only drafts can be published")
    for old in db.scalars(select(ConfigVersion).where(ConfigVersion.tenant_id == user.tenant_id,
                                                      ConfigVersion.kind == row.kind, ConfigVersion.status == "PUBLISHED")):
        old.status = "ARCHIVED"
    row.status = "PUBLISHED"
    db.add(AuditLog(tenant_id=user.tenant_id, actor=f"staff:{user.id}", action="config_publish",
                    target=f"config:{row.id}", detail={"kind": row.kind, "version": row.version}))
    db.commit()
    return {"status": row.status}
