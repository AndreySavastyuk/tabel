# -*- coding: utf-8 -*-
"""Тесты производственного календаря: CRUD + гейтинг, засев праздников РФ,
влияние праздника/переноса на число рабочих дней (через weekend_fn).

Запуск:  python -m pytest tests/test_calendar.py -q
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

from engine import compute
from engine.calendar import make_calendar_weekend_fn

from api import security
from api.constants import Role
from api.db import Base, get_db
from api.main import app
from api.models import User
from api.services.refdata_from_db import load_calendar


@pytest.fixture()
def env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    db.add_all([
        User(username="admin", password_hash=security.hash_password("admin"), role=Role.admin_hr.value),
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


def test_calendar_crud_and_gating(env):
    client, _ = env
    admin = tok(client, "admin", "admin")
    # добавить праздник
    assert client.put("/calendar", json={"cal_date": "2026-04-15", "kind": "holiday"}, headers=admin).status_code == 200
    got = client.get("/calendar?year=2026", headers=admin).json()
    assert any(e["cal_date"] == "2026-04-15" and e["kind"] == "holiday" for e in got)
    # перенос (рабочая суббота) — upsert по дате
    assert client.put("/calendar", json={"cal_date": "2026-04-18", "kind": "workday_override"}, headers=admin).status_code == 200
    # удалить
    assert client.delete("/calendar/2026-04-15", headers=admin).status_code == 204
    assert not any(e["cal_date"] == "2026-04-15" for e in client.get("/calendar?year=2026", headers=admin).json())
    # гейтинг
    ruk = tok(client, "ruk", "ruk")
    assert client.put("/calendar", json={"cal_date": "2026-05-01", "kind": "holiday"}, headers=ruk).status_code == 403
    assert client.delete("/calendar/2026-04-18", headers=ruk).status_code == 403
    assert client.post("/calendar/seed?year=2026", headers=ruk).status_code == 403


def test_seed_federal(env):
    client, _ = env
    admin = tok(client, "admin", "admin")
    r = client.post("/calendar/seed?year=2026", headers=admin)
    # 14 праздников + 4 официальных переноса 2026 (9 янв, 9 мар, 11 мая, 31 дек)
    assert r.status_code == 200 and r.json()["added"] == 18 and r.json()["transfers"] == 4
    # повторно — 0 (идемпотентно)
    assert client.post("/calendar/seed?year=2026", headers=admin).json()["added"] == 0
    got = client.get("/calendar?year=2026", headers=admin).json()
    assert len(got) == 18
    assert sum(e["kind"] == "holiday" for e in got) == 14
    assert sum(e["kind"] == "dayoff" for e in got) == 4


def test_holiday_and_override_affect_working_days(env):
    client, TS = env
    admin = tok(client, "admin", "admin")
    span = (date(2026, 4, 1), date(2026, 4, 30))

    db = TS()
    wf0 = make_calendar_weekend_fn(*load_calendar(db))
    base = compute.count_working_days(span, wf0)        # только сб/вс
    db.close()

    client.put("/calendar", json={"cal_date": "2026-04-15", "kind": "holiday"}, headers=admin)  # среда → праздник
    db = TS()
    wf1 = make_calendar_weekend_fn(*load_calendar(db))
    db.close()
    assert wf1("15.04.2026") is True
    assert compute.count_working_days(span, wf1) == base - 1

    client.put("/calendar", json={"cal_date": "2026-04-18", "kind": "workday_override"}, headers=admin)  # суббота → рабочая
    db = TS()
    wf2 = make_calendar_weekend_fn(*load_calendar(db))
    db.close()
    assert wf2("18.04.2026") is False
    assert compute.count_working_days(span, wf2) == base     # -1 праздник +1 суббота


def test_monthly_norms_pure():
    from api.services.calendar_norms import monthly_norms
    n = monthly_norms([], [], [], 2026)
    apr = next(x for x in n if x["month"] == "2026-04")
    assert apr["work_days"] == 22 and apr["norm_5x2"] == 176.0   # 22 будних × 8
    assert apr["short_days"] == 0

    # 01.05.2026 (пт) — праздник: 30.04 (чт) становится предпраздничным (−1 ч)
    n2 = monthly_norms([date(2026, 5, 1)], [], [], 2026)
    apr2 = next(x for x in n2 if x["month"] == "2026-04")
    assert apr2["norm_5x2"] == 175.0 and apr2["short_days"] == 1

    # перенесённый выходной (dayoff) — нерабочий, но НЕ сокращает предыдущий день
    n3 = monthly_norms([], [date(2026, 12, 31)], [], 2026)
    dec = next(x for x in n3 if x["month"] == "2026-12")
    dec0 = next(x for x in n if x["month"] == "2026-12")
    assert dec["work_days"] == dec0["work_days"] - 1             # 31.12 стал выходным
    assert dec["short_days"] == 0                                # 30.12 НЕ сокращён


def test_official_2026_norms():
    """Сверка с официальным производственным календарём РФ 2026 (КонсультантПлюс)."""
    from api.holidays_ru import federal_holidays, transfers
    from api.services.calendar_norms import monthly_norms
    doff, work = transfers(2026)
    n = {x["month"]: x for x in monthly_norms(federal_holidays(2026), doff, work, 2026)}
    expect = {  # месяц: (рабочих дней, норма часов 40ч-недели)
        "2026-01": (15, 120.0), "2026-02": (19, 152.0), "2026-03": (21, 168.0),
        "2026-04": (22, 175.0), "2026-05": (19, 151.0), "2026-06": (21, 167.0),
        "2026-07": (23, 184.0), "2026-08": (21, 168.0), "2026-09": (22, 176.0),
        "2026-10": (22, 176.0), "2026-11": (20, 159.0), "2026-12": (22, 176.0),
    }
    for mk, (wd, hrs) in expect.items():
        assert n[mk]["work_days"] == wd, (mk, "дней", n[mk]["work_days"], "ожид", wd)
        assert n[mk]["norm_5x2"] == hrs, (mk, "часов", n[mk]["norm_5x2"], "ожид", hrs)
    assert sum(x["work_days"] for x in n.values()) == 247        # офиц. итог 2026
    assert n["2026-12"]["short_days"] == 0                       # 31.12 — выходной, не сокращённый


def test_norms_endpoint(env):
    client, _ = env
    r = client.get("/calendar/norms?year=2026", headers=tok(client, "admin", "admin"))
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 12
    assert all({"month", "work_days", "short_days", "norm_5x2"} <= set(x) for x in data)
