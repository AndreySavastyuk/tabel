# -*- coding: utf-8 -*-
"""Центр закрытия месяца: список периодов, сводка готовности, закрытие/
переоткрытие, выбор активного прогона. Доступ — Кадры/Админ и Бухгалтер
(закрытие/переоткрытие — только Кадры/Админ). Единица закрытия — цельный месяц."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import require_role
from ..models import PeriodState, PipelineRun
from ..schemas import (ClosingSummaryOut, MonthPeriodOut, PeriodActiveRunIn,
                       PeriodCloseIn, PeriodReopenIn)
from ..services import period_close

router = APIRouter(prefix="/periods", tags=["periods"])

_MONTH = re.compile(r"^\d{4}-\d{2}$")


def _valid_period(period: str) -> str:
    if not _MONTH.match(period):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Период должен быть в формате YYYY-MM")
    return period


def _state_out(db: Session, ps: PeriodState) -> MonthPeriodOut:
    n_runs, last_at = db.execute(
        select(func.count(), func.max(PipelineRun.created_at))
        .where(PipelineRun.period_label == ps.period)).one()
    return MonthPeriodOut(period=ps.period, status=ps.status, active_run_id=ps.active_run_id,
                          n_runs=n_runs or 0, last_run_at=last_at, closed_at=ps.closed_at)


@router.get("", response_model=list[MonthPeriodOut],
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def get_periods(limit: int = Query(24, le=120), db: Session = Depends(get_db)):
    return period_close.list_periods(db, limit=limit)


@router.get("/{period}/closing-summary", response_model=ClosingSummaryOut,
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def closing_summary(period: str = Path(...), run_id: Optional[int] = None,
                    db: Session = Depends(get_db)):
    return period_close.build_closing_summary(db, _valid_period(period), run_id)


@router.put("/{period}/active-run", response_model=MonthPeriodOut,
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def put_active_run(body: PeriodActiveRunIn, period: str = Path(...),
                   db: Session = Depends(get_db)):
    ps = period_close.set_active_run(db, _valid_period(period), body.run_id)
    if ps is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Прогон не принадлежит этому периоду")
    return _state_out(db, ps)


@router.post("/{period}/close", response_model=MonthPeriodOut)
def close(body: PeriodCloseIn, period: str = Path(...), db: Session = Depends(get_db),
          user=Depends(require_role(Role.admin_hr))):
    ps, blockers = period_close.close_period(
        db, _valid_period(period), run_id=body.run_id, force=body.force, closed_by=user.id)
    if ps is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Нельзя закрыть месяц: " + "; ".join(f"{b.label} ({b.count})" for b in blockers))
    return _state_out(db, ps)


@router.post("/{period}/reopen", response_model=MonthPeriodOut)
def reopen(body: PeriodReopenIn, period: str = Path(...), db: Session = Depends(get_db),
           user=Depends(require_role(Role.admin_hr))):
    ps = period_close.reopen_period(db, _valid_period(period), note=body.note)
    return _state_out(db, ps)
