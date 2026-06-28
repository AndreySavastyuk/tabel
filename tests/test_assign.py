# -*- coding: utf-8 -*-
"""Массовое назначение из файла: предпросмотр (matched/ambiguous/not_found) и
применение с get-or-create отделов/графиков. Запуск:
python -m pytest tests/test_assign.py -q
"""
import io
import os
import sys
import tempfile

import openpyxl
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
from api.models import Department, Employee, Schedule, User

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
    for full in ("Иванов Иван Иванович", "Петров Пётр Петрович",
                 "Кузнецов Алексей Иванович", "Кузнецов Андрей Петрович"):
        db.add(Employee(full_name=full, normalized_name=full))
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


def _sheet() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ФИО", "Отдел", "График"])
    ws.append(["Иванов Иван Иванович", "Цех №1", "5x2"])    # точное совпадение
    ws.append(["Кузнецов", "Склад", ""])                     # два однофамильца -> неоднозначно
    ws.append(["Несуществующий Икс", "X", ""])               # не найден
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_preview_classifies_rows(ctx):
    client, TS = ctx
    admin = tok(client, "admin", "admin")
    r = client.post("/assign/preview", files={"file": ("assign.xlsx", _sheet(), _XLSX)}, headers=admin)
    assert r.status_code == 200, r.text
    rows = {row["raw_name"]: row for row in r.json()}
    assert rows["Иванов Иван Иванович"]["status"] == "matched"
    assert rows["Иванов Иван Иванович"]["match"]["full_name"] == "Иванов Иван Иванович"
    assert rows["Кузнецов"]["status"] == "ambiguous"
    assert len(rows["Кузнецов"]["candidates"]) == 2
    assert rows["Несуществующий Икс"]["status"] == "not_found"
    # предпросмотр ничего не создаёт
    db = TS()
    assert db.query(Department).count() == 0 and db.query(Schedule).count() == 0
    db.close()


def test_apply_creates_and_assigns(ctx):
    client, TS = ctx
    admin = tok(client, "admin", "admin")
    preview = client.post("/assign/preview", files={"file": ("a.xlsx", _sheet(), _XLSX)},
                          headers=admin).json()
    ivanov = next(p for p in preview if p["raw_name"] == "Иванов Иван Иванович")
    kuznetsov = next(p for p in preview if p["raw_name"] == "Кузнецов")
    items = [
        {"employee_id": ivanov["match"]["employee_id"], "department_name": "Цех №1", "schedule_code": "5x2"},
        {"employee_id": kuznetsov["candidates"][0]["employee_id"], "department_name": "Склад"},
    ]
    r = client.post("/assign/apply", json={"items": items}, headers=admin)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["updated"] == 2
    assert set(res["departments_created"]) == {"Цех №1", "Склад"}
    assert res["schedules_created"] == ["5x2"]

    db = TS()
    iv = db.get(Employee, ivanov["match"]["employee_id"])
    dept = db.query(Department).filter_by(name="Цех №1").one()
    sched = db.query(Schedule).filter_by(code="5x2").one()
    assert iv.department_id == dept.id and iv.schedule_id == sched.id
    db.close()


def test_assign_role_gating(ctx):
    client, _ = ctx
    for u in ("buh", "ruk"):
        r = client.post("/assign/preview", files={"file": ("a.xlsx", _sheet(), _XLSX)},
                        headers=tok(client, u, u))
        assert r.status_code == 403, (u, r.status_code)
