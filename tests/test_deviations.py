# -*- coding: utf-8 -*-
"""Очередь отклонений: стабильный дедуп между прогонами (сохранение статуса),
is_present при исчезновении, нормализация re-entry, API список/счётчик/PATCH/
bulk/скоуп руководителя. Синтетический — на чистом клоне/CI.

Запуск:  python -m pytest tests/test_deviations.py -q
"""
import os
import sys
import tempfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api import security
from api.constants import Role
from api.db import Base, get_db
from api.main import app
from api.models import (Department, DeviationItem, Employee, PipelineRun, User)
from api.services import ingestion
from engine import model


def _dr(name, date, devs, dept="Цех"):
    dr = model.DayRecord(name=name, date=date)
    dr.dept = dept
    dr.deviations = devs
    return dr


def _item(eid, dept_id, code="MISSING_EXIT", rid=1, date="10.04.2026"):
    return DeviationItem(dedup_key=f"{eid}|{date}|{code}", run_id=rid, employee_id=eid,
                         department_id=dept_id, work_date=date, dev_code=code,
                         status="new", is_present=True,
                         first_seen_at=datetime(2026, 5, 1), last_seen_at=datetime(2026, 5, 1))


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
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="ruk", password_hash=security.hash_password("ruk"),
             role=Role.dept_head.value, department_id=dept.id),
    ])
    db.commit()
    ids = {"E": e.id, "F": f.id, "dept": dept.id, "other": other.id}
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


def _run(db, created=datetime(2026, 5, 1)):
    r = PipelineRun(status="done", created_at=created)
    db.add(r)
    db.flush()
    return r.id


# --- sync-слой ------------------------------------------------------------
def test_sync_dedup_and_status_preserved(ctx):
    _, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    rid1 = _run(db)
    ingestion._sync_deviations(db, rid1, {"E": [_dr("E", "10.04.2026", ["MISSING_EXIT"])]}, {"E": eid})
    db.commit()
    it = db.scalars(select(DeviationItem)).one()
    assert it.dev_code == "MISSING_EXIT" and it.status == "new" and it.is_present is True
    assert it.department_id == ids["dept"]
    it.status = "accepted"            # оператор принял
    db.commit()
    rid2 = _run(db, created=datetime(2026, 5, 2))
    ingestion._sync_deviations(db, rid2, {"E": [_dr("E", "10.04.2026", ["MISSING_EXIT"])]}, {"E": eid})
    db.commit()
    items = db.scalars(select(DeviationItem)).all()
    assert len(items) == 1                            # дубля нет
    assert items[0].status == "accepted"             # статус сохранён
    assert items[0].run_id == rid2 and items[0].is_present is True
    db.close()


def test_sync_marks_absent_when_gone(ctx):
    _, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    rid = _run(db)
    ingestion._sync_deviations(db, rid, {"E": [_dr("E", "10.04.2026", ["MISSING_EXIT"])]}, {"E": eid})
    db.commit()
    ingestion._sync_deviations(db, rid, {"E": [_dr("E", "10.04.2026", [])]}, {"E": eid})  # исчезло
    db.commit()
    it = db.scalars(select(DeviationItem)).one()
    assert it.is_present is False                     # не удалён, помечен
    db.close()


def test_sync_reentry_normalized(ctx):
    _, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    rid = _run(db)
    ingestion._sync_deviations(
        db, rid, {"E": [_dr("E", "10.04.2026", ["Выход с территории 45 мин (12:00→12:50)"])]}, {"E": eid})
    db.commit()
    it = db.scalars(select(DeviationItem)).one()
    assert it.dev_code == "REENTRY_GAP"
    assert it.detail and "45 мин" in it.detail
    db.close()


# --- API ------------------------------------------------------------------
def test_api_list_count_patch(ctx):
    client, TS, ids = ctx
    db = TS()
    rid = _run(db)
    db.add(_item(ids["E"], ids["dept"], rid=rid))
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    lst = client.get("/deviations", headers=admin).json()
    assert len(lst) == 1 and lst[0]["dev_label"] == "Нет выхода" and lst[0]["employee_name"] == "E"
    assert client.get("/deviations/count", headers=admin).json()["open"] == 1
    did = lst[0]["id"]
    r = client.patch(f"/deviations/{did}", json={"status": "accepted", "note": "так и должно быть"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    detail = client.get(f"/deviations/{did}", headers=admin).json()
    assert detail["comments"][0]["new_status"] == "accepted"
    assert detail["comments"][0]["body"] == "так и должно быть"
    assert client.get("/deviations/count", headers=admin).json()["open"] == 0   # accepted ушёл из open


def test_api_bulk_and_dept_scope(ctx):
    client, TS, ids = ctx
    db = TS()
    rid = _run(db)
    db.add_all([_item(ids["E"], ids["dept"], rid=rid), _item(ids["F"], ids["other"], rid=rid)])
    db.commit()
    e_item = db.scalars(select(DeviationItem).where(DeviationItem.employee_id == ids["E"])).one().id
    f_item = db.scalars(select(DeviationItem).where(DeviationItem.employee_id == ids["F"])).one().id
    db.close()
    admin = tok(client, "admin", "admin")
    ruk = tok(client, "ruk", "ruk")
    assert {x["employee_name"] for x in client.get("/deviations", headers=ruk).json()} == {"E"}
    r = client.post("/deviations/bulk", json={"ids": [e_item, f_item], "status": "in_progress"}, headers=ruk)
    assert r.json() == {"updated": 1, "skipped": 1}     # F (Офис) пропущен
    assert client.patch(f"/deviations/{f_item}", json={"status": "ignored"}, headers=ruk).status_code == 403
    r2 = client.post("/deviations/bulk", json={"ids": [e_item, f_item], "status": "ignored"}, headers=admin)
    assert r2.json()["updated"] == 2


def test_api_assignee_and_users(ctx):
    client, TS, ids = ctx
    db = TS()
    rid = _run(db)
    db.add(_item(ids["E"], ids["dept"], rid=rid))
    db.commit()
    did = db.scalars(select(DeviationItem)).one().id
    admin_id = db.scalars(select(User).where(User.username == "admin")).one().id
    db.close()
    admin = tok(client, "admin", "admin")
    assert any(u["username"] == "admin" for u in client.get("/users", headers=admin).json())
    r = client.patch(f"/deviations/{did}", json={"assignee_id": admin_id}, headers=admin)
    assert r.status_code == 200 and r.json()["assignee_id"] == admin_id and r.json()["assignee_name"]
    assert client.get("/users", headers=tok(client, "ruk", "ruk")).status_code == 403   # руководителю нельзя
