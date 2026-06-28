# -*- coding: utf-8 -*-
"""Тесты UX-доработок: массовое присвоение (bulk-assign) и помесячная сводка
карточки сотрудника (агрегация day_records по месяцам, дедуп по последнему
прогону).

Запуск:  python -m pytest tests/test_employee_stats.py -q
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
from api.models import (DayRecordRow, Department, Employee, PipelineRun,
                        Schedule, ScheduleNorm, User)


def _day(run_id, eid, date, worked=0.0, ot=0.0, late=0, absence=None, entry="08:00", exit="17:00"):
    return DayRecordRow(run_id=run_id, employee_id=eid, work_date=date,
                        entry=entry, exit=exit, worked_hours=worked, overtime_h=ot,
                        lateness_min=late, absence=absence, deviations=[])


@pytest.fixture()
def ctx():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    dept = Department(name="Цех")
    other = Department(name="Офис")
    sched = Schedule(code="G", shift_start="08:00", shift_len=8)
    db.add_all([dept, other, sched])
    db.flush()
    db.add(ScheduleNorm(schedule_id=sched.id, month="2026-04", norm_hours=160))
    e = Employee(full_name="E", normalized_name="E", department_id=dept.id)
    f = Employee(full_name="F", normalized_name="F", department_id=other.id)
    db.add_all([e, f])
    db.flush()
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="buh", password_hash=security.hash_password("buh"), role=Role.accountant.value),
        User(username="ruk", password_hash=security.hash_password("ruk"),
             role=Role.dept_head.value, department_id=dept.id),
    ])
    db.commit()
    ids = {"E": e.id, "F": f.id, "dept": dept.id, "sched": sched.id}
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


def test_bulk_assign_and_gating(ctx):
    client, _, ids = ctx
    admin = tok(client, "admin", "admin")
    r = client.patch("/employees/bulk",
                     json={"ids": [ids["E"], ids["F"]], "department_id": ids["dept"], "schedule_id": ids["sched"]},
                     headers=admin)
    assert r.status_code == 200 and r.json()["updated"] == 2
    # проверяем присвоение
    e = client.get(f"/employees/{ids['F']}", headers=admin).json()
    assert e["department_id"] == ids["dept"] and e["schedule_id"] == ids["sched"]
    # очистка графика явным null
    client.patch("/employees/bulk", json={"ids": [ids["F"]], "schedule_id": None}, headers=admin)
    assert client.get(f"/employees/{ids['F']}", headers=admin).json()["schedule_id"] is None
    # гейтинг
    assert client.patch("/employees/bulk", json={"ids": [ids["E"]], "cabinet": "X"},
                        headers=tok(client, "buh", "buh")).status_code == 403
    assert client.patch("/employees/bulk", json={"ids": [ids["E"]], "cabinet": "X"},
                        headers=tok(client, "ruk", "ruk")).status_code == 403


def test_no_department_filter(ctx):
    """Фильтр «без отдела» — очередь неразобранных сотрудников."""
    client, TS, _ = ctx
    db = TS()
    db.add(Employee(full_name="Безотделов Б", normalized_name="Безотделов Б"))  # без отдела
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    assert len(client.get("/employees", headers=admin).json()) == 3      # E, F, Безотделов
    nd = client.get("/employees?no_department=true", headers=admin).json()
    assert len(nd) == 1 and nd[0]["full_name"] == "Безотделов Б"


def test_admin_patch_employee_assignment(ctx):
    """Единичное назначение отдела/графика/кабинета (на это опирается карточка)."""
    client, _, ids = ctx
    admin = tok(client, "admin", "admin")
    r = client.patch(f"/employees/{ids['F']}",
                     json={"department_id": ids["dept"], "schedule_id": ids["sched"], "cabinet": "К-5"},
                     headers=admin)
    assert r.status_code == 200, r.text
    e = client.get(f"/employees/{ids['F']}", headers=admin).json()
    assert e["department_id"] == ids["dept"]
    assert e["schedule_id"] == ids["sched"]
    assert e["cabinet"] == "К-5"


def test_monthly_summary(ctx):
    client, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    db.add(Employee(full_name="x", normalized_name="x"))  # шум
    # сотруднику E присвоим график (для нормы)
    db.get(Employee, eid).schedule_id = ids["sched"]
    run = PipelineRun(status="done", created_at=datetime(2026, 5, 1))
    db.add(run)
    db.flush()
    rid = run.id
    db.add_all([
        _day(rid, eid, "01.04.2026", worked=8.0),
        _day(rid, eid, "02.04.2026", worked=8.0),
        _day(rid, eid, "03.04.2026", worked=8.0),
        _day(rid, eid, "04.04.2026", worked=9.0, ot=1.0),
        _day(rid, eid, "07.04.2026", worked=8.0, late=30),
        _day(rid, eid, "08.04.2026", worked=0.0, absence="отпуск", entry=None, exit=None),
    ])
    db.commit()
    db.close()

    admin = tok(client, "admin", "admin")
    m = client.get(f"/employees/{eid}/months", headers=admin).json()
    assert len(m) == 1
    apr = m[0]
    assert apr["month"] == "2026-04"
    assert apr["work_days"] == 5                       # 5 дней с часами (08 — отпуск, не в счёт)
    assert abs(apr["worked_total"] - 41.0) < 0.01      # 8+8+8+9+8
    assert abs(apr["overtime_total"] - 1.0) < 0.01
    assert apr["late_days"] == 1 and apr["late_minutes"] == 30
    assert apr["absence_days"] == 1
    assert apr["norm_hours"] == 160
    assert abs(apr["balance"] - (41.0 - 160)) < 0.01

    days = client.get(f"/employees/{eid}/days?month=2026-04", headers=admin).json()
    assert len(days) == 6
    assert days[0]["work_date"] == "01.04.2026"        # отсортировано по дате


def test_run_day_records_dept_scope(ctx):
    """Скоуп руководителя на /runs/{id}/day-records: он видит только свой отдел.
    Синтетический (без реальных выгрузок) — гоняется и на чистом клоне/CI, в
    отличие от интеграционного test_api_phase2::test_run_pipeline_and_export."""
    client, TS, ids = ctx
    db = TS()
    run = PipelineRun(status="done", created_at=datetime(2026, 5, 1))
    db.add(run)
    db.flush()
    rid = run.id
    db.add_all([
        _day(rid, ids["E"], "01.04.2026", worked=8.0),   # E — в отделе ruk'а (Цех)
        _day(rid, ids["E"], "02.04.2026", worked=8.0),
        _day(rid, ids["F"], "01.04.2026", worked=8.0),   # F — в чужом отделе (Офис)
    ])
    db.commit()
    db.close()

    admin = tok(client, "admin", "admin")
    ruk = tok(client, "ruk", "ruk")
    all_dr = client.get(f"/runs/{rid}/day-records?limit=20000", headers=admin).json()
    ruk_dr = client.get(f"/runs/{rid}/day-records?limit=20000", headers=ruk).json()
    assert len(all_dr) == 3                       # админ видит все записи прогона
    assert {r["employee_name"] for r in ruk_dr} == {"E"}   # руководитель — только свой отдел
    assert len(all_dr) > len(ruk_dr) > 0          # инвариант скоупа


def test_dedup_latest_run(ctx):
    client, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    r1 = PipelineRun(status="done", created_at=datetime(2026, 5, 1))
    r2 = PipelineRun(status="done", created_at=datetime(2026, 5, 2))
    db.add_all([r1, r2])
    db.flush()
    db.add(_day(r1.id, eid, "01.04.2026", worked=8.0))
    db.add(_day(r2.id, eid, "01.04.2026", worked=10.0))   # позже — должен победить
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    days = client.get(f"/employees/{eid}/days?month=2026-04", headers=admin).json()
    assert len(days) == 1
    assert abs(days[0]["worked_hours"] - 10.0) < 0.01
