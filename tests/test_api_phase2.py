# -*- coding: utf-8 -*-
"""API-тесты Фазы 2: загрузка файлов, запуск прогона (фоновая обработка),
статус, своды, Excel-экспорт, гварды ролей и скоуп отдела.

Запуск:  python -m pytest tests/test_api_phase2.py -q
"""
import os
import shutil
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import api.routers.uploads as uploads_mod
from api.db import Base, get_db, get_session_factory
from api.main import app
from api.models import Upload
from scripts.seed_from_excel import import_reference, seed_users


@pytest.fixture()
def ctx():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    dept_ids = import_reference(db, ROOT)   # справочники
    seed_users(db, dept_ids)                # дев-юзеры admin/buh/ruk
    db.commit()
    db.close()

    def odb():
        s = TS()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = odb
    app.dependency_overrides[get_session_factory] = lambda: TS
    updir = tempfile.mkdtemp(prefix="up_")
    old_dir = uploads_mod.UPLOAD_DIR
    uploads_mod.UPLOAD_DIR = updir

    yield TestClient(app), TS

    app.dependency_overrides.clear()
    uploads_mod.UPLOAD_DIR = old_dir
    shutil.rmtree(updir, ignore_errors=True)
    engine.dispose()
    os.unlink(path)


def tok(client, u, p):
    r = client.post("/auth/login", data={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_upload_roles(ctx):
    client, _ = ctx
    files = {"file": ("test.csv", b"a;b;c\n", "text/csv")}
    r = client.post("/uploads", data={"source": "stork"}, files=files, headers=tok(client, "admin", "admin"))
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "stork"
    # бухгалтер не может загружать
    files = {"file": ("test.csv", b"a;b;c\n", "text/csv")}
    assert client.post("/uploads", data={"source": "stork"}, files=files,
                       headers=tok(client, "buh", "buh")).status_code == 403


def test_run_pipeline_and_export(ctx):
    client, TS = ctx
    # загрузки указывают на реальные файлы репозитория
    s = TS()
    ups = [
        Upload(filename="StorK.csv", source="stork", stored_path=os.path.join(ROOT, "StorK.csv")),
        Upload(filename="SIGUR.xlsx", source="sigur", stored_path=os.path.join(ROOT, "SIGUR.xlsx")),
        Upload(filename="lez.xlsx", source="lez", stored_path=os.path.join(ROOT, "ЛЭЗ", "lez.xlsx")),
    ]
    s.add_all(ups)
    s.commit()
    ids = [u.id for u in ups]
    s.close()

    admin = tok(client, "admin", "admin")
    r = client.post("/runs", json={"upload_ids": ids}, headers=admin)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    # фоновая задача в TestClient выполняется синхронно → прогон уже готов
    run = client.get(f"/runs/{rid}", headers=admin).json()
    assert run["status"] == "done", run
    assert run["n_day_records"] > 1000
    assert run["n_employees"] > 100

    # своды — бухгалтеру можно, руководителю нет
    assert client.get(f"/runs/{rid}/periods", headers=admin).status_code == 200
    assert client.get(f"/runs/{rid}/periods", headers=tok(client, "buh", "buh")).status_code == 200
    assert client.get(f"/runs/{rid}/periods", headers=tok(client, "ruk", "ruk")).status_code == 403

    # экспорт xlsx (zip-сигнатура PK)
    ex = client.get(f"/runs/{rid}/export/timesheet.xlsx", headers=admin)
    assert ex.status_code == 200
    assert ex.content[:2] == b"PK"
    assert len(ex.content) > 5000

    # day-records: руководитель видит МЕНЬШЕ, чем админ (скоуп отдела)
    all_dr = client.get(f"/runs/{rid}/day-records?limit=20000", headers=admin).json()
    ruk_dr = client.get(f"/runs/{rid}/day-records?limit=20000", headers=tok(client, "ruk", "ruk")).json()
    assert len(all_dr) > len(ruk_dr) > 0


def test_export_not_ready_409(ctx):
    client, TS = ctx
    from api.models import PipelineRun
    s = TS()
    run = PipelineRun(status="queued", upload_ids=[])
    s.add(run)
    s.commit()
    rid = run.id
    s.close()
    r = client.get(f"/runs/{rid}/export/timesheet.xlsx", headers=tok(client, "admin", "admin"))
    assert r.status_code == 409
