# -*- coding: utf-8 -*-
"""Список пользователей — для назначения ответственного за отклонение.
Доступ: Кадры/Админ и Бухгалтер (те, кто ведёт очередь отклонений)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import require_role
from ..models import User
from ..schemas import UserBrief

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserBrief],
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.username)).all()
