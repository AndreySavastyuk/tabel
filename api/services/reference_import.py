# -*- coding: utf-8 -*-
"""Импорт справочников из загруженного Excel в БД (через UI / API).

Переиспользует scripts.seed_from_excel.import_reference: раскладывает загруженный
файл во временную ЛЭЗ/<каноническое имя> и прогоняет тот же идемпотентный импорт,
что и CLI-сидер. Так UI-загрузка и сидер используют ровно одну логику разбора
(engine.refdata.load_reference_data с нечётким сопоставлением заголовков)."""
import os
import shutil
import tempfile

from sqlalchemy.orm import Session

from engine.refdata import ABSENCE_FILE, EMP_REF_FILE, NORMS_FILE, TRIP_FILE

from ..constants import ReferenceKind
from ..models import Absence, Department, Employee, Schedule, ScheduleNorm

_KIND_FILE = {
    ReferenceKind.employees: EMP_REF_FILE,
    ReferenceKind.norms: NORMS_FILE,
    ReferenceKind.absences: ABSENCE_FILE,
    ReferenceKind.trips: TRIP_FILE,
}


def reference_counts(db: Session) -> dict:
    """Текущие итоги справочников в БД."""
    return {
        "departments": db.query(Department).count(),
        "schedules": db.query(Schedule).count(),
        "norms": db.query(ScheduleNorm).count(),
        "employees": db.query(Employee).count(),
        "absences": db.query(Absence).count(),
    }


def import_reference_upload(db: Session, kind: ReferenceKind, src_path: str) -> dict:
    """Импортирует один справочный xlsx в БД (идемпотентно, upsert).

    Возвращает {'before': counts, 'after': counts}. Бросает на нечитаемом файле —
    роутер транслирует это в 400."""
    # Отложенный импорт: scripts.seed_from_excel тянет весь сидер; держим связь
    # api<-scripts локальной и ленивой.
    from scripts.seed_from_excel import import_reference

    before = reference_counts(db)
    wp = tempfile.mkdtemp(prefix="ref_import_")
    try:
        lez = os.path.join(wp, "ЛЭЗ")
        os.makedirs(lez, exist_ok=True)
        shutil.copy(src_path, os.path.join(lez, _KIND_FILE[kind]))
        import_reference(db, wp)   # читает wp/ЛЭЗ/*, upsert в БД (не коммитит)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        shutil.rmtree(wp, ignore_errors=True)
    return {"before": before, "after": reference_counts(db)}
