# -*- coding: utf-8 -*-
"""Сотрудники. Чтение — всем (Руководитель видит только свой отдел). Создание/
правка/массовое присвоение — Кадры/Админ; Бухгалтер может менять только ставку.
Карточка: помесячная сводка + дни месяца."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.names import name_format

from ..constants import Role
from ..db import get_db
from ..deps import get_current_user, require_role, scoped_department_id
from ..models import Employee
from ..schemas import (DayExplainOut, DayRecordOut, EmployeeBulkAssign,
                       EmployeeCreate, EmployeeOut, EmployeeUpdate, MonthSummary,
                       employee_out)
from ..services import employee_stats, explain, time_adjust

router = APIRouter(prefix="/employees", tags=["employees"])


def _require_access(user, emp: Employee):
    dep = scoped_department_id(user)
    if dep is not None and emp.department_id != dep:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Сотрудник вне вашего отдела")


@router.get("", response_model=list[EmployeeOut])
def list_employees(q: Optional[str] = None, active_only: bool = False,
                   department_id: Optional[int] = None, no_schedule: bool = False,
                   no_department: bool = False, vehicle_only: bool = False,
                   include_dismissed: bool = False,
                   limit: int = Query(2000, le=5000), offset: int = 0,
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    dep = scoped_department_id(user)
    if user.role == Role.dept_head.value and dep is None:
        return []
    stmt = select(Employee)
    if dep is not None:
        stmt = stmt.where(Employee.department_id == dep)
    elif department_id is not None:
        stmt = stmt.where(Employee.department_id == department_id)
    if active_only:
        stmt = stmt.where(Employee.is_active.is_(True))
    if no_schedule:
        stmt = stmt.where(Employee.schedule_id.is_(None))
    if no_department:                       # «неразобранные» — без отдела
        stmt = stmt.where(Employee.department_id.is_(None))
    if vehicle_only:                        # отмеченные «личный транспорт»
        stmt = stmt.where(Employee.arrives_by_car.is_(True))
    if not include_dismissed:               # уволенные скрыты, пока не попросили
        stmt = stmt.where(Employee.dismissed_at.is_(None))
    if q:
        stmt = stmt.where(Employee.full_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Employee.full_name).limit(limit).offset(offset)
    return [employee_out(e, Role(user.role)) for e in db.scalars(stmt).all()]


@router.patch("/bulk", dependencies=[Depends(require_role(Role.admin_hr))])
def bulk_assign(body: EmployeeBulkAssign, db: Session = Depends(get_db)):
    """Массово присвоить отдел/кабинет/график выбранным сотрудникам.
    Передавайте только нужные поля; явный null — очистить."""
    fields = body.model_dump(exclude_unset=True)
    fields.pop("ids", None)
    if fields.get("arrives_by_car", False) is None:   # null для bool = «снять флаг»
        fields["arrives_by_car"] = False
    if not body.ids or not fields:
        return {"updated": 0}
    emps = db.scalars(select(Employee).where(Employee.id.in_(body.ids))).all()
    for e in emps:
        for k, v in fields.items():
            setattr(e, k, v)
    db.commit()
    return {"updated": len(emps), "fields": list(fields)}


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(body: EmployeeCreate, db: Session = Depends(get_db),
                    user=Depends(require_role(Role.admin_hr))):
    e = Employee(normalized_name=name_format(body.full_name), **body.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return employee_out(e, Role(user.role))


@router.get("/{emp_id}", response_model=EmployeeOut)
def get_employee(emp_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    e = db.get(Employee, emp_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    _require_access(user, e)
    return employee_out(e, Role(user.role))


@router.patch("/{emp_id}", response_model=EmployeeOut)
def update_employee(emp_id: int, body: EmployeeUpdate, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    if user.role not in (Role.admin_hr.value, Role.accountant.value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    e = db.get(Employee, emp_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    data = body.model_dump(exclude_unset=True)
    if user.role == Role.accountant.value and set(data) - {"hourly_rate"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Бухгалтеру можно менять только ставку (hourly_rate)")
    for k, v in data.items():
        setattr(e, k, v)
        if k == "full_name":
            e.normalized_name = name_format(v)
    if "dismissed_at" in data:              # увольнение гасит активность, восстановление возвращает
        e.is_active = data["dismissed_at"] is None
    db.commit()
    db.refresh(e)
    return employee_out(e, Role(user.role))


@router.get("/{emp_id}/months", response_model=list[MonthSummary])
def employee_months(emp_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    e = db.get(Employee, emp_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    _require_access(user, e)
    return employee_stats.monthly_summaries(db, emp_id)


@router.get("/{emp_id}/days", response_model=list[DayRecordOut])
def employee_days(emp_id: int, month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
                  db: Session = Depends(get_db), user=Depends(get_current_user)):
    e = db.get(Employee, emp_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    _require_access(user, e)
    dmap = time_adjust.deduction_map(db)
    out = []
    for r in employee_stats.daily_records(db, emp_id, month):
        o = DayRecordOut.model_validate(r)
        o.employee_name = e.full_name
        m = dmap.get((emp_id, r.work_date), 0)
        if m:
            o.deduct_minutes = int(m)
            o.effective_hours = time_adjust.apply_day(r.worked_hours, m)
        out.append(o)
    return out


@router.get("/{emp_id}/days/{work_date}/explain", response_model=DayExplainOut)
def explain_day(emp_id: int,
                work_date: str = Path(..., pattern=r"^\d{2}\.\d{2}\.\d{4}$"),
                run_id: Optional[int] = None,
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Полное объяснение расчёта дня (DD.MM.YYYY). По умолчанию — из последнего
    прогона; ?run_id фиксирует конкретный прогон."""
    e = db.get(Employee, emp_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    _require_access(user, e)
    data = explain.build_day_explanation(db, emp_id, work_date, run_id=run_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "День не найден")
    return data
