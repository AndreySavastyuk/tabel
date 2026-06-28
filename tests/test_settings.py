# -*- coding: utf-8 -*-
"""Настройки: переименование кабинетов (bulk) и пороги расчёта (сохранение в
app_settings, чтение load_thresholds), ролевой гейтинг. Запуск:
python -m pytest tests/test_settings.py -q
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api import security
from api.constants import Role
from api.db import Base, get_db
from api.main import app
from api.models import Employee, User
from api.services.refdata_from_db import load_thresholds


@pytest.fixture()
def ctx():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="buh", password_hash=security.hash_password("buh"), role=Role.accountant.value),
        User(username="ruk", password_hash=security.hash_password("ruk"), role=Role.dept_head.value),
    ])
    db.add_all([
        Employee(full_name="A", normalized_name="A", cabinet="101"),
        Employee(full_name="B", normalized_name="B", cabinet="101"),
        Employee(full_name="C", normalized_name="C", cabinet="202"),
    ])
    db.commit()
    db.close()

    def odb():
        s = TS()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = odb
    yield TestClient(app), TS
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(path)


def tok(c, u, p):
    return {"Authorization": f"Bearer {c.post('/auth/login', data={'username': u, 'password': p}).json()['access_token']}"}


def test_cabinets_list_and_rename(ctx):
    client, _ = ctx
    admin = tok(client, "admin", "admin")
    cabs = {c["name"]: c["count"] for c in client.get("/settings/cabinets", headers=admin).json()}
    assert cabs == {"101": 2, "202": 1}
    r = client.post("/settings/cabinets/rename", json={"old_name": "101", "new_name": "К-101"}, headers=admin)
    assert r.status_code == 200 and r.json()["updated"] == 2
    cabs2 = {c["name"]: c["count"] for c in client.get("/settings/cabinets", headers=admin).json()}
    assert cabs2 == {"К-101": 2, "202": 1}


def test_thresholds_get_and_put(ctx):
    client, TS = ctx
    admin = tok(client, "admin", "admin")
    items = client.get("/settings/thresholds", headers=admin).json()
    keys = {i["key"] for i in items}
    assert "lateness_grace_min" in keys and "shift_gap_min" in keys
    assert all("label" in i and "default" in i for i in items)

    r = client.put("/settings/thresholds",
                   json={"values": {"lateness_grace_min": 15, "shift_gap_min": 240}}, headers=admin)
    assert r.status_code == 200
    vals = {i["key"]: i["value"] for i in r.json()}
    assert vals["lateness_grace_min"] == 15 and vals["shift_gap_min"] == 240

    # сохранено в app_settings и читается движком
    db = TS()
    saved = load_thresholds(db)
    db.close()
    assert saved.get("lateness_grace_min") == 15 and saved.get("shift_gap_min") == 240


def test_settings_role_gating(ctx):
    client, _ = ctx
    for u in ("buh", "ruk"):
        assert client.get("/settings/cabinets", headers=tok(client, u, u)).status_code == 403
        assert client.get("/settings/thresholds", headers=tok(client, u, u)).status_code == 403
