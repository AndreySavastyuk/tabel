# -*- coding: utf-8 -*-
"""Производственный календарь: праздники и переносы (рабочие субботы). Сб/вс
вычисляются автоматически и в БД не хранятся. Чтение — всем; правка — Кадры."""
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import get_current_user, require_role
from ..holidays_ru import federal_holidays, transfers
from ..models import HolidayCalendar
from ..schemas import CalendarEntryIn, CalendarEntryOut, CalendarNorm
from ..services.calendar_norms import monthly_norms_db

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/norms", response_model=list[CalendarNorm])
def calendar_norms(year: int = Query(...), db: Session = Depends(get_db),
                   _=Depends(get_current_user)):
    """Помесячные нормы часов: 5/2 (8ч, с предпраздничным −1ч) и 3/3 (12ч)."""
    return monthly_norms_db(db, year)


@router.get("", response_model=list[CalendarEntryOut])
def list_calendar(year: int = Query(...), db: Session = Depends(get_db),
                  _=Depends(get_current_user)):
    return db.scalars(
        select(HolidayCalendar)
        .where(HolidayCalendar.cal_date >= date(year, 1, 1),
               HolidayCalendar.cal_date <= date(year, 12, 31),
               HolidayCalendar.kind != "weekend")
        .order_by(HolidayCalendar.cal_date)).all()


@router.put("", response_model=CalendarEntryOut,
            dependencies=[Depends(require_role(Role.admin_hr))])
def upsert_entry(body: CalendarEntryIn, db: Session = Depends(get_db)):
    row = db.scalar(select(HolidayCalendar).where(HolidayCalendar.cal_date == body.cal_date))
    if row is None:
        row = HolidayCalendar(cal_date=body.cal_date, kind=body.kind.value, note=body.note)
        db.add(row)
    else:
        row.kind = body.kind.value
        row.note = body.note
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{cal_date}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role(Role.admin_hr))])
def delete_entry(cal_date: date, db: Session = Depends(get_db)):
    row = db.scalar(select(HolidayCalendar).where(HolidayCalendar.cal_date == cal_date))
    if row:
        db.delete(row)
        db.commit()


@router.post("/seed", dependencies=[Depends(require_role(Role.admin_hr))])
def seed_year(year: int = Query(...), db: Session = Depends(get_db)):
    """Засеять производственный календарь за год: федеральные праздники +
    официальные переносы (если известны для года; иначе только праздники)."""
    existing = {d for (d,) in db.execute(select(HolidayCalendar.cal_date))}
    added = 0

    def _add(d, kind):
        nonlocal added
        if d not in existing:
            db.add(HolidayCalendar(cal_date=d, kind=kind))
            existing.add(d)
            added += 1

    for d in federal_holidays(year):
        _add(d, "holiday")
    doff, work = transfers(year)
    for d in doff:
        _add(d, "dayoff")
    for d in work:
        _add(d, "workday_override")
    db.commit()
    return {"added": added, "year": year, "transfers": len(doff) + len(work)}
