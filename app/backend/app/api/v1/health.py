from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Tenant

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(select(func.count()).select_from(Tenant)).scalar_one()
    return {"status": "ready"}
