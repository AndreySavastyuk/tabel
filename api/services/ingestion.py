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

from ..constants import DeviationStatus
from ..models import (AccessEvent, DayRecordRow, DeviationItem, Employee,
                      EmployeeAlias, PeriodSummary, PipelineRun, Upload)
from .deviation_codes import detail_of, dev_code
from .refdata_from_db import (build_fixed_times, build_refdata,
                              load_calendar, load_thresholds)

# Порог по СУММЕ отлучек ЛЭЗ за день (мин): если суммарно человек был вне
# территории дольше — заводим отклонение «Выход с территории». В отличие от
# движка (порог на КАЖДЫЙ эпизод) здесь суммируются все выходы, в т.ч. короткие.
# Значение по умолчанию; фактически берётся из порогов прогона (Настройки →
# ключ away_daily_min), см. _persist.
AWAY_DAILY_MIN = 30


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


def _truncate_to_period(records, d0, d1):
    """Оставляет в records только дни в пределах [d0, d1] (включительно)."""
    for name in list(records):
        kept = []
        for dr in records[name]:
            d = compute.parse_ddmmyyyy(dr.date)
            if d is not None and d0 <= d <= d1:
                kept.append(dr)
        records[name] = kept


def compute_analytics(db: Session, wp: str, names=None, period_from=None, period_to=None):
    """Парсинг + расчёт (без записи в БД). Возвращает
    (records, periods, base, lezbase, points, weekend_fn, thresholds).

    thresholds — фактически применённый словарь порогов прогона; сохраняется в
    PipelineRun.thresholds для воспроизводимости (объяснение дня, отклонения).

    Если задан период [period_from, period_to], записи обрезаются по нему, а
    норма периода считается пропорционально доле рабочих дней (неполный месяц).
    Без периода (legacy) — поведение прежнее, byte-for-byte."""
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
    if period_from and period_to:
        _truncate_to_period(records, period_from, period_to)
        span = (period_from, period_to)
        norm_factors = compute.period_norm_factors(period_from, period_to, weekend_fn)
    else:
        span = compute.date_span_of(records)
        norm_factors = None
    compute.inject_absence_records(records, ref, span, weekend_fn=weekend_fn)
    work_days = compute.count_working_days(span, weekend_fn=weekend_fn)
    periods = compute.build_employee_periods(
        records, ref=ref, working_days=work_days, thresholds=thresholds,
        norm_factors=norm_factors)
    return records, periods, base, lezbase, points, weekend_fn, thresholds


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


def _persist(db: Session, run_id: int, records, periods, base, lezbase, points, emap,
             thresholds=None):
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

    away = int((thresholds or emodel.THRESHOLDS).get("away_daily_min", AWAY_DAILY_MIN))
    _sync_deviations(db, run_id, records, emap, away_daily_min=away)


def _sync_deviations(db: Session, run_id: int, records, emap, away_daily_min=AWAY_DAILY_MIN):
    """Синхронизирует deviation_items против отклонений этого прогона.

    Ключ employee_id|work_date|dev_code run-независим: повторный прогон того же
    дня НЕ плодит дубль и НЕ сбрасывает статус/ответственного/комментарии —
    обновляет лишь run_id/last_seen/detail/is_present. Отклонение, исчезнувшее
    из прогона (данные поправили), помечается is_present=False (не удаляется —
    аудит)."""
    eids = {e for e in emap.values() if e is not None}
    dept_by_eid = {}
    if eids:
        for e in db.scalars(select(Employee).where(Employee.id.in_(eids))):
            dept_by_eid[e.id] = e.department_id

    present = {}   # dedup_key -> поля
    for nm, recs in records.items():
        eid = emap.get(nm)
        if eid is None:
            continue
        for dr in recs:
            fields = dict(dept_name=dr.dept, department_id=dept_by_eid.get(eid))
            # 1) обычные коды из движка. Re-entry движка ПРОПУСКАЕМ — «выход с
            #    территории» пересчитываем сами по ДНЕВНОЙ СУММЕ отлучек (ниже).
            for item in (dr.deviations or []):
                code = dev_code(item)
                if code == emodel.DEV_REENTRY:
                    continue
                key = f"{eid}|{dr.date}|{code}"
                if key not in present:
                    present[key] = dict(employee_id=eid, work_date=dr.date, dev_code=code,
                                        detail=detail_of(item), away_minutes=0, **fields)
            # 2) выход с территории: сумма ВСЕХ отлучек ЛЭЗ за день (в т.ч. < 30 мин
            #    по отдельности); флаг, если суммарно за день > порога.
            episodes = compute.lez_reentry_gaps(dr.lez_events, 0)
            total = sum(m for _, _, m in episodes)
            if total > away_daily_min:
                key = f"{eid}|{dr.date}|{emodel.DEV_REENTRY}"
                detail = "; ".join(f"{t_out}→{t_in} · {m} мин" for t_out, t_in, m in episodes)
                present[key] = dict(employee_id=eid, work_date=dr.date,
                                    dev_code=emodel.DEV_REENTRY, detail=detail,
                                    away_minutes=int(total), **fields)

    now = datetime.now(timezone.utc)
    existing = {}
    if present:
        for di in db.scalars(select(DeviationItem).where(
                DeviationItem.dedup_key.in_(list(present.keys())))):
            existing[di.dedup_key] = di
    for key, f in present.items():
        di = existing.get(key)
        if di is None:
            db.add(DeviationItem(
                dedup_key=key, run_id=run_id, employee_id=f["employee_id"],
                department_id=f["department_id"], work_date=f["work_date"],
                dev_code=f["dev_code"], detail=f["detail"], away_minutes=f["away_minutes"],
                dept_name=f["dept_name"], status=DeviationStatus.new.value, is_present=True,
                first_seen_at=now, last_seen_at=now))
        else:
            di.run_id = run_id
            di.detail = f["detail"]
            di.away_minutes = f["away_minutes"]
            di.dept_name = f["dept_name"]
            di.department_id = f["department_id"]
            di.is_present = True
            di.last_seen_at = now
            # status / assignee / comments / time_decision / deduct_minutes — НЕ трогаем
            # (решение о вычете переживает перепрогон; сумма меняется, решение — нет)

    # исчезнувшие: ранее наблюдались этим прогоном, теперь отсутствуют
    gone = select(DeviationItem).where(
        DeviationItem.run_id == run_id, DeviationItem.is_present.is_(True))
    if present:
        gone = gone.where(DeviationItem.dedup_key.notin_(list(present.keys())))
    for di in db.scalars(gone):
        di.is_present = False


def process_run(run_id: int, SessionFactory, names=None):
    """Полный прогон: parse → compute → persist. Не бросает наружу (для
    фоновой задачи): при ошибке помечает run как failed."""
    db = SessionFactory()
    wp = None
    try:
        run = db.get(PipelineRun, run_id)
        if run.is_final:
            # финальный (утверждённый) прогон заморожен — пересчёт запрещён.
            return
        run.status = "running"
        period_from, period_to = run.period_from, run.period_to
        db.commit()
        uploads = db.scalars(select(Upload).where(Upload.id.in_(run.upload_ids or []))).all()
        wp = _assemble_workdir(uploads)
        records, periods, base, lezbase, points, _wf, thresholds = compute_analytics(
            db, wp, names=names, period_from=period_from, period_to=period_to)
        emap = _resolve_employees(db, set(base) | set(lezbase))
        _persist(db, run_id, records, periods, base, lezbase, points, emap, thresholds=thresholds)
        run = db.get(PipelineRun, run_id)
        run.status = "done"
        run.thresholds = thresholds
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
