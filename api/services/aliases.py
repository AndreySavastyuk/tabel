# -*- coding: utf-8 -*-
"""Разбор ФИО: очередь неподтверждённых алиасов (плейсхолдеры, заведённые
ингестом для нераспознанных имён), подсказка кандидатов (нечёткое сопоставление
engine.names) и слияние дубля сотрудника в реального с переносом всех данных."""
from sqlalchemy.orm import Session

from engine.names import match_score

from ..models import (AccessEvent, Absence, DayRecordRow, Employee,
                      EmployeeAlias, PeriodSummary)


def list_unresolved(db: Session, limit: int = 500) -> list[dict]:
    """Неподтверждённые алиасы + до 5 кандидатов-сотрудников по похожести ФИО."""
    aliases = (db.query(EmployeeAlias)
               .filter(EmployeeAlias.confirmed.is_(False))
               .order_by(EmployeeAlias.id).limit(limit).all())
    if not aliases:
        return []
    employees = db.query(Employee).all()
    # Сотрудники, у которых есть подтверждённый алиас — «канонические» (из
    # справочника или уже разобранные); их предпочтительно показывать целью слияния.
    canonical = {row[0] for row in db.query(EmployeeAlias.employee_id)
                 .filter(EmployeeAlias.confirmed.is_(True)).all()}

    out = []
    for a in aliases:
        cands = []
        for e in employees:
            if e.id == a.employee_id:
                continue
            sc = match_score(a.normalized_name, e.normalized_name)
            if sc > 0:
                cands.append((e, sc))
        # сначала по похожести, при равенстве — канонические выше
        cands.sort(key=lambda es: (-es[1], es[0].id not in canonical))
        out.append({
            "id": a.id,
            "employee_id": a.employee_id,
            "raw_name": a.raw_name,
            "normalized_name": a.normalized_name,
            "source": a.source,
            "candidates": [{
                "employee_id": e.id,
                "full_name": e.full_name,
                "department_id": e.department_id,
                "score": sc,
                "canonical": e.id in canonical,
            } for e, sc in cands[:5]],
        })
    return out


def confirm_alias(db: Session, alias_id: int) -> EmployeeAlias:
    """Подтвердить алиас как отдельного (нового) сотрудника."""
    a = db.get(EmployeeAlias, alias_id)
    if a is None:
        raise LookupError("Алиас не найден")
    a.confirmed = True
    if a.confidence is None or float(a.confidence) < 1.0:
        a.confidence = 1.0
    db.commit()
    return a


def merge_employee(db: Session, src_id: int, target_id: int) -> dict:
    """Слить сотрудника src в target: перенести все данные, перенести/подтвердить
    алиасы, удалить дубль src. Возвращает счётчики перенесённого."""
    if src_id == target_id:
        raise ValueError("Нельзя объединить сотрудника с самим собой")
    src = db.get(Employee, src_id)
    target = db.get(Employee, target_id)
    if src is None or target is None:
        raise LookupError("Сотрудник не найден")

    moved = {"day_records": 0, "periods": 0, "events": 0, "absences": 0, "aliases": 0}

    # DayRecordRow: UniqueConstraint(run_id, employee_id, work_date) —
    # коллизии (тот же прогон+дата уже есть у target) у src удаляем.
    tgt_days = {(r.run_id, r.work_date)
                for r in db.query(DayRecordRow).filter_by(employee_id=target_id).all()}
    for r in db.query(DayRecordRow).filter_by(employee_id=src_id).all():
        if (r.run_id, r.work_date) in tgt_days:
            db.delete(r)
        else:
            r.employee_id = target_id
            moved["day_records"] += 1

    # PeriodSummary: UniqueConstraint(run_id, employee_id).
    tgt_runs = {r.run_id for r in db.query(PeriodSummary).filter_by(employee_id=target_id).all()}
    for r in db.query(PeriodSummary).filter_by(employee_id=src_id).all():
        if r.run_id in tgt_runs:
            db.delete(r)
        else:
            r.employee_id = target_id
            moved["periods"] += 1

    # AccessEvent / Absence: без ограничений уникальности — переносим все.
    for r in db.query(AccessEvent).filter_by(employee_id=src_id).all():
        r.employee_id = target_id
        moved["events"] += 1
    for r in db.query(Absence).filter_by(employee_id=src_id).all():
        r.employee_id = target_id
        moved["absences"] += 1

    # Алиасы: переносим через relationship (cascade delete-orphan), дубли по
    # normalized_name удаляем, перенесённые помечаем confirmed.
    tgt_norms = {a.normalized_name for a in target.aliases}
    for a in list(src.aliases):
        if a.normalized_name in tgt_norms:
            db.delete(a)
        else:
            a.employee = target
            a.confirmed = True
            tgt_norms.add(a.normalized_name)
            moved["aliases"] += 1

    db.flush()
    db.delete(src)
    db.commit()
    return {"merged_into": target_id, "moved": moved}
