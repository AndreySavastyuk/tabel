# -*- coding: utf-8 -*-
"""Конфигурация бэкенда (env-переменные с префиксом TABEL_)."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TABEL_", env_file=".env", extra="ignore")

    # БД: SQLite в разработке, PostgreSQL в проде (postgresql+psycopg://user:pass@host/db)
    database_url: str = "sqlite:///./tabel.db"
    # Подпись JWT — в проде задать TABEL_SECRET_KEY.
    secret_key: str = "dev-secret-change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720          # 12 часов
    refresh_token_expire_minutes: int = 60 * 24 * 14  # 14 дней
    # Папка с выгрузками/справочниками (рабочая директория табеля).
    workdir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Разрешённые origin для CORS (через запятую); по умолчанию любой в LAN.
    cors_origins: str = "*"


settings = Settings()
