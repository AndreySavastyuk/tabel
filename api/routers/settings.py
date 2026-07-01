# -*- coding: utf-8 -*-
"""Настройки (только Кадры/Админ): кабинеты (переименование) и пороги расчёта
(model.THRESHOLDS, хранятся в app_settings['thresholds'] и применяются в прогоне).
Отделы редактируются через /departments, графики — через /schedules."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.model import THRESHOLDS

from ..constants import Role
from ..db import get_db
from ..deps import require_role
from ..models import AppSetting, Employee
from ..schemas import CabinetOut, CabinetRename, ThresholdItem, ThresholdsIn

router = APIRouter(prefix="/settings", tags=["settings"],
                   dependencies=[Depends(require_role(Role.admin_hr))])

THRESHOLDS_KEY = "thresholds"

# Человекочитаемые подписи/единицы порогов (порядок — как в THRESHOLDS).
_META = {
    "time_mismatch_min": ("Расхождение времён ЛЭЗ ↔ внутренняя система", "мин"),
    "implausible_hours_max": ("Максимум правдоподобных часов за день", "ч"),
    "implausible_hours_min": ("Отработано ≤ этого — подозрительно", "ч"),
    "lateness_grace_min": ("Грейс опоздания (не считать опозданием)", "мин"),
    "reentry_gap_min": ("Разрыв выход→вход на проходной (ЛЭЗ), один эпизод", "мин"),
    "away_daily_min": ("Суммарные отлучки за день → флаг «вне территории»", "мин"),
    "shift_gap_min": ("Перерыв, начинающий новую смену", "мин"),
    "max_shift_min": ("Максимальная длительность смены", "мин"),
}


def _effective(db: Session) -> list[ThresholdItem]:
    row = db.get(AppSetting, THRESHOLDS_KEY)
    saved = dict(row.value) if row and isinstance(row.value, dict) else {}
    items = []
    for key, default in THRESHOLDS.items():
        label, unit = _META.get(key, (key, ""))
        items.append(ThresholdItem(key=key, label=label, unit=unit,
                                   value=float(saved.get(key, default)), default=float(default)))
    return items


@router.get("/thresholds", response_model=list[ThresholdItem])
def get_thresholds(db: Session = Depends(get_db)):
    return _effective(db)


@router.put("/thresholds", response_model=list[ThresholdItem])
def put_thresholds(body: ThresholdsIn, db: Session = Depends(get_db)):
    # Сохраняем только известные ключи, приводя к типу дефолта (int/float).
    clean = {}
    for key, default in THRESHOLDS.items():
        if key in body.values:
            v = body.values[key]
            clean[key] = int(v) if isinstance(default, int) else float(v)
    row = db.get(AppSetting, THRESHOLDS_KEY)
    if row is None:
        db.add(AppSetting(key=THRESHOLDS_KEY, value=clean))
    else:
        row.value = clean
    db.commit()
    return _effective(db)


@router.get("/cabinets", response_model=list[CabinetOut])
def list_cabinets(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Employee.cabinet, func.count())
        .where(Employee.cabinet.isnot(None))
        .group_by(Employee.cabinet).order_by(Employee.cabinet)).all()
    return [CabinetOut(name=name, count=cnt) for name, cnt in rows]


@router.post("/cabinets/rename")
def rename_cabinet(body: CabinetRename, db: Session = Depends(get_db)):
    """Переименовать кабинет у всех сотрудников. Пустое новое имя — очистить."""
    new = (body.new_name or "").strip() or None
    emps = db.scalars(select(Employee).where(Employee.cabinet == body.old_name)).all()
    for e in emps:
        e.cabinet = new
    db.commit()
    return {"updated": len(emps)}
