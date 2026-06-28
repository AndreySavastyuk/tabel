# -*- coding: utf-8 -*-
"""Разбор ФИО: очередь неподтверждённых алиасов, подсказка кандидатов по
похожести, подтверждение «как нового» и слияние дубля с переносом данных.
Запуск: python -m pytest tests/test_aliases.py -q
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
from api.models import DayRecordRow, Employee, EmployeeAlias, PipelineRun, User


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


def _emp(db, full, confirmed):
    e = Employee(full_name=full, normalized_name=full)
    db.add(e)
    db.flush()
    db.add(EmployeeAlias(employee_id=e.id, raw_name=full, normalized_name=full,
                         source="manual", confidence=(1.0 if confirmed else 0.0),
                         confirmed=confirmed))
    return e


def test_unresolved_candidates_and_merge(ctx):
    client, TS = ctx
    db = TS()
    canon = _emp(db, "Иванов Иван Иванович", True)      # из справочника (confirmed)
    ph = _emp(db, "Иванов И", False)                     # плейсхолдер из ингеста
    run = PipelineRun(status="done")
    db.add(run)
    db.flush()
    db.add(DayRecordRow(run_id=run.id, employee_id=ph.id, work_date="01.04.2026", worked_hours=8))
    db.commit()
    ph_id, canon_id = ph.id, canon.id
    aid = db.query(EmployeeAlias).filter_by(employee_id=ph_id, confirmed=False).one().id
    db.close()

    admin = tok(client, "admin", "admin")
    items = client.get("/aliases/unresolved", headers=admin).json()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == aid and item["raw_name"] == "Иванов И"
    assert canon_id in [c["employee_id"] for c in item["candidates"]]
    assert item["candidates"][0]["canonical"] is True       # каноничный кандидат первым

    r = client.post(f"/aliases/{aid}/merge", json={"target_employee_id": canon_id}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["moved"]["day_records"] == 1

    db = TS()
    assert db.get(Employee, ph_id) is None                  # дубль удалён
    assert db.query(DayRecordRow).one().employee_id == canon_id   # день перенаправлен
    assert db.query(EmployeeAlias).filter_by(employee_id=canon_id).count() == 2
    db.close()
    assert client.get("/aliases/unresolved", headers=admin).json() == []   # очередь пуста


def test_merge_collision_keeps_target_and_no_orphans(ctx):
    """Оба сотрудника имеют день в одном прогоне: при слиянии целевой день
    сохраняется, коллизия src удаляется, уникальный день src переносится,
    сирот не остаётся."""
    client, TS = ctx
    db = TS()
    canon = _emp(db, "Петров Пётр Петрович", True)
    ph = _emp(db, "Петров П", False)
    run = PipelineRun(status="done")
    db.add(run)
    db.flush()
    db.add_all([
        DayRecordRow(run_id=run.id, employee_id=canon.id, work_date="01.04.2026", worked_hours=8),
        DayRecordRow(run_id=run.id, employee_id=ph.id, work_date="01.04.2026", worked_hours=5),  # коллизия
        DayRecordRow(run_id=run.id, employee_id=ph.id, work_date="02.04.2026", worked_hours=7),  # уникальный
    ])
    db.commit()
    ph_id, canon_id = ph.id, canon.id
    aid = db.query(EmployeeAlias).filter_by(employee_id=ph_id, confirmed=False).one().id
    db.close()

    admin = tok(client, "admin", "admin")
    r = client.post(f"/aliases/{aid}/merge", json={"target_employee_id": canon_id}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["moved"]["day_records"] == 1            # перенёсся только 02.04

    db = TS()
    assert db.get(Employee, ph_id) is None
    assert db.query(DayRecordRow).count() == 2             # коллизия удалена, сирот нет
    d0 = db.query(DayRecordRow).filter_by(employee_id=canon_id, work_date="01.04.2026").one()
    assert float(d0.worked_hours) == 8.0                    # целевой день не перезаписан
    assert {d.work_date for d in db.query(DayRecordRow).filter_by(employee_id=canon_id)} == \
        {"01.04.2026", "02.04.2026"}
    db.close()


def test_confirm_as_new(ctx):
    client, TS = ctx
    db = TS()
    _emp(db, "Сидоров Сидор", False)
    db.commit()
    aid = db.query(EmployeeAlias).filter_by(confirmed=False).one().id
    db.close()
    admin = tok(client, "admin", "admin")
    assert len(client.get("/aliases/unresolved", headers=admin).json()) == 1
    assert client.post(f"/aliases/{aid}/confirm", headers=admin).status_code == 200
    assert client.get("/aliases/unresolved", headers=admin).json() == []


def test_alias_count(ctx):
    client, TS = ctx
    db = TS()
    _emp(db, "Тестов Тест", False)     # неподтверждённый
    _emp(db, "Иванов Иван", True)       # подтверждённый — не в счёте
    db.commit()
    db.close()
    admin = tok(client, "admin", "admin")
    assert client.get("/aliases/count", headers=admin).json()["unresolved"] == 1
    assert client.get("/aliases/count", headers=tok(client, "buh", "buh")).status_code == 403


def test_aliases_role_gating(ctx):
    client, _ = ctx
    assert client.get("/aliases/unresolved", headers=tok(client, "buh", "buh")).status_code == 403
    assert client.get("/aliases/unresolved", headers=tok(client, "ruk", "ruk")).status_code == 403
