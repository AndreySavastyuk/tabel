# -*- coding: utf-8 -*-
"""Разовый импорт справочников ЛЭЗ/*.xlsx в БД + сид праздников и пользователей.

Идемпотентно (можно перезапускать). Запуск из корня репозитория:
  python -m scripts.seed_from_excel [<workdir>]

<workdir> по умолчанию — корень проекта (где лежит папка ЛЭЗ/). Перед запуском
БД должна быть мигрирована: `alembic upgrade head`.
"""
import os
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.names import name_format
from engine.refdata import load_reference_data

from api import security
from api.config import settings
from api.constants import HolidayKind, Role
from api.holidays_ru import federal_holidays, transfers
from api.db import SessionLocal
from api.models import (Absence, Department, Employee, EmployeeAlias,
                        HolidayCalendar, Schedule, ScheduleNorm, User)

EMP_REF = "Справочник_сотрудников.xlsx"

# Дев-пользователи: (username, пароль, роль). Поменять пароли в проде!
DEV_USERS = [
    ("admin", "admin", Role.admin_hr),
    ("buh", "buh", Role.accountant),
    ("ruk", "ruk", Role.dept_head),     # отдел назначается ниже (первый по алфавиту)
]


def read_all_names(wp):
    """Все ФИО (name_format) из Справочник_сотрудников.xlsx."""
    path = os.path.join(wp, "ЛЭЗ", EMP_REF)
    names = set()
    if not os.path.exists(path):
        return names
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None) or ()
    fio_idx = 0
    for i, h in enumerate(header):
        if h and "фио" in str(h).strip().lower():
            fio_idx = i
            break
    for row in rows:
        if row and fio_idx < len(row) and row[fio_idx]:
            nm = name_format(str(row[fio_idx]).strip())
            if nm:
                names.add(nm)
    return names


def _get_or_create_department(db, name):
    d = db.query(Department).filter_by(name=name).one_or_none()
    if d is None:
        d = Department(name=name)
        db.add(d)
        db.flush()
    return d


def _get_or_create_schedule(db, code, ref):
    s = db.query(Schedule).filter_by(code=code).one_or_none()
    if s is None:
        s = Schedule(code=code)
        db.add(s)
    s.shift_start = ref.shift_start.get(code)
    s.shift_len = ref.shift_len.get(code)
    lunch = ref.lunch.get(code)
    s.lunch_start, s.lunch_end = (lunch if lunch else (None, None))
    db.flush()
    return s


def import_reference(db, wp):
    ref = load_reference_data(wp, name_normalizer=name_format)

    # 1) Отделы
    dept_names = set(ref.dept_by_name.values()) | {"Без отдела"}
    dept_ids = {n: _get_or_create_department(db, n).id for n in sorted(dept_names)}

    # 2) Графики + нормы
    codes = (set(ref.shift_start) | set(ref.shift_len) | set(ref.lunch)
             | {c for c, _ in ref.norms})
    sched_ids = {c: _get_or_create_schedule(db, c, ref).id for c in sorted(codes)}
    for (code, month), hours in ref.norms.items():
        sid = sched_ids[code]
        n = db.query(ScheduleNorm).filter_by(schedule_id=sid, month=month).one_or_none()
        if n is None:
            db.add(ScheduleNorm(schedule_id=sid, month=month, norm_hours=hours))
        else:
            n.norm_hours = hours

    # 3) Сотрудники (полный список из Справочника + имена из ref)
    names = read_all_names(wp) | set(ref.dept_by_name) | set(ref.schedule_by_name) \
        | set(ref.cabinet_by_name) | set(ref.fixed_times) | set(ref.lez_controlled)
    by_norm = {}
    for nm in sorted(names):
        emp = db.query(Employee).filter_by(normalized_name=nm).first()
        if emp is None:
            emp = Employee(full_name=nm, normalized_name=nm)
            db.add(emp)
            db.flush()
        emp.department_id = dept_ids.get(ref.dept(nm))
        emp.cabinet = ref.cabinet(nm)
        sc = ref.schedule(nm)
        emp.schedule_id = sched_ids.get(sc) if sc else None
        emp.fixed_time = ref.fixed_times.get(nm)
        emp.lez_controlled = ref.is_lez_controlled(nm)
        emp.arrives_by_car = ref.is_arrives_by_car(nm)
        by_norm[nm] = emp
        if not db.query(EmployeeAlias).filter_by(employee_id=emp.id, normalized_name=nm).first():
            db.add(EmployeeAlias(employee_id=emp.id, raw_name=nm, normalized_name=nm,
                                 source="manual", confidence=1.0, confirmed=True))

    # 4) Отсутствия (если заполнены)
    for nm, spans in ref.absences.items():
        emp = by_norm.get(nm) or db.query(Employee).filter_by(normalized_name=nm).first()
        if emp is None:
            continue
        for typ, d1, d2 in spans:
            exists = db.query(Absence).filter_by(
                employee_id=emp.id, type=typ, date_from=d1, date_to=d2).first()
            if not exists:
                db.add(Absence(employee_id=emp.id, type=typ, date_from=d1, date_to=d2,
                               status="approved"))
    return dept_ids


def seed_calendar(db, year_from=2025, year_to=2027):
    """Засев производственного календаря: федеральные праздники + официальные
    переносы (где известны). Сб/вс считаются автоматически и не хранятся."""
    existing = {d for (d,) in db.query(HolidayCalendar.cal_date).all()}
    added = 0

    def _add(d, kind):
        nonlocal added
        if d not in existing:
            db.add(HolidayCalendar(cal_date=d, kind=kind))
            existing.add(d)
            added += 1

    for y in range(year_from, year_to + 1):
        for d in federal_holidays(y):
            _add(d, HolidayKind.holiday.value)
        doff, work = transfers(y)
        for d in doff:
            _add(d, HolidayKind.dayoff.value)
        for d in work:
            _add(d, HolidayKind.workday_override.value)
    return added


def seed_users(db, dept_ids):
    # В проде НЕ заводим дев-юзеров со слабыми паролями (admin/admin и т.п.).
    # Создаём одного admin с паролем из TABEL_BOOTSTRAP_ADMIN_PASSWORD или падаем.
    if settings.is_prod:
        pw = os.environ.get("TABEL_BOOTSTRAP_ADMIN_PASSWORD")
        if not pw or len(pw) < 12:
            raise SystemExit(
                "TABEL_ENV=prod: отказ заводить дев-юзеров. Задайте "
                "TABEL_BOOTSTRAP_ADMIN_PASSWORD (>=12 символов) для создания "
                "начального admin, либо заводите пользователей вне сидера."
            )
        if db.query(User).filter_by(username="admin").one_or_none() is None:
            db.add(User(username="admin", password_hash=security.hash_password(pw),
                        role=Role.admin_hr.value))
        return  # никаких admin/admin, buh/buh, ruk/ruk в проде

    first_dept = min(dept_ids.values()) if dept_ids else None
    for username, pw, role in DEV_USERS:
        u = db.query(User).filter_by(username=username).one_or_none()
        if u is None:
            u = User(username=username, password_hash=security.hash_password(pw), role=role.value)
            db.add(u)
        u.role = role.value
        if role == Role.dept_head:
            u.department_id = first_dept


def main():
    wp = sys.argv[1] if len(sys.argv) > 1 else settings.workdir
    db = SessionLocal()
    try:
        dept_ids = import_reference(db, wp)
        cal = seed_calendar(db)
        seed_users(db, dept_ids)
        db.commit()
        print(f"Импорт готов: отделов={db.query(Department).count()}, "
              f"графиков={db.query(Schedule).count()}, норм={db.query(ScheduleNorm).count()}, "
              f"сотрудников={db.query(Employee).count()}, "
              f"отсутствий={db.query(Absence).count()}, календарь+={cal}, "
              f"пользователей={db.query(User).count()}")
        if not settings.is_prod:
            print("Дев-логины:", ", ".join(f"{u}/{p} ({r.value})" for u, p, r in DEV_USERS))
    finally:
        db.close()


if __name__ == "__main__":
    main()
