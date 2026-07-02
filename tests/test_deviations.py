# -*- coding: utf-8 -*-
"""Очередь отклонений: стабильный дедуп между прогонами (сохранение статуса),
is_present при исчезновении, нормализация re-entry, API список/счётчик/PATCH/
bulk/скоуп руководителя. Синтетический — на чистом клоне/CI.

Запуск:  python -m pytest tests/test_deviations.py -q
"""
import os
import sys
import tempfile
from datetime import date, datetime

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
from api.models import (Department, DayRecordRow, DeviationItem, Employee, PipelineRun, User)
from api.services import ingestion, time_adjust
from engine import model


def _dr(name, date, devs, dept="Цех", lez_events=None):
    dr = model.DayRecord(name=name, date=date)
    dr.dept = dept
    dr.deviations = devs
    dr.lez_events = lez_events or []      # сырые отметки ЛЭЗ (для «выхода с территории»)
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


def test_sync_reentry_from_lez_events(ctx):
    """«Выход с территории» считается из сырых отметок ЛЭЗ (сумма отлучек за
    день), а НЕ из строки движка. Строка движка в deviations игнорируется."""
    _, TS, ids = ctx
    eid = ids["E"]
    db = TS()
    rid = _run(db)
    lez = [("12:00", "Выход"), ("12:50", "Вход")]      # 50 мин вне территории
    ingestion._sync_deviations(
        db, rid, {"E": [_dr("E", "10.04.2026", ["Выход с территории 999 мин (x)"], lez_events=lez)]},
        {"E": eid})
    db.commit()
    it = db.scalars(select(DeviationItem)).one()        # ровно один (строка движка не плодит второй)
    assert it.dev_code == "REENTRY_GAP"
    assert it.away_minutes == 50
    assert it.detail and "12:00→12:50" in it.detail and "50 мин" in it.detail
    db.close()


def test_away_daily_sum_threshold(ctx):
    """Несколько КОРОТКИХ отлучек суммируются: > 30 мин суммарно → флаг;
    суммарно <= 30 мин → отклонения нет (в отличие от порога на эпизод)."""
    _, TS, ids = ctx
    db = TS()
    rid = _run(db)
    # три выхода по 15 мин = 45 мин суммарно (> 30) → флаг
    big = [("10:00", "Выход"), ("10:15", "Вход"),
           ("12:00", "Выход"), ("12:15", "Вход"),
           ("15:00", "Выход"), ("15:15", "Вход")]
    ingestion._sync_deviations(db, rid, {"E": [_dr("E", "10.04.2026", [], lez_events=big)]}, {"E": ids["E"]})
    # два выхода по 10 мин = 20 мин суммарно (<= 30) → нет флага
    small = [("10:00", "Выход"), ("10:10", "Вход"), ("12:00", "Выход"), ("12:10", "Вход")]
    ingestion._sync_deviations(db, rid, {"F": [_dr("F", "10.04.2026", [], dept="Офис", lez_events=small)]}, {"F": ids["F"]})
    db.commit()
    items = {it.employee_id: it for it in db.scalars(select(DeviationItem))}
    assert ids["E"] in items and items[ids["E"]].away_minutes == 45
    assert ids["F"] not in items
    db.close()


def test_away_threshold_configurable(ctx):
    """Порог дневной суммы отлучек берётся из настроек (away_daily_min)."""
    _, TS, ids = ctx
    db = TS()
    rid = _run(db)
    lez = [("10:00", "Выход"), ("10:40", "Вход")]      # 40 мин вне территории
    recs = {"E": [_dr("E", "10.04.2026", [], lez_events=lez)]}
    # порог 60 мин — 40 мин не дотягивают, отклонения нет
    ingestion._sync_deviations(db, rid, recs, {"E": ids["E"]}, away_daily_min=60)
    db.commit()
    assert db.scalars(select(DeviationItem)).first() is None
    # порог 30 мин — те же 40 мин уже флагуются
    ingestion._sync_deviations(db, rid, recs, {"E": ids["E"]}, away_daily_min=30)
    db.commit()
    it = db.scalars(select(DeviationItem)).one()
    assert it.dev_code == "REENTRY_GAP" and it.away_minutes == 40
    db.close()


def test_vehicle_strips_only_internal(ctx):
    """У сотрудника с «личным транспортом» ONLY_INTERNAL вырезается до записи
    (въехал на машине — отметки ЛЭЗ законно нет); остальные коды и другие
    сотрудники не затронуты."""
    _, TS, ids = ctx
    db = TS()
    db.get(Employee, ids["E"]).arrives_by_car = True
    db.commit()
    recs = {"E": [_dr("E", "10.04.2026", ["ONLY_INTERNAL", "MISSING_EXIT"])],
            "F": [_dr("F", "10.04.2026", ["ONLY_INTERNAL"], dept="Офис")]}
    ingestion.strip_vehicle_deviations(db, recs, {"E": ids["E"], "F": ids["F"]})
    assert recs["E"][0].deviations == ["MISSING_EXIT"]
    assert recs["F"][0].deviations == ["ONLY_INTERNAL"]
    db.close()


def test_dismissed_strips_from_dismissal_date(ctx):
    """С даты увольнения отклонения дня вырезаются (сдача пропуска ломает
    отметки): и коды движка, и сырые отметки ЛЭЗ (дневная сумма отлучек).
    Дни ДО даты увольнения не трогаются."""
    _, TS, ids = ctx
    db = TS()
    db.get(Employee, ids["E"]).dismissed_at = date(2026, 4, 10)
    db.commit()
    lez = [("12:00", "Выход"), ("13:00", "Вход")]
    recs = {"E": [_dr("E", "09.04.2026", ["MISSING_EXIT"]),
                  _dr("E", "10.04.2026", ["MISSING_EXIT", "ONLY_INTERNAL"], lez_events=lez)]}
    ingestion.strip_dismissed_days(db, recs, {"E": ids["E"]})
    assert recs["E"][0].deviations == ["MISSING_EXIT"]     # до увольнения — не тронут
    assert recs["E"][1].deviations == [] and recs["E"][1].lez_events == []
    db.close()


def test_dismissed_api_flow(ctx):
    """PATCH dismissed_at гасит is_active и скрывает сотрудника из списка по
    умолчанию; include_dismissed=true возвращает; сброс даты восстанавливает."""
    client, _, ids = ctx
    admin = tok(client, "admin", "admin")
    r = client.patch(f"/employees/{ids['E']}", json={"dismissed_at": "2026-04-10"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["dismissed_at"] == "2026-04-10" and r.json()["is_active"] is False
    names = {e["full_name"] for e in client.get("/employees", headers=admin).json()}
    assert "E" not in names and "F" in names               # уволенный скрыт
    shown = {e["full_name"] for e in
             client.get("/employees?include_dismissed=true", headers=admin).json()}
    assert "E" in shown                                     # по флагу — показан
    r2 = client.patch(f"/employees/{ids['E']}", json={"dismissed_at": None}, headers=admin)
    assert r2.json()["dismissed_at"] is None and r2.json()["is_active"] is True


def test_vehicle_flag_patch_and_filter(ctx):
    """Флаг «личный транспорт» правится через PATCH /employees/{id};
    ?vehicle_only=true отдаёт только отмеченных."""
    client, _, ids = ctx
    admin = tok(client, "admin", "admin")
    r = client.patch(f"/employees/{ids['E']}", json={"arrives_by_car": True}, headers=admin)
    assert r.status_code == 200 and r.json()["arrives_by_car"] is True
    names = {e["full_name"] for e in
             client.get("/employees?vehicle_only=true", headers=admin).json()}
    assert names == {"E"}


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


def _reentry_item(eid, dept_id, rid, away=90, deduct=None, decision="pending", date="10.04.2026"):
    return DeviationItem(dedup_key=f"{eid}|{date}|REENTRY_GAP", run_id=rid, employee_id=eid,
                         department_id=dept_id, work_date=date, dev_code="REENTRY_GAP",
                         away_minutes=away, deduct_minutes=deduct, time_decision=decision,
                         status="new", is_present=True,
                         first_seen_at=datetime(2026, 5, 1), last_seen_at=datetime(2026, 5, 1))


def test_time_decision_gating_and_default(ctx):
    """Вычет времени: доступен кадрам/бухгалтеру (не руководителю); по умолчанию
    вычитается вся сумма отлучек; сумму можно переопределить и решение — снять."""
    client, TS, ids = ctx
    db = TS()
    rid = _run(db)
    db.add(_reentry_item(ids["E"], ids["dept"], rid, away=90))
    db.commit()
    did = db.scalars(select(DeviationItem)).one().id
    db.close()
    admin = tok(client, "admin", "admin")
    ruk = tok(client, "ruk", "ruk")
    # руководителю нельзя решать вычет (влияет на зарплату)
    assert client.patch(f"/deviations/{did}", json={"time_decision": "deducted"}, headers=ruk).status_code == 403
    # кадры: вычет по умолчанию = вся сумма отлучек
    r = client.patch(f"/deviations/{did}", json={"time_decision": "deducted"}, headers=admin)
    assert r.status_code == 200 and r.json()["time_decision"] == "deducted" and r.json()["deduct_minutes"] == 90
    # переопределение суммы вычета
    assert client.patch(f"/deviations/{did}", json={"deduct_minutes": 60}, headers=admin).json()["deduct_minutes"] == 60
    # снять вычет — минуты обнуляются
    r3 = client.patch(f"/deviations/{did}", json={"time_decision": "counted"}, headers=admin)
    assert r3.json()["time_decision"] == "counted" and r3.json()["deduct_minutes"] is None


def test_time_adjust_deduction_math(ctx):
    """deduction_map / run_applied_by_employee / apply_day: дневной вычет
    ограничен часами дня, свод = сумма дневных вычетов."""
    _, TS, ids = ctx
    db = TS()
    rid = _run(db)
    db.add(DayRecordRow(run_id=rid, employee_id=ids["E"], work_date="10.04.2026",
                        entry="08:00", exit="17:00", worked_hours=8.0))
    db.add(_reentry_item(ids["E"], ids["dept"], rid, away=90, deduct=90, decision="deducted"))
    db.commit()
    assert time_adjust.deduction_map(db)[(ids["E"], "10.04.2026")] == 90
    assert time_adjust.run_applied_by_employee(db, rid)[ids["E"]] == 1.5   # 90 мин, worked 8 ч
    assert time_adjust.apply_day(8.0, 90) == 6.5
    assert time_adjust.apply_day(1.0, 90) == 0.0                            # вычет не уводит в минус
    db.close()


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
