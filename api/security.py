# -*- coding: utf-8 -*-
"""Пароли (bcrypt) и JWT (PyJWT)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def hash_password(plain: str) -> str:
    # bcrypt ограничен 72 байтами — обрезаем (стандартная практика).
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


def _token(sub: str, role: str, minutes: int, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(sub), "role": role, "iat": now,
               "exp": now + timedelta(minutes=minutes)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(sub: str, role: str, extra: dict | None = None) -> str:
    return _token(sub, role, settings.access_token_expire_minutes, extra)


def create_refresh_token(sub: str, role: str) -> str:
    return _token(sub, role, settings.refresh_token_expire_minutes, {"typ": "refresh"})


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
