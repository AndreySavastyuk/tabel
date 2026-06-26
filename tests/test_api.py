# -*- coding: utf-8 -*-
"""API-тесты Фазы 1: авторизация по ролям, гварды, скоуп отдела, редакция
денег, CRUD. Изолированная temp-БД, без влияния на рабочую tabel.db.

Запуск:  python -m pytest tests/test_api.py -q
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
from api.models import Department, Employee, Schedule, User


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = TS()
    d1 = Department(name="Цех 1")
    d2 = Department(name="Офис")
    db.add_all([d1, d2])
    db.flush()
    s1 = Schedule(code="5x2", shift_start="08:00", shift_len=8)
    db.add(s1)
    db.flush()
    db.add_all([
        Employee(full_name="Иванов И", normalized_name="Иванов И", department_id=d1.id,
                 schedule_id=s1.id, hourly_rate=500, lez_controlled=True),
        Employee(full_name="Петров П", normalized_name="Петров П", department_id=d2.id,
                 hourly_rate=600),
    ])
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
        User(username="buh", password_hash=security.hash_password("buh"), role=Role.accountant.value),
        User(username="ruk", password_hash=security.hash_password("ruk"),
             role=Role.dept_head.value, department_id=d1.id),
    ])
    db.commit()
    db.close()

    def override_db():
        s = TS()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(path)


def tok(client, u, p):
    r = client.post("/auth/login", data={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- auth ---
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_ok_and_bad(client):
    assert client.post("/auth/login", data={"username": "admin", "password": "admin"}).status_code == 200
    assert client.post("/auth/login", data={"username": "admin", "password": "x"}).status_code == 401


def test_me(client):
    r = client.get("/auth/me", headers=tok(client, "buh", "buh"))
    assert r.status_code == 200 and r.json()["role"] == "accountant"


def test_no_token_401(client):
    assert client.get("/employees").status_code == 401


# --- role guards ---
def test_department_mutation_roles(client):
    assert client.post("/departments", json={"name": "Новый"}, headers=tok(client, "admin", "admin")).status_code == 201
    assert client.post("/departments", json={"name": "Х"}, headers=tok(client, "buh", "buh")).status_code == 403
    assert client.post("/departments", json={"name": "Х"}, headers=tok(client, "ruk", "ruk")).status_code == 403
    # читать может любой авторизованный
    assert client.get("/departments", headers=tok(client, "ruk", "ruk")).status_code == 200


def test_norms_roles(client):
    sid = client.get("/schedules", headers=tok(client, "admin", "admin")).json()[0]["id"]
    body = {"month": "2026-04", "norm_hours": 175}
    assert client.put(f"/schedules/{sid}/norms", json=body, headers=tok(client, "buh", "buh")).status_code == 200
    assert client.put(f"/schedules/{sid}/norms", json=body, headers=tok(client, "ruk", "ruk")).status_code == 403


# --- employees: scoping + money redaction ---
def test_admin_sees_all_with_rate(client):
    r = client.get("/employees", headers=tok(client, "admin", "admin"))
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert any(e["hourly_rate"] == 500 for e in data)


def test_dept_head_scoped_and_redacted(client):
    r = client.get("/employees", headers=tok(client, "ruk", "ruk"))
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1 and data[0]["full_name"] == "Иванов И"   # только свой отдел
    assert data[0]["hourly_rate"] is None                          # ставка скрыта


def test_accountant_sees_rate(client):
    data = client.get("/employees", headers=tok(client, "buh", "buh")).json()
    assert any(e["hourly_rate"] == 600 for e in data)


def test_dept_head_cannot_see_foreign_employee(client):
    emps = client.get("/employees", headers=tok(client, "admin", "admin")).json()
    foreign = next(e for e in emps if e["full_name"] == "Петров П")
    r = client.get(f"/employees/{foreign['id']}", headers=tok(client, "ruk", "ruk"))
    assert r.status_code == 403


def test_accountant_can_only_change_rate(client):
    emps = client.get("/employees", headers=tok(client, "admin", "admin")).json()
    eid = emps[0]["id"]
    h = tok(client, "buh", "buh")
    assert client.patch(f"/employees/{eid}", json={"hourly_rate": 999}, headers=h).status_code == 200
    assert client.patch(f"/employees/{eid}", json={"full_name": "Хакер"}, headers=h).status_code == 403


def test_admin_create_employee(client):
    r = client.post("/employees", json={"full_name": "Сидоров С", "hourly_rate": 700},
                    headers=tok(client, "admin", "admin"))
    assert r.status_code == 201 and r.json()["normalized_name"] == "Сидоров С"


def test_dept_head_cannot_patch(client):
    emps = client.get("/employees", headers=tok(client, "admin", "admin")).json()
    r = client.patch(f"/employees/{emps[0]['id']}", json={"cabinet": "X"},
                     headers=tok(client, "ruk", "ruk"))
    assert r.status_code == 403
