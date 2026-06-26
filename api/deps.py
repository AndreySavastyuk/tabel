# -*- coding: utf-8 -*-
"""Зависимости FastAPI: текущий пользователь, проверка ролей, скоуп отдела."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import security
from .constants import Role
from .db import get_db
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    cred_err = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный или просроченный токен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_token(token)
        if payload.get("typ") == "refresh":
            raise cred_err
        uid = int(payload["sub"])
    except Exception:
        raise cred_err
    user = db.get(User, uid)
    if user is None or not user.is_active:
        raise cred_err
    return user


def require_role(*roles: Role):
    """Фабрика зависимости: доступ только указанным ролям."""
    allowed = {r.value if isinstance(r, Role) else r for r in roles}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Недостаточно прав")
        return user

    return checker


def scoped_department_id(user: User) -> int | None:
    """Для Руководителя отдела — его department_id (фильтр выборок). Для прочих
    ролей — None (без ограничения)."""
    if user.role == Role.dept_head.value:
        return user.department_id
    return None
