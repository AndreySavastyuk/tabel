# -*- coding: utf-8 -*-
"""UI-импорт справочников: POST /reference/import заводит отделы/графики/
сотрудников из загруженного Excel (синтетический файл, без приватных данных);
проверка ролевого гейтинга. Запуск: python -m pytest tests/test_reference_import.py -q
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
from api.models import User

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


def _emp_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ФИО", "Отдел", "Кабинет", "График", "Фикс.время", "Контроль ЛЭЗ"])
    ws.append(["Иванов Иван Иванович", "Цех №1", "101", "5x2", "08:00", "да"])
    ws.append(["Петров Пётр Петрович", "Бухгалтерия", "202", "5x2", "", "нет"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_employees_creates_departments_and_employees(ctx):
    client, _ = ctx
    admin = tok(client, "admin", "admin")
    r = client.post("/reference/import", data={"kind": "employees"},
                    files={"file": ("Справочник_сотрудников.xlsx", _emp_xlsx(), _XLSX)},
                    headers=admin)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["before"]["employees"] == 0
    assert body["after"]["employees"] == 2
    assert body["after"]["departments"] >= 3          # 2 реальных + «Без отдела»

    emps = client.get("/employees", headers=admin).json()
    assert len(emps) == 2
    assert all(e["department_id"] for e in emps)       # отделы реально привязаны

    # идемпотентность: повторный импорт не плодит дубликаты
    r2 = client.post("/reference/import", data={"kind": "employees"},
                     files={"file": ("Справочник_сотрудников.xlsx", _emp_xlsx(), _XLSX)},
                     headers=admin)
    assert r2.status_code == 201
    assert r2.json()["after"]["employees"] == 2


def test_import_role_gating(ctx):
    client, _ = ctx
    for u in ("buh", "ruk"):
        r = client.post("/reference/import", data={"kind": "employees"},
                        files={"file": ("e.xlsx", _emp_xlsx(), _XLSX)},
                        headers=tok(client, u, u))
        assert r.status_code == 403, (u, r.status_code)
