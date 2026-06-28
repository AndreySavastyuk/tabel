# -*- coding: utf-8 -*-
"""Объяснение расчёта дня: выбор прогона (latest / run_id), сырые события за
сутки, график-снимок, fallback порогов, формула, скоуп руководителя, 404 и
детерминированный тай-брейк latest_run_for_day. Синтетический (без выгрузок) —
гоняется на чистом клоне/CI.

Запуск:  python -m pytest tests/test_explain.py -q
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
from api.models import (AccessEvent, DayRecordRow, Department, Employee,
                        PipelineRun, Schedule, User)
from api.services.employee_stats import latest_run_for_day


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
    sched = Schedule(code="G", shift_start="08:00", shift_len=8,
                     lunch_start="12:00", lunch_end="12:30")
    db.add_all([dept, other, sched])
    db.flush()
    e = Employee(full_name="E", normalized_name="E", department_id=dept.id)
    f = Employee(full_name="F", normalized_name="F", department_id=other.id)
    db.add_all([e, f])
    db.flush()
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="ruk", password_hash=security.hash_password("ruk"),
             role=Role.dept_head.value, department_id=dept.id),
    ])
    db.commit()
    ids = {"E": e.id, "F": f.id, "dept": dept.id}
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


def _min_day(run_id, eid, worked=8.0, exit="17:00"):
    return DayRecordRow(run_id=run_id, employee_id=eid, work_date="15.05.2026",
                        entry="08:00", exit=exit, worked_hours=worked, deviations=[])


def test_explain_basic(ctx):
    client, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    run = PipelineRun(status="done", created_at=datetime(2026, 6, 1),
                      thresholds={"lateness_grace_min": 5, "reentry_gap_min": 30})
    db.add(run)
    db.flush()
    rid = run.id
    db.add(DayRecordRow(
        run_id=rid, employee_id=eid, work_date="15.05.2026",
        int_entry="08:10", int_exit="17:00", entry="08:10", exit="17:00",
        entry_source="internal", exit_source="internal",
        start_fixed=True, original_start="08:25",
        raw_hours=8.83, lunch_deducted=0.5, worked_hours=8.33,
        schedule_code="G", day_norm=8.0, lateness_min=10, overtime_h=0.33,
        deviations=["Выход с территории 45 мин (12:00→12:50)"]))
    db.add_all([
        AccessEvent(run_id=rid, employee_id=eid, raw_name="E",
                    event_ts=datetime(2026, 5, 15, 8, 10), kind="Вход", source="internal", system="StorK"),
        AccessEvent(run_id=rid, employee_id=eid, raw_name="E",
                    event_ts=datetime(2026, 5, 15, 17, 0), kind="Выход", source="internal", system="StorK"),
        AccessEvent(run_id=rid, employee_id=eid, raw_name="E",   # шум: другой день
                    event_ts=datetime(2026, 5, 16, 9, 0), kind="Вход", source="LEZ", system="LEZ"),
    ])
    db.commit()
    db.close()

    admin = tok(client, "admin", "admin")
    r = client.get(f"/employees/{eid}/days/15.05.2026/explain", headers=admin)
    assert r.status_code == 200, r.text
    j = r.json()
    assert abs(j["day"]["raw_hours"] - 8.83) < 0.01
    assert abs(j["day"]["day_norm"] - 8.0) < 0.01
    assert j["day"]["schedule_code"] == "G"
    assert j["day"]["original_start"] == "08:25"
    assert len(j["raw_events"]) == 2                     # только за 15.05
    assert j["raw_events"][0]["time"] == "08:10"
    assert j["schedule"]["lunch_start"] == "12:00"
    assert j["thresholds_source"] == "run_snapshot"
    assert j["thresholds"]["reentry_gap_min"] == 30
    keys = [s["key"] for s in j["formula"]]
    assert keys[:3] == ["raw_hours", "lunch", "worked"]
    assert "lateness" in keys and "overtime" in keys
    assert j["run"]["id"] == rid


def test_explain_latest_and_run_id(ctx):
    client, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    r1 = PipelineRun(status="done", created_at=datetime(2026, 6, 1))
    r2 = PipelineRun(status="done", created_at=datetime(2026, 6, 2))
    db.add_all([r1, r2])
    db.flush()
    db.add(_min_day(r1.id, eid, worked=8.0, exit="17:00"))
    db.add(_min_day(r2.id, eid, worked=9.0, exit="18:00"))
    db.commit()
    id1 = r1.id
    db.close()

    admin = tok(client, "admin", "admin")
    latest = client.get(f"/employees/{eid}/days/15.05.2026/explain", headers=admin).json()
    assert abs(latest["day"]["worked_hours"] - 9.0) < 0.01    # последний прогон
    pinned = client.get(f"/employees/{eid}/days/15.05.2026/explain?run_id={id1}", headers=admin).json()
    assert abs(pinned["day"]["worked_hours"] - 8.0) < 0.01    # зафиксирован старый


def test_explain_thresholds_fallback(ctx):
    client, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    run = PipelineRun(status="done", created_at=datetime(2026, 6, 1))   # thresholds=None
    db.add(run)
    db.flush()
    db.add(_min_day(run.id, eid))
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    j = client.get(f"/employees/{eid}/days/15.05.2026/explain", headers=admin).json()
    assert j["thresholds_source"] == "current"
    assert j["thresholds"]                                    # merged defaults непустой


def test_explain_404_and_dept_scope(ctx):
    client, TS, ids = ctx
    db = TS()
    run = PipelineRun(status="done", created_at=datetime(2026, 6, 1))
    db.add(run)
    db.flush()
    db.add(_min_day(run.id, ids["F"]))
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    ruk = tok(client, "ruk", "ruk")
    assert client.get(f"/employees/{ids['E']}/days/01.01.2020/explain", headers=admin).status_code == 404
    assert client.get(f"/employees/{ids['F']}/days/15.05.2026/explain", headers=ruk).status_code == 403


def test_explain_bad_date_422(ctx):
    client, _, ids = ctx
    admin = tok(client, "admin", "admin")
    assert client.get(f"/employees/{ids['E']}/days/2026-05-15/explain", headers=admin).status_code == 422


def test_latest_run_for_day_tiebreak(ctx):
    """При равном created_at побеждает больший run_id (детерминизм)."""
    client, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    same = datetime(2026, 6, 1)
    r1 = PipelineRun(status="done", created_at=same)
    r2 = PipelineRun(status="done", created_at=same)
    db.add_all([r1, r2])
    db.flush()
    db.add(_min_day(r1.id, eid, worked=8.0))
    db.add(_min_day(r2.id, eid, worked=9.0))      # r2.id > r1.id
    db.commit()
    id2 = r2.id
    db.close()
    s = TS()
    try:
        dr, run = latest_run_for_day(s, eid, "15.05.2026")
        assert run.id == id2
        assert abs(float(dr.worked_hours) - 9.0) < 0.01
    finally:
        s.close()
