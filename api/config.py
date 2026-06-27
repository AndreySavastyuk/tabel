# -*- coding: utf-8 -*-
"""Конфигурация бэкенда (env-переменные с префиксом TABEL_).

Прод-режим включается TABEL_ENV=prod. В нём Settings проверяет, что небезопасные
dev-дефолты заменены (секрет, CORS, БД), и ПАДАЕТ на старте, если нет, — чтобы
мисконфигурированный прод не поднялся. В dev (по умолчанию) проверки — no-op,
локальный запуск без env-переменных работает как раньше (zero-config DX)."""
import os
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Небезопасный dev-дефолт секрета — задан один раз, чтобы проверка не устарела
# при смене значения. НЕ использовать в проде (валидатор ниже это запрещает).
INSECURE_SECRET = "dev-secret-change-me-in-production"

# Разрешённые алгоритмы подписи JWT (в проде валидатор отвергает прочие, в т.ч. 'none').
ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512",
                      "ES256", "ES384", "ES512"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TABEL_", env_file=".env", extra="ignore")

    # Окружение: dev (по умолчанию) | prod. В проде включаются строгие проверки.
    env: Literal["dev", "prod"] = "dev"

    # БД: SQLite в разработке, PostgreSQL в проде (postgresql+psycopg://user:pass@host/db)
    database_url: str = "sqlite:///./tabel.db"
    # Подпись JWT — в проде задать TABEL_SECRET_KEY (случайный, >=32 символов).
    secret_key: str = INSECURE_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720          # 12 часов
    refresh_token_expire_minutes: int = 60 * 24 * 14  # 14 дней
    # Папка с выгрузками/справочниками (рабочая директория табеля).
    workdir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Разрешённые origin для CORS (через запятую); по умолчанию любой в LAN.
    cors_origins: str = "*"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @model_validator(mode="after")
    def _enforce_prod_hardening(self) -> "Settings":
        """В проде небезопасные dev-дефолты запрещены — fail fast на старте.
        В dev (по умолчанию) — ничего не требуем, поведение неизменно."""
        if self.env != "prod":
            return self
        problems = []
        if self.secret_key == INSECURE_SECRET or len(self.secret_key) < 32:
            problems.append(
                'TABEL_SECRET_KEY не задан или слаб — нужен случайный секрет >=32 символов '
                '(python -c "import secrets; print(secrets.token_urlsafe(48))").'
            )
        if self.algorithm not in ALLOWED_ALGORITHMS:
            problems.append(
                f"TABEL_ALGORITHM={self.algorithm!r} не разрешён — выберите один из: "
                + ", ".join(sorted(ALLOWED_ALGORITHMS)) + "."
            )
        # '*' недопустим как ЛЮБОЙ элемент списка: Starlette включает reflection+credentials,
        # если '*' встречается в allow_origins (а не только когда это всё значение).
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if not origins or "*" in origins:
            problems.append(
                "TABEL_CORS_ORIGINS пуст или содержит '*' — небезопасно с credentials; "
                "перечислите явные origin'ы через запятую (например https://tabel.example)."
            )
        if self.database_url.strip().lower().startswith("sqlite"):
            problems.append(
                "TABEL_DATABASE_URL указывает на SQLite — в проде используйте PostgreSQL "
                "(postgresql+psycopg://user:pass@host/db)."
            )
        if problems:
            raise ValueError(
                "Небезопасная конфигурация при TABEL_ENV=prod:\n- " + "\n- ".join(problems))
        return self


settings = Settings()
