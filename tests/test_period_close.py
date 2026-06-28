# -*- coding: utf-8 -*-
"""Центр закрытия месяца: сводка готовности (раздельные no_department/
no_schedule, deviations по активному прогону, export_ready), жёсткий гейт
закрытия (409), close/reopen, выбор активного прогона, роли. Синтетический.

Запуск:  python -m pytest tests/test_period_close.py -q
"""
import os
import sys
import tempfile
from datetime import date, datetime

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
from api.models import (Department, DeviationItem, Employee, EmployeeAlias,
                        PipelineRun, Schedule, User)


@pytest.fixture()
def ctx():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    dept = Department(name="Цех")
    sched = Schedule(code="G", shift_start="08:00", shift_len=8)
    db.add_all([dept, sched])
    db.flush()
    e = Employee(full_name="E", normalized_name="E", department_id=dept.id, schedule_id=sched.id)
    db.add(e)
    db.flush()
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="buh", password_hash=security.hash_password("buh"), role=Role.accountant.value),
        User(username="ruk", password_hash=security.hash_password("ruk"),
             role=Role.dept_head.value, department_id=dept.id),
    ])
    db.commit()
    ids = {"E": e.id, "dept": dept.id, "sched": sched.id}
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


def _done_run(db, created=datetime(2026, 5, 1)):
    r = PipelineRun(status="done", created_at=created, period_label="2026-04",
                    period_from=date(2026, 4, 1), period_to=date(2026, 4, 30))
    db.add(r)
    db.flush()
    return r


def test_closing_summary_blocks(ctx):
    client, TS, ids = ctx
    db = TS()
    run = _done_run(db)
    db.add(Employee(full_name="G", normalized_name="G"))            # без отдела и графика
    db.add(EmployeeAlias(employee_id=ids["E"], raw_name="Икс", normalized_name="икс",
                         source="manual", confidence=0.0, confirmed=False))
    db.add(DeviationItem(dedup_key=f"{ids['E']}|10.04.2026|MISSING_EXIT", run_id=run.id,
                         employee_id=ids["E"], department_id=ids["dept"], work_date="10.04.2026",
                         dev_code="MISSING_EXIT", status="new", is_present=True,
                         first_seen_at=datetime(2026, 5, 1), last_seen_at=datetime(2026, 5, 1)))
    rid = run.id
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    s = client.get("/periods/2026-04/closing-summary", headers=admin).json()
    assert s["run"]["id"] == rid
    assert s["no_department"] == 1 and s["no_schedule"] == 1        # ДВА раздельных счётчика
    assert s["aliases_unresolved"] == 1
    assert s["deviations"]["open"] == 1 and s["deviations"]["by_code"]["MISSING_EXIT"] == 1
    assert s["export_ready"] is False
    blocking = {c["key"]: c["ok"] for c in s["checklist"] if c["blocking"]}
    assert blocking == {"run": True, "aliases": False, "no_schedule": False, "no_department": False}


def test_close_blocked_then_ok_then_reopen(ctx):
    client, TS, _ = ctx
    db = TS()
    _done_run(db)
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    # чистый период (E с отделом и графиком, нет алиасов) — закрытие проходит
    r = client.post("/periods/2026-04/close", json={}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert any(p["period"] == "2026-04" and p["status"] == "closed"
               for p in client.get("/periods", headers=admin).json())
    assert client.post("/periods/2026-04/reopen", json={}, headers=admin).json()["status"] == "open"


def test_close_409_on_blocker(ctx):
    client, TS, ids = ctx
    db = TS()
    _done_run(db)
    db.add(EmployeeAlias(employee_id=ids["E"], raw_name="Y", normalized_name="y",
                         source="manual", confidence=0.0, confirmed=False))
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    assert client.post("/periods/2026-04/close", json={}, headers=admin).status_code == 409


def test_active_run_selection(ctx):
    client, TS, _ = ctx
    db = TS()
    r1 = _done_run(db, created=datetime(2026, 5, 1))
    r2 = _done_run(db, created=datetime(2026, 5, 2))
    id1, id2 = r1.id, r2.id
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    assert client.get("/periods/2026-04/closing-summary", headers=admin).json()["run"]["id"] == id2
    client.put("/periods/2026-04/active-run", json={"run_id": id1}, headers=admin)
    assert client.get("/periods/2026-04/closing-summary", headers=admin).json()["run"]["id"] == id1


def test_roles_and_validation(ctx):
    client, TS, _ = ctx
    db = TS()
    _done_run(db)
    db.commit()
    db.close()
    buh = tok(client, "buh", "buh")
    ruk = tok(client, "ruk", "ruk")
    admin = tok(client, "admin", "admin")
    # бухгалтер видит сводку, но не закрывает
    assert client.get("/periods/2026-04/closing-summary", headers=buh).status_code == 200
    assert client.post("/periods/2026-04/close", json={}, headers=buh).status_code == 403
    # руководитель не имеет доступа к центру
    assert client.get("/periods", headers=ruk).status_code == 403
    assert client.get("/periods/2026-04/closing-summary", headers=ruk).status_code == 403
    # валидация формата периода
    assert client.get("/periods/2026_04/closing-summary", headers=admin).status_code == 422
