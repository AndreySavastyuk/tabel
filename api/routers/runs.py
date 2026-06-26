# -*- coding: utf-8 -*-
"""Прогоны табеля: запуск (фоновая обработка), статус, day-records, своды,
Excel-экспорт. Запуск/экспорт — Кадры/Админ и Бухгалтер; day-records —
Руководитель видит только свой отдел."""
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     status)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db, get_session_factory
from ..deps import get_current_user, require_role, scoped_department_id
from ..models import DayRecordRow, Employee, PeriodSummary, PipelineRun, Upload
from ..schemas import DayRecordOut, PeriodOut, RunCreate, RunOut
from ..services import export, ingestion

router = APIRouter(prefix="/runs", tags=["runs"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(body: RunCreate, bg: BackgroundTasks, db: Session = Depends(get_db),
               factory=Depends(get_session_factory),
               user=Depends(require_role(Role.admin_hr))):
    ups = db.scalars(select(Upload).where(Upload.id.in_(body.upload_ids))).all()
    if not ups:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не указаны корректные загрузки")
    run = PipelineRun(created_by=user.id, upload_ids=body.upload_ids, status="queued")
    db.add(run)
    db.commit()
    db.refresh(run)
    bg.add_task(ingestion.process_run, run.id, factory)
    return run


@router.get("", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(PipelineRun).order_by(PipelineRun.id.desc())).all()


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
    out = []
    for r in rows:
        o = DayRecordOut.model_validate(r)
        o.employee_name = names.get(r.employee_id)
        out.append(o)
    return out


@router.get("/{run_id}/periods", response_model=list[PeriodOut],
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def run_periods(run_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(PeriodSummary).where(PeriodSummary.run_id == run_id)
        .order_by(PeriodSummary.percent)).all()
    names = {e.id: e.full_name for e in db.scalars(select(Employee)).all()}
    out = []
    for r in rows:
        o = PeriodOut.model_validate(r)
        o.employee_name = names.get(r.employee_id)
        out.append(o)
    return out


@router.get("/{run_id}/export/timesheet.xlsx",
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def export_timesheet(run_id: int, db: Session = Depends(get_db)):
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогон не найден")
    if run.status != "done":
        raise HTTPException(status.HTTP_409_CONFLICT, "Прогон ещё не завершён")
    buf = export.write_workbook(db, run_id)
    headers = {"Content-Disposition": f'attachment; filename="tabel_run{run_id}.xlsx"'}
    return StreamingResponse(buf, media_type=_XLSX, headers=headers)
