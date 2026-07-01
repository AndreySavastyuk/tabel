# -*- coding: utf-8 -*-
"""Прогоны табеля: запуск (фоновая обработка), статус, day-records, своды,
Excel-экспорт. Период прогона (месяц/диапазон), финализация (утверждение
финального прогона периода), сравнение перезапусков (diff). Запуск/экспорт —
Кадры/Админ и Бухгалтер; day-records — Руководитель видит только свой отдел."""
import calendar
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     status)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db, get_session_factory
from ..deps import get_current_user, require_role, scoped_department_id
from ..models import DayRecordRow, Employee, PeriodSummary, PipelineRun, Upload
from ..schemas import (DayDiff, DayRecordOut, PeriodOut, RunCreate, RunDiffOut,
                       RunOut)
from ..services import export, ingestion, time_adjust
from ..services.deviation_codes import dev_code
from engine import compute as ecompute

router = APIRouter(prefix="/runs", tags=["runs"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _resolve_period(body: RunCreate):
    """(period_from, period_to, period_label) из тела создания прогона."""
    if body.period:
        y, m = (int(x) for x in body.period.split("-"))
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1]), body.period
    if body.period_from and body.period_to:
        return body.period_from, body.period_to, None
    return None, None, None


def _bounds(run: PipelineRun):
    """Границы периода прогона [from, to] или (None, None)."""
    if run.period_from and run.period_to:
        return run.period_from, run.period_to
    if run.period_label:
        y, m = (int(x) for x in run.period_label.split("-"))
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    return None, None


def _overlaps(a: PipelineRun, b: PipelineRun) -> bool:
    af, at = _bounds(a)
    bf, bt = _bounds(b)
    if None in (af, at, bf, bt):
        return False
    return af <= bt and bf <= at


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(body: RunCreate, bg: BackgroundTasks, db: Session = Depends(get_db),
               factory=Depends(get_session_factory),
               user=Depends(require_role(Role.admin_hr))):
    ups = db.scalars(select(Upload).where(Upload.id.in_(body.upload_ids))).all()
    if not ups:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не указаны корректные загрузки")
    pf, pt, plabel = _resolve_period(body)
    run = PipelineRun(created_by=user.id, upload_ids=body.upload_ids, status="queued",
                      period_from=pf, period_to=pt, period_label=plabel)
    db.add(run)
    db.commit()
    db.refresh(run)
    bg.add_task(ingestion.process_run, run.id, factory)
    return run


@router.get("", response_model=list[RunOut])
def list_runs(period: Optional[str] = None, db: Session = Depends(get_db),
              _=Depends(get_current_user)):
    stmt = select(PipelineRun)
    if period:
        stmt = stmt.where(PipelineRun.period_label == period)
    return db.scalars(stmt.order_by(PipelineRun.id.desc())).all()


# ВАЖНО: литеральный /final объявлен ДО /{run_id}, иначе 'final' парсится как id.
@router.get("/final", response_model=RunOut)
def final_run(period: Optional[str] = None, db: Session = Depends(get_db),
              _=Depends(get_current_user)):
    """Финальный (утверждённый) прогон периода — на него ссылаются экспорт и карточки."""
    stmt = select(PipelineRun).where(PipelineRun.is_final.is_(True))
    if period:
        stmt = stmt.where(PipelineRun.period_label == period)
    run = db.scalars(stmt.order_by(PipelineRun.finalized_at.desc())).first()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Финальный прогон не найден")
    return run


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогон не найден")
    return run


@router.get("/{run_id}/day-records", response_model=list[DayRecordOut])
def run_day_records(run_id: int, db: Session = Depends(get_db),
                    user=Depends(get_current_user),
                    limit: int = Query(5000, le=20000), offset: int = 0):
    stmt = select(DayRecordRow).where(DayRecordRow.run_id == run_id)
    if user.role == Role.dept_head.value:
        dep = scoped_department_id(user)
        if dep is None:
            return []
        stmt = stmt.join(Employee, Employee.id == DayRecordRow.employee_id) \
                   .where(Employee.department_id == dep)
    stmt = stmt.order_by(DayRecordRow.id).limit(limit).offset(offset)
    rows = db.scalars(stmt).all()
    names = {e.id: e.full_name for e in db.scalars(select(Employee)).all()}
    dmap = time_adjust.deduction_map(db)
    out = []
    for r in rows:
        o = DayRecordOut.model_validate(r)
        o.employee_name = names.get(r.employee_id)
        m = dmap.get((r.employee_id, r.work_date), 0)
        if m:
            o.deduct_minutes = int(m)
            o.effective_hours = time_adjust.apply_day(r.worked_hours, m)
        out.append(o)
    return out


@router.get("/{run_id}/periods", response_model=list[PeriodOut],
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def run_periods(run_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(PeriodSummary).where(PeriodSummary.run_id == run_id)
        .order_by(PeriodSummary.percent)).all()
    names = {e.id: e.full_name for e in db.scalars(select(Employee)).all()}
    # Вычет времени вне территории уменьшает отработанные/зачтённые часы и %.
    applied = time_adjust.run_applied_by_employee(db, run_id)
    out = []
    for r in rows:
        o = PeriodOut.model_validate(r)
        o.employee_name = names.get(r.employee_id)
        ded = applied.get(r.employee_id, 0.0)
        if ded:
            o.deducted_hours = ded
            o.worked_total = round(o.worked_total - ded, 2)
            o.credited_total = round(o.credited_total - ded, 2)
            if o.period_norm > 0:
                o.percent = round(o.credited_total / o.period_norm * 100.0, 1)
                o.bucket = ecompute.bucket_of(o.percent)
        out.append(o)
    return out


@router.post("/{run_id}/finalize", response_model=RunOut)
def finalize_run(run_id: int, db: Session = Depends(get_db),
                 user=Depends(require_role(Role.admin_hr))):
    """Пометить прогон финальным/утверждённым. Снимает is_final со всех
    пересекающихся по периоду прогонов (ровно один финальный на период)."""
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогон не найден")
    if run.status != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, "Прогон ещё не завершён")
    if _bounds(run) == (None, None):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "У прогона не задан период — финализация невозможна")
    for o in db.scalars(select(PipelineRun).where(
            PipelineRun.is_final.is_(True), PipelineRun.id != run_id)).all():
        if _overlaps(o, run):
            o.is_final = False
            o.finalized_at = None
            o.finalized_by = None
    run.is_final = True
    run.finalized_at = datetime.now(timezone.utc)
    run.finalized_by = user.id
    db.commit()
    db.refresh(run)
    return run


@router.post("/{run_id}/unfinalize", response_model=RunOut)
def unfinalize_run(run_id: int, db: Session = Depends(get_db),
                   user=Depends(require_role(Role.admin_hr))):
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогон не найден")
    run.is_final = False
    run.finalized_at = None
    run.finalized_by = None
    db.commit()
    db.refresh(run)
    return run


_DIFF_FIELDS = ("worked_hours", "lateness_min", "overtime_h", "absence", "entry", "exit")


def _norm_field(r, name):
    v = getattr(r, name)
    if name in ("worked_hours", "overtime_h"):
        return round(float(v or 0), 2)
    if name == "lateness_min":
        return int(v or 0)
    return v


def _dev_codes(r):
    return sorted({dev_code(x) for x in (r.deviations or [])})


@router.get("/{run_id}/diff/{other_run_id}", response_model=RunDiffOut,
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def run_diff(run_id: int, other_run_id: int, db: Session = Depends(get_db),
             only_changed: bool = False, limit: int = Query(2000, le=10000)):
    """Diff двух прогонов по стабильному ключу (employee_id, work_date):
    added (есть в other, нет в base), removed (есть в base, нет в other),
    changed (значимые поля разошлись). re-entry сравнивается по коду."""
    a = db.get(PipelineRun, run_id)
    b = db.get(PipelineRun, other_run_id)
    if a is None or b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогон не найден")
    arows = {(r.employee_id, r.work_date): r
             for r in db.scalars(select(DayRecordRow).where(DayRecordRow.run_id == run_id))}
    brows = {(r.employee_id, r.work_date): r
             for r in db.scalars(select(DayRecordRow).where(DayRecordRow.run_id == other_run_id))}
    names = {e.id: e.full_name for e in db.scalars(select(Employee))}
    added, removed, changed = [], [], []

    if not only_changed:
        for key in brows.keys() - arows.keys():
            eid, wd = key
            r = brows[key]
            added.append(DayDiff(employee_id=eid, employee_name=names.get(eid), work_date=wd,
                                 fields={"worked_hours": {"from": None, "to": _norm_field(r, "worked_hours")},
                                         "absence": {"from": None, "to": r.absence}}))
        for key in arows.keys() - brows.keys():
            eid, wd = key
            r = arows[key]
            removed.append(DayDiff(employee_id=eid, employee_name=names.get(eid), work_date=wd,
                                   fields={"worked_hours": {"from": _norm_field(r, "worked_hours"), "to": None},
                                           "absence": {"from": r.absence, "to": None}}))

    for key in arows.keys() & brows.keys():
        ra, rb = arows[key], brows[key]
        diffs = {}
        for name in _DIFF_FIELDS:
            va, vb = _norm_field(ra, name), _norm_field(rb, name)
            if va != vb:
                diffs[name] = {"from": va, "to": vb}
        da, dbv = _dev_codes(ra), _dev_codes(rb)
        if da != dbv:
            diffs["deviations"] = {"from": da, "to": dbv}
        if diffs:
            eid, wd = key
            changed.append(DayDiff(employee_id=eid, employee_name=names.get(eid),
                                   work_date=wd, fields=diffs))

    return RunDiffOut(
        base_run_id=run_id, other_run_id=other_run_id,
        n_added=len(added), n_removed=len(removed), n_changed=len(changed),
        added=added[:limit], removed=removed[:limit], changed=changed[:limit])


@router.get("/{run_id}/export/timesheet.xlsx",
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def export_timesheet(run_id: int, db: Session = Depends(get_db),
                     allow_nonfinal: bool = Query(False)):
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогон не найден")
    if run.status != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, "Прогон ещё не завершён")
    if not run.is_final and run.period_label and not allow_nonfinal:
        fin = db.scalars(select(PipelineRun).where(
            PipelineRun.period_label == run.period_label,
            PipelineRun.is_final.is_(True))).first()
        if fin and fin.id != run_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"По периоду {run.period_label} утверждён финальный прогон №{fin.id}; "
                f"экспортируйте его или передайте allow_nonfinal=true")
    buf = export.write_workbook(db, run_id)
    headers = {"Content-Disposition": f'attachment; filename="tabel_run{run_id}.xlsx"'}
    return StreamingResponse(buf, media_type=_XLSX, headers=headers)
