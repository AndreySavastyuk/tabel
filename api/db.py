# -*- coding: utf-8 -*-
"""Подключение к БД (SQLAlchemy 2.0). DB-agnostic: SQLite ↔ PostgreSQL."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_connect_args = {}
if settings.database_url.startswith("sqlite"):
    # SQLite + многопоточный FastAPI
    _connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=_connect_args,
                       future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI-зависимость: сессия БД на запрос."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory():
    """Фабрика сессий для фоновых задач (своя сессия вне запроса).
    Переопределяется в тестах на тестовую БД."""
    return SessionLocal
