# -*- coding: utf-8 -*-
"""Гейт Фазы 4: отсутствия. (1) В зачёт нормы идут только APPROVED. (2) Отметка
отпуска сдвигает % отработано. (3) Воркфлоу отгула: submitted → подтверждает
только Кадры/Админ; руководитель оформляет лишь отгул по своему отделу.

Запуск:  python -m pytest tests/test_absences.py -q
"""
import os
import sys
import tempfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import compute, model

from api import security
from api.constants import Role
from api.db import Base, get_db
from api.main import app
from api.models import (Absence, Department, Employee, Schedule, ScheduleNorm, User)
from api.services.refdata_from_db import build_refdata


@pytest.fixture()
def env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    dept = Department(name="Цех")
    other = Department(name="Офис")
    sched = Schedule(code="G", shift_start="08:00", shift_len=8, lunch_start="12:00", lunch_end="12:30")
    db.add_all([dept, other, sched])
    db.flush()
    db.add(ScheduleNorm(schedule_id=sched.id, month="2026-04", norm_hours=160))
    emp = Employee(full_name="E", normalized_name="E", department_id=dept.id, schedule_id=sched.id)
    foreign = Employee(full_name="F", normalized_name="F", department_id=other.id, schedule_id=sched.id)
    db.add_all([emp, foreign])
    db.flush()
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="ruk", password_hash=security.hash_password("ruk"),
             role=Role.dept_head.value, department_id=dept.id),
    ])
    db.commit()
    eid, fid = emp.id, foreign.id
    db.close()

    def odb():
        s = TS()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = odb
    yield TestClient(app), TS, eid, fid
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(path)


def tok(c, u, p):
    return {"Authorization": f"Bearer {c.post('/auth/login', data={'username': u, 'password': p}).json()['access_token']}"}


def _worked_records():
    recs = []
    for d in (1, 2, 3, 4, 5, 11, 12, 13, 14, 15):
        dr = model.DayRecord(name="E", date=f"{d:02d}.04.2026")
        dr.entry, dr.exit, dr.worked_hours, dr.day_norm = "08:00", "17:00", 8.0, 8.0
        recs.append(dr)
    return {"E": recs}


def _percent(ref):
    recs = _worked_records()
    span = compute.date_span_of(recs)
    compute.inject_absence_records(recs, ref, span, weekend_fn=None)
    wd = compute.count_working_days(span, weekend_fn=None)
    periods = compute.build_employee_periods(recs, ref=ref, working_days=wd)
    return periods["E"]


def test_refdata_counts_only_approved(env):
    _, TS, eid, _ = env
    db = TS()
    db.add(Absence(employee_id=eid, type="отпуск", date_from=date(2026, 4, 6),
                   date_to=date(2026, 4, 10), status="approved"))
    db.add(Absence(employee_id=eid, type="отгул", date_from=date(2026, 4, 20),
                   date_to=date(2026, 4, 20), status="submitted"))
    db.commit()
    ref = build_refdata(db)
    types = {t for t, _, _ in ref.absences.get("E", [])}
    assert types == {"отпуск"}, types          # отгул (submitted) не учтён
    # подтверждаем отгул -> учитывается
    a = db.scalars(__import__('sqlalchemy').select(Absence).where(Absence.type == "отгул")).first()
    a.status = "approved"
    db.commit()
    ref2 = build_refdata(db)
    types2 = {t for t, _, _ in ref2.absences.get("E", [])}
    assert types2 == {"отпуск", "отгул"}, types2
    db.close()


def test_approved_absence_shifts_percent(env):
    _, TS, eid, _ = env
    db = TS()
    ref0 = build_refdata(db)
    p0 = _percent(ref0)                          # без отсутствий
    db.add(Absence(employee_id=eid, type="отпуск", date_from=date(2026, 4, 6),
                   date_to=date(2026, 4, 10), status="approved"))
    db.commit()
    ref1 = build_refdata(db)
    p1 = _percent(ref1)                          # +5 дней отпуска в зачёт
    db.close()
    assert p0.period_norm == 160
    assert p1.credited_total > p0.credited_total
    assert p1.percent > p0.percent
    assert abs(p0.percent - 50.0) < 0.1          # 80/160


def test_otgul_workflow_and_gating(env):
    client, TS, eid, _ = env
    admin = tok(client, "admin", "admin")
    # отгул создаётся в статусе submitted даже админом
    r = client.post("/absences", json={"employee_id": eid, "type": "отгул",
                                       "date_from": "2026-04-20", "date_to": "2026-04-20"}, headers=admin)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["status"] == "submitted"
    # руководитель не может подтверждать
    assert client.post(f"/absences/{aid}/approve", headers=tok(client, "ruk", "ruk")).status_code == 403
    # админ подтверждает
    ap = client.post(f"/absences/{aid}/approve", headers=admin)
    assert ap.status_code == 200 and ap.json()["status"] == "approved"
    # после подтверждения попадает в RefData
    db = TS()
    assert any(t == "отгул" for t, _, _ in build_refdata(db).absences.get("E", []))
    db.close()


def test_dept_head_create_rules(env):
    client, TS, eid, fid = env
    ruk = tok(client, "ruk", "ruk")
    # отпуск руководителю нельзя
    assert client.post("/absences", json={"employee_id": eid, "type": "отпуск",
                                          "date_from": "2026-04-06", "date_to": "2026-04-10"},
                       headers=ruk).status_code == 403
    # отгул по своему отделу — можно (submitted)
    ok = client.post("/absences", json={"employee_id": eid, "type": "отгул",
                                        "date_from": "2026-04-21", "date_to": "2026-04-21"}, headers=ruk)
    assert ok.status_code == 201 and ok.json()["status"] == "submitted"
    # отгул по чужому отделу — нельзя
    assert client.post("/absences", json={"employee_id": fid, "type": "отгул",
                                          "date_from": "2026-04-21", "date_to": "2026-04-21"},
                       headers=ruk).status_code == 403
