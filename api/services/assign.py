# -*- coding: utf-8 -*-
"""Массовое назначение отделов/графиков/кабинетов из загруженного листа
«ФИО → Отдел/График/Кабинет».

preview() — read-only: парсит лист, нечётко сопоставляет ФИО с существующими
сотрудниками (engine.names.match_score) и классифицирует строки
(matched/ambiguous/not_found). apply() — мутация по подтверждённым строкам:
get-or-create отдел по имени и график по коду, проставляет поля сотрудникам."""
import openpyxl
from sqlalchemy.orm import Session

from engine.names import match_score, name_format

from ..models import Department, Employee, Schedule

# Порог «близких» кандидатов: если второй кандидат в пределах этого от лидера —
# строка считается неоднозначной (несколько однофамильцев).
_AMBIGUITY = 0.15


def _col(header, *subs):
    for i, h in enumerate(header):
        for s in subs:
            if s in h:
                return i
    return None


def parse_sheet(path: str) -> list[dict]:
    """Читает xlsx: ищет колонки ФИО/Отдел/График/Кабинет по подстроке заголовка."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(h or "").strip().lower().replace("ё", "е") for h in (next(rows, ()) or ())]
    i_fio = _col(header, "фио", "сотрудник")
    i_dept = _col(header, "отдел", "подразделение")
    i_sched = _col(header, "график")
    i_cab = _col(header, "кабинет", "каб")
    if i_fio is None:
        return []

    def cell(r, i):
        if i is None or i >= len(r) or r[i] is None:
            return None
        v = str(r[i]).strip()
        return v or None

    out = []
    for r in rows:
        if not r:
            continue
        fio = cell(r, i_fio)
        if not fio:
            continue
        out.append({
            "raw_name": name_format(fio),
            "department_name": cell(r, i_dept),
            "schedule_code": cell(r, i_sched),
            "cabinet": cell(r, i_cab),
        })
    return out


def preview(db: Session, parsed: list[dict]) -> list[dict]:
    employees = db.query(Employee).all()
    out = []
    for idx, row in enumerate(parsed, start=1):
        scored = [(e, match_score(row["raw_name"], e.normalized_name)) for e in employees]
        scored = sorted([es for es in scored if es[1] > 0], key=lambda es: -es[1])
        item = {
            "row": idx,
            "raw_name": row["raw_name"],
            "department_name": row["department_name"],
            "schedule_code": row["schedule_code"],
            "cabinet": row["cabinet"],
            "status": "not_found",
            "match": None,
            "candidates": [],
        }
        if scored:
            top = scored[0][1]
            close = [es for es in scored if es[1] >= top - _AMBIGUITY]
            if len(close) == 1:
                e, sc = scored[0]
                item["status"] = "matched"
                item["match"] = {"employee_id": e.id, "full_name": e.full_name,
                                 "department_id": e.department_id, "score": sc}
            else:
                item["status"] = "ambiguous"
                item["candidates"] = [
                    {"employee_id": e.id, "full_name": e.full_name,
                     "department_id": e.department_id, "score": sc}
                    for e, sc in close[:5]]
        out.append(item)
    return out


def _get_or_create_department(db, name, created):
    d = db.query(Department).filter_by(name=name).one_or_none()
    if d is None:
        d = Department(name=name)
        db.add(d)
        db.flush()
        created.append(name)
    return d


def _get_or_create_schedule(db, code, created):
    s = db.query(Schedule).filter_by(code=code).one_or_none()
    if s is None:
        s = Schedule(code=code)
        db.add(s)
        db.flush()
        created.append(code)
    return s


def apply(db: Session, items: list) -> dict:
    """Проставляет отдел/график/кабинет сотрудникам по подтверждённым строкам.
    Отделы/графики, которых нет, создаются по имени/коду."""
    depts_created: list[str] = []
    scheds_created: list[str] = []
    updated = 0
    for it in items:
        emp = db.get(Employee, it.employee_id)
        if emp is None:
            continue
        touched = False
        if it.department_name:
            emp.department_id = _get_or_create_department(db, it.department_name, depts_created).id
            touched = True
        if it.schedule_code:
            emp.schedule_id = _get_or_create_schedule(db, it.schedule_code, scheds_created).id
            touched = True
        if it.cabinet:
            emp.cabinet = it.cabinet
            touched = True
        if touched:
            updated += 1
    db.commit()
    return {
        "updated": updated,
        "departments_created": sorted(set(depts_created)),
        "schedules_created": sorted(set(scheds_created)),
    }
