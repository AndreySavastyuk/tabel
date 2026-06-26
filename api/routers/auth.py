# -*- coding: utf-8 -*-
"""Аутентификация: вход (JWT), обновление токена, текущий пользователь."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import security
from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if (user is None or not user.is_active
            or not security.verify_password(form.password, user.password_hash)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    return Token(
        access_token=security.create_access_token(user.id, user.role),
        refresh_token=security.create_refresh_token(user.id, user.role),
    )


@router.post("/refresh", response_model=Token)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = security.decode_token(body.refresh_token)
        assert payload.get("typ") == "refresh"
        uid = int(payload["sub"])
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный refresh-токен")
    user = db.get(User, uid)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь неактивен")
    return Token(
        access_token=security.create_access_token(user.id, user.role),
        refresh_token=security.create_refresh_token(user.id, user.role),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
