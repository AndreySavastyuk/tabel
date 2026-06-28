# -*- coding: utf-8 -*-
"""Точка входа FastAPI. Запуск: uvicorn api.main:app --host 0.0.0.0 --port 8000

Хост 0.0.0.0 делает сервис доступным в локальной сети."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import (absences, aliases, assign, auth, calendar, departments,
                      deviations, employees, periods, reference, runs, schedules,
                      settings as settings_router, uploads, users)

# В проде прячем интерактивную документацию (Swagger/redoc/openapi-схему).
_docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if settings.is_prod else {}
app = FastAPI(title="Табель СКУД", version="0.1.0",
              description="Веб-табель: подготовка табелей, анализ времени, "
                          "отсутствия, переработки (часы и деньги), статистика.",
              **_docs)

if settings.is_prod:
    # Только явные origin'ы ('*' уже запрещён валидатором Settings в проде),
    # методы/заголовки сужены до фактически используемых SPA.
    _origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
else:
    # Dev: удобство (любой origin в LAN) — поведение как раньше.
    _origins = ["*"] if settings.cors_origins.strip() == "*" else \
        [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(departments.router)
app.include_router(schedules.router)
app.include_router(employees.router)
app.include_router(users.router)
app.include_router(uploads.router)
app.include_router(reference.router)
app.include_router(aliases.router)
app.include_router(assign.router)
app.include_router(settings_router.router)
app.include_router(runs.router)
app.include_router(deviations.router)
app.include_router(periods.router)
app.include_router(absences.router)
app.include_router(calendar.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
