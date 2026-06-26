# -*- coding: utf-8 -*-
"""Ингест: собирает рабочую папку из загруженных файлов, прогоняет движок
(engine.pipeline-логика) и сохраняет access_events / day_records /
period_summaries. Движок чист (без глобалей после Фазы 0), поэтому прогон
выполняется в фоновой задаче со своей сессией БД — без подпроцесса."""
import os
import shutil
import tempfile
from datetime import datetime, timezone

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from engine import bases, compute, model as emodel, shifts
from engine.calendar import make_calendar_weekend_fn
from engine.timeutil import date_former

from ..models import (AccessEvent, DayRecordRow, Employee, EmployeeAlias,
                      PeriodSummary, PipelineRun, Upload)
from .refdata_from_db import (build_fixed_times, build_refdata,
                              load_calendar, load_thresholds)


def _assemble_workdir(uploads) -> str:
    """Копирует загрузки в temp-папку с именами, которые ждёт engine.bases."""
    wp = tempfile.mkdtemp(prefix="scud_run_")
    os.makedirs(os.path.join(wp, "ЛЭЗ"), exist_ok=True)
    dst_by_source = {
        "stork": os.path.join(wp, "StorK.csv"),
        "sigur": os.path.join(wp, "SIGUR.xlsx"),
        "hikvision": os.path.join(wp, "report.xls"),
        "lez": os.path.join(wp, "ЛЭЗ", "lez.xlsx"),
    }
    for up in uploads:
        dst = dst_by_source.get(up.source)
        if dst and os.path.exists(up.stored_path):
            shutil.copy(up.stored_path, dst)
    return wp


def compute_analytics(db: Session, wp: str, names=None):
    """Парсинг + расчёт (без записи в БД). Возвращает
    (records, periods, base, lezbase, points, weekend_fn)."""
    ref = build_refdata(db)
    fixed = build_fixed_times(db)
    thresholds = {**emodel.THRESHOLDS, **load_thresholds(db)}
    weekend_fn = make_calendar_weekend_fn(*load_calendar(db))

    base, lezbase, points = bases.build_bases(wp)
    allnames = set(base) | set(lezbase)
    if names is not None:
        allnames &= set(names)
    rebuild = {n: [] for n in allnames}
    records = shifts.build_day_records(
        rebuild, base, lezbase, ref=ref, fixed_employees=fixed, apply_fixed=True,
        thresholds=thresholds, weekend_fn=weekend_fn)
    span = compute.date_span_of(records)
    compute.inject_absence_records(records, ref, span, weekend_fn=weekend_fn)
    work_days = compute.count_working_days(span, weekend_fn=weekend_fn)
    periods = compute.build_employee_periods(
        records, ref=ref, working_days=work_days, thresholds=thresholds)
    return records, periods, base, lezbase, points, weekend_fn


def _resolve_employees(db: Session, names) -> dict:
    """{normalized_name: employee_id}. Несопоставленные ФИО заводятся
    автоматически (alias confirmed=False — в очередь сверки), без тихих потерь."""
    emap = {e.normalized_name: e.id for e in db.scalars(select(Employee)).all()}
    for nm in names:
        if nm not in emap:
            e = Employee(full_name=nm, normalized_name=nm, is_active=True, lez_controlled=False)
            db.add(e)
            db.flush()
            emap[nm] = e.id
            db.add(EmployeeAlias(employee_id=e.id, raw_name=nm, normalized_name=nm,
                                 source="manual", confidence=0.0, confirmed=False))
    return emap


def _persist(db: Session, run_id: int, records, periods, base, lezbase, points, emap):
    db.execute(delete(DayRecordRow).where(DayRecordRow.run_id == run_id))
    db.execute(delete(PeriodSummary).where(PeriodSummary.run_id == run_id))
    db.execute(delete(AccessEvent).where(AccessEvent.run_id == run_id))

    drows = []
    for nm, recs in records.items():
        eid = emap.get(nm)
        if eid is None:
            continue
        for dr in recs:
            drows.append(dict(
                run_id=run_id, employee_id=eid, work_date=dr.date, is_weekend=dr.is_weekend,
                int_entry=dr.int_entry, int_exit=dr.int_exit, lez_entry=dr.lez_entry,
                lez_exit=dr.lez_exit, entry=dr.entry, exit=dr.exit,
                entry_source=dr.entry_source, exit_source=dr.exit_source,
                start_fixed=dr.start_fixed, original_start=dr.original_start,
                raw_hours=dr.raw_hours, lunch_deducted=dr.lunch_deducted,
                worked_hours=dr.worked_hours, schedule_code=dr.schedule, dept_name=dr.dept,
                cabinet=dr.cabinet, lez_controlled=dr.lez_controlled,
                dual_tracked=dr.dual_tracked, day_norm=dr.day_norm, absence=dr.absence,
                lateness_min=dr.lateness_min, overtime_h=dr.overtime_h,
                deviations=list(dr.deviations or [])))
    if drows:
        db.execute(insert(DayRecordRow), drows)

    prows = []
    for nm, ep in periods.items():
        eid = emap.get(nm)
        if eid is None:
            continue
        prows.append(dict(
            run_id=run_id, employee_id=eid, schedule_code=ep.schedule, dept_name=ep.dept,
            worked_total=ep.worked_total, credited_total=ep.credited_total,
            period_norm=ep.period_norm, absence_days=ep.absence_days,
            late_count=ep.late_count, late_minutes=ep.late_minutes,
            overtime_total=ep.overtime_total, percent=ep.percent, bucket=ep.bucket,
            overtime_pay=None))
    if prows:
        db.execute(insert(PeriodSummary), prows)

    events = []
    for src, store in (("internal", base), ("LEZ", lezbase)):
        for nm, d in store.items():
            eid = emap.get(nm)
            for key, kind in d.items():
                dt = date_former(key)
                if not isinstance(dt, datetime):
                    continue
                events.append(dict(
                    run_id=run_id, employee_id=eid, raw_name=nm, event_ts=dt,
                    kind=str(kind)[:10], source=src,
                    system=points.get(f"{nm} {key}", src)))
    if events:
        db.execute(insert(AccessEvent), events)


def process_run(run_id: int, SessionFactory, names=None):
    """Полный прогон: parse → compute → persist. Не бросает наружу (для
    фоновой задачи): при ошибке помечает run как failed."""
    db = SessionFactory()
    wp = None
    try:
        run = db.get(PipelineRun, run_id)
        run.status = "running"
        db.commit()
        uploads = db.scalars(select(Upload).where(Upload.id.in_(run.upload_ids or []))).all()
        wp = _assemble_workdir(uploads)
        records, periods, base, lezbase, points, _ = compute_analytics(db, wp, names=names)
        emap = _resolve_employees(db, set(base) | set(lezbase))
        _persist(db, run_id, records, periods, base, lezbase, points, emap)
        run = db.get(PipelineRun, run_id)
        run.status = "done"
        run.n_day_records = sum(len(v) for v in records.values())
        run.n_employees = len(periods)
        run.finished_at = datetime.now(timezone.utc)
        for up in uploads:
            up.status = "parsed"
        db.commit()
    except Exception as e:
        db.rollback()
        run = db.get(PipelineRun, run_id)
        if run:
            run.status = "failed"
            run.error_text = str(e)[:2000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
        print("process_run failed:", e)
    finally:
        if wp:
            shutil.rmtree(wp, ignore_errors=True)
        db.close()
