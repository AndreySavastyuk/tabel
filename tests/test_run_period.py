# -*- coding: utf-8 -*-
"""Период прогона, пропорциональная норма, финализация, дедуп с приоритетом
финального, diff, гейт экспорта. Синтетический (без выгрузок) — на чистом
клоне/CI.

Запуск:  python -m pytest tests/test_run_period.py -q
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
from api.db import Base, get_db, get_session_factory
from api.main import app
from api.models import (DayRecordRow, Department, Employee, PipelineRun, Upload,
                        User)
from engine import compute, model


# --- engine: пропорциональная норма (pure) -------------------------------
def _no_weekend(ds):
    return False


def _eday(d, worked):
    dr = model.DayRecord(name="E", date=d)
    dr.entry, dr.exit = "08:00", "17:00"
    dr.worked_hours, dr.day_norm = worked, 8.0
    return dr


class _Ref:
    def __init__(self, code, norms):
        self._code, self.norms = code, norms

    def schedule(self, name):
        return self._code

    def dept(self, name):
        return "D"


def test_period_norm_factors_full_month_is_one():
    f = compute.period_norm_factors(date(2026, 4, 1), date(2026, 4, 30), _no_weekend)
    assert f == {"2026-04": 1.0}


def test_period_norm_factors_partial_half():
    # апрель 30 дней, все рабочие; период 1..15 => 15/30 = 0.5
    f = compute.period_norm_factors(date(2026, 4, 1), date(2026, 4, 15), _no_weekend)
    assert abs(f["2026-04"] - 0.5) < 1e-9


def test_build_periods_parity_factor_one_identical():
    """Инвариант: factor==1.0 (полный месяц) ⇒ результат идентичен прежнему."""
    ref = _Ref("G", {("G", "2026-04"): 160.0})
    recs = {"E": [_eday(f"{d:02d}.04.2026", 8.0) for d in range(1, 11)]}  # 80 ч
    base = compute.build_employee_periods(recs, ref=ref, months=["2026-04"], working_days=20)
    scaled = compute.build_employee_periods(recs, ref=ref, months=["2026-04"], working_days=20,
                                            norm_factors={"2026-04": 1.0})
    assert base["E"].period_norm == scaled["E"].period_norm == 160.0
    assert base["E"].percent == scaled["E"].percent
    assert base["E"].credited_total == scaled["E"].credited_total


def test_build_periods_partial_norm_scaled():
    """Половина месяца ⇒ норма вдвое меньше, процент вдвое выше."""
    ref = _Ref("G", {("G", "2026-04"): 160.0})
    recs = {"E": [_eday(f"{d:02d}.04.2026", 8.0) for d in range(1, 11)]}  # 80 ч
    full = compute.build_employee_periods(recs, ref=ref, months=["2026-04"], working_days=20)
    half = compute.build_employee_periods(recs, ref=ref, months=["2026-04"], working_days=10,
                                          norm_factors={"2026-04": 0.5})
    assert abs(full["E"].period_norm - 160.0) < 1e-9 and abs(full["E"].percent - 50.0) < 0.1
    assert abs(half["E"].period_norm - 80.0) < 1e-9 and abs(half["E"].percent - 100.0) < 0.1


# --- API: период / финализация / дедуп / diff / экспорт -------------------
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
    db.add_all([dept, other])
    db.flush()
    e = Employee(full_name="E", normalized_name="E", department_id=dept.id)
    f = Employee(full_name="F", normalized_name="F", department_id=other.id)
    db.add_all([e, f])
    db.flush()
    db.add(User(username="admin", password_hash=security.hash_password("admin"),
                role=Role.admin_hr.value))
    db.commit()
    ids = {"E": e.id, "F": f.id}
    db.close()

    def odb():
        s = TS()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = odb
    app.dependency_overrides[get_session_factory] = lambda: TS   # фон. задача → тестовая БД
    yield TestClient(app), TS, ids
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(path)


def tok(c):
    return {"Authorization": f"Bearer {c.post('/auth/login', data={'username': 'admin', 'password': 'admin'}).json()['access_token']}"}


def _month_run(status="done", created=datetime(2026, 5, 1), is_final=False):
    return PipelineRun(status=status, created_at=created, period_label="2026-04",
                       period_from=date(2026, 4, 1), period_to=date(2026, 4, 30),
                       is_final=is_final)


def test_create_run_with_month(ctx):
    client, TS, _ = ctx
    db = TS()
    up = Upload(filename="StorK.csv", source="stork", stored_path="/nonexistent.csv")
    db.add(up)
    db.commit()
    uid = up.id
    db.close()
    r = client.post("/runs", json={"upload_ids": [uid], "period": "2026-04"}, headers=tok(client))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["period_label"] == "2026-04"
    assert j["period_from"] == "2026-04-01" and j["period_to"] == "2026-04-30"


def test_create_run_invalid_period_422(ctx):
    client, TS, _ = ctx
    db = TS()
    up = Upload(filename="x", source="stork", stored_path="/none")
    db.add(up)
    db.commit()
    uid = up.id
    db.close()
    admin = tok(client)
    assert client.post("/runs", json={"upload_ids": [uid], "period": "2026/04"},
                       headers=admin).status_code == 422
    assert client.post("/runs", json={"upload_ids": [uid], "period": "2026-04",
                                       "period_from": "2026-04-01", "period_to": "2026-04-30"},
                       headers=admin).status_code == 422


def test_finalize_requires_done(ctx):
    client, TS, _ = ctx
    db = TS()
    r = _month_run(status="running")
    db.add(r)
    db.commit()
    rid = r.id
    db.close()
    assert client.post(f"/runs/{rid}/finalize", headers=tok(client)).status_code == 409


def test_finalize_supersedes_overlapping(ctx):
    client, TS, _ = ctx
    db = TS()
    r1 = _month_run(created=datetime(2026, 5, 1))
    r2 = _month_run(created=datetime(2026, 5, 2))
    db.add_all([r1, r2])
    db.commit()
    id1, id2 = r1.id, r2.id
    db.close()
    admin = tok(client)
    assert client.post(f"/runs/{id1}/finalize", headers=admin).status_code == 200
    assert client.post(f"/runs/{id2}/finalize", headers=admin).status_code == 200
    runs = {r["id"]: r for r in client.get("/runs", headers=admin).json()}
    assert runs[id2]["is_final"] is True
    assert runs[id1]["is_final"] is False           # снят при финализации r2
    assert client.get("/runs/final?period=2026-04", headers=admin).json()["id"] == id2


def test_dedup_prefers_final(ctx):
    client, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    old = _month_run(created=datetime(2026, 5, 1))
    new = PipelineRun(status="done", created_at=datetime(2026, 5, 9))   # позже, НЕ финальный
    db.add_all([old, new])
    db.flush()
    db.add(DayRecordRow(run_id=old.id, employee_id=eid, work_date="10.04.2026",
                        entry="08:00", exit="17:00", worked_hours=8.0, deviations=[]))
    db.add(DayRecordRow(run_id=new.id, employee_id=eid, work_date="10.04.2026",
                        entry="08:00", exit="19:00", worked_hours=10.0, deviations=[]))
    old_id = old.id
    db.commit()
    db.close()
    admin = tok(client)
    d = client.get(f"/employees/{eid}/days?month=2026-04", headers=admin).json()
    assert abs(d[0]["worked_hours"] - 10.0) < 0.01           # без финала — поздний
    assert client.post(f"/runs/{old_id}/finalize", headers=admin).status_code == 200
    d2 = client.get(f"/employees/{eid}/days?month=2026-04", headers=admin).json()
    assert abs(d2[0]["worked_hours"] - 8.0) < 0.01           # финальный старый победил


def test_export_guard_blocks_nonfinal(ctx):
    client, TS, _ = ctx
    db = TS()
    fin = _month_run(created=datetime(2026, 5, 1), is_final=True)
    non = _month_run(created=datetime(2026, 5, 2))
    db.add_all([fin, non])
    db.commit()
    non_id = non.id
    db.close()
    r = client.get(f"/runs/{non_id}/export/timesheet.xlsx", headers=tok(client))
    assert r.status_code == 409


def test_run_diff(ctx):
    client, TS, ids = ctx
    db = TS()
    a = PipelineRun(status="done", created_at=datetime(2026, 5, 1))
    b = PipelineRun(status="done", created_at=datetime(2026, 5, 2))
    db.add_all([a, b])
    db.flush()
    db.add(DayRecordRow(run_id=a.id, employee_id=ids["E"], work_date="10.04.2026",
                        entry="08:00", exit="17:00", worked_hours=8.0, deviations=[]))
    db.add(DayRecordRow(run_id=b.id, employee_id=ids["E"], work_date="10.04.2026",
                        entry="08:00", exit="18:00", worked_hours=9.0, deviations=[]))
    db.add(DayRecordRow(run_id=b.id, employee_id=ids["F"], work_date="11.04.2026",
                        entry="08:00", exit="17:00", worked_hours=8.0, deviations=[]))
    aid, bid = a.id, b.id
    db.commit()
    db.close()
    j = client.get(f"/runs/{aid}/diff/{bid}", headers=tok(client)).json()
    assert j["n_changed"] == 1
    assert abs(j["changed"][0]["fields"]["worked_hours"]["from"] - 8.0) < 0.01
    assert abs(j["changed"][0]["fields"]["worked_hours"]["to"] - 9.0) < 0.01
    assert j["n_added"] == 1 and j["n_removed"] == 0           # F 11.04 только в b
