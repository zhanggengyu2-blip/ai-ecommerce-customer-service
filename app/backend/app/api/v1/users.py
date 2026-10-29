from fastapi import APIRouter
from fastapi import Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import User
from app.core.security import role_required
from app.schemas.users import StaffCreateRequest, StaffUpdateRequest
from app.services import users as users_service

router = APIRouter(tags=["users"])


@router.get("/api/admin/users")
def list_users(user: User = Depends(role_required("ADMIN")), db: Session = Depends(get_db)):
    return users_service.list_users(user=user, db=db)


@router.get("/api/admin/users/page")
def page_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               keyword: str = Query("", max_length=128), user_type: str = "", role: str = "",
               active: bool | None = None, user: User = Depends(role_required("ADMIN")), db: Session = Depends(get_db)):
    return users_service.page_users(page=page, page_size=page_size, keyword=keyword, user_type=user_type, role=role, active=active, user=user, db=db)


@router.post("/api/admin/users")
def create_user(body: StaffCreateRequest, user: User = Depends(role_required("ADMIN")), db: Session = Depends(get_db)):
    return users_service.create_user(body=body, user=user, db=db)


@router.patch("/api/admin/users/{user_id}")
def update_user(user_id: int, body: StaffUpdateRequest, user: User = Depends(role_required("ADMIN")),
                db: Session = Depends(get_db)):
    return users_service.update_user(user_id=user_id, body=body, user=user, db=db)
