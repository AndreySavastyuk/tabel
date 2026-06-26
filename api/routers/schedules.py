# -*- coding: utf-8 -*-
"""Графики и нормы. Чтение — всем; графики мутирует Кадры/Админ; нормы —
Кадры/Админ или Бухгалтер."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import get_current_user, require_role
from ..models import Schedule, ScheduleNorm
from ..schemas import (ScheduleIn, ScheduleNormIn, ScheduleNormOut, ScheduleOut)

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("", response_model=list[ScheduleOut])
def list_schedules(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(Schedule).order_by(Schedule.code)).all()


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role(Role.admin_hr))])
def create_schedule(body: ScheduleIn, db: Session = Depends(get_db)):
    if db.scalar(select(Schedule).where(Schedule.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "График с таким кодом уже есть")
    s = Schedule(**body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.patch("/{sched_id}", response_model=ScheduleOut,
              dependencies=[Depends(require_role(Role.admin_hr))])
def update_schedule(sched_id: int, body: ScheduleIn, db: Session = Depends(get_db)):
    s = db.get(Schedule, sched_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "График не найден")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@router.get("/{sched_id}/norms", response_model=list[ScheduleNormOut])
def list_norms(sched_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(
        select(ScheduleNorm).where(ScheduleNorm.schedule_id == sched_id)
        .order_by(ScheduleNorm.month)).all()


@router.put("/{sched_id}/norms", response_model=ScheduleNormOut,
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def upsert_norm(sched_id: int, body: ScheduleNormIn, db: Session = Depends(get_db)):
    """Создаёт или обновляет норму графика на месяц (YYYY-MM)."""
    if db.get(Schedule, sched_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "График не найден")
    norm = db.scalar(select(ScheduleNorm).where(
        ScheduleNorm.schedule_id == sched_id, ScheduleNorm.month == body.month))
    if norm is None:
        norm = ScheduleNorm(schedule_id=sched_id, month=body.month, norm_hours=body.norm_hours)
        db.add(norm)
    else:
        norm.norm_hours = body.norm_hours
    db.commit()
    db.refresh(norm)
    return norm
