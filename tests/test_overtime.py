# -*- coding: utf-8 -*-
"""Поквартальный свод переработок: агрегация по кварталам года, API и скоуп
руководителя отдела. Синтетический (чистый клон/CI).

Запуск:  python -m pytest tests/test_overtime.py -q
"""
import os
import sys
import tempfile
from datetime import datetime

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
from api.models import DayRecordRow, Department, Employee, PipelineRun, User
from api.services import overtime as ot


@pytest.fixture()
def ctx():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    d1, d2 = Department(name="Цех"), Department(name="Офис")
    db.add_all([d1, d2])
    db.flush()
    e = Employee(full_name="E", normalized_name="E", department_id=d1.id, overtime_tracked=True)
    f = Employee(full_name="F", normalized_name="F", department_id=d2.id, overtime_tracked=False)
    db.add_all([e, f])
    db.flush()
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="ruk", password_hash=security.hash_password("ruk"),
             role=Role.dept_head.value, department_id=d1.id),
    ])
    r = PipelineRun(status="done", created_at=datetime(2026, 5, 1))
    db.add(r)
    db.flush()
    db.add_all([   # E: Q1(фев) 2ч + Q2(апр) 3ч; F: Q2(апр) 1ч; 2025 не в счёт
        DayRecordRow(run_id=r.id, employee_id=e.id, work_date="10.02.2026", overtime_h=2.0),
        DayRecordRow(run_id=r.id, employee_id=e.id, work_date="10.04.2026", overtime_h=3.0),
        DayRecordRow(run_id=r.id, employee_id=f.id, work_date="11.04.2026", overtime_h=1.0),
        DayRecordRow(run_id=r.id, employee_id=e.id, work_date="10.04.2025", overtime_h=9.0),
    ])
    db.commit()
    ids = {"E": e.id, "F": f.id, "d1": d1.id}
    db.close()

    def odb():
        s = TS()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = odb
    yield TestClient(app), TS, ids
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(path)


def tok(c, u, p):
    return {"Authorization": f"Bearer {c.post('/auth/login', data={'username': u, 'password': p}).json()['access_token']}"}


def test_quarter_aggregation(ctx):
    _, TS, ids = ctx
    db = TS()
    rows = ot.overtime_report(db, 2026)
    assert ot.available_years(db) == [2026, 2025]
    db.close()
    by = {r["employee_id"]: r for r in rows}
    assert by[ids["E"]]["q1"] == 2.0 and by[ids["E"]]["q2"] == 3.0 and by[ids["E"]]["total"] == 5.0
    assert by[ids["E"]]["q3"] == 0.0 and by[ids["E"]]["overtime_tracked"] is True
    assert by[ids["F"]]["q2"] == 1.0 and by[ids["F"]]["overtime_tracked"] is False


def test_api_and_dept_scope(ctx):
    client, _, ids = ctx
    admin = tok(client, "admin", "admin")
    r = client.get("/overtime?year=2026", headers=admin).json()
    assert r["year"] == 2026 and 2026 in r["years"]
    assert {x["employee_id"] for x in r["rows"]} == {ids["E"], ids["F"]}
    # без year — берётся последний доступный (2026)
    assert client.get("/overtime", headers=admin).json()["year"] == 2026
    # руководитель Цеха видит только своего сотрудника
    ruk = tok(client, "ruk", "ruk")
    assert {x["employee_id"] for x in client.get("/overtime", headers=ruk).json()["rows"]} == {ids["E"]}
