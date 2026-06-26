# -*- coding: utf-8 -*-
"""Отсутствия: отпуск/больничный/командировка (факты, сразу approved) и отгул
(submitted → подтверждает Кадры/Админ). Руководитель оформляет только отгул по
своему отделу и видит только свой отдел; подтверждение/правка/удаление — Кадры."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import AbsenceStatus, AbsenceType, Role
from ..db import get_db
from ..deps import get_current_user, require_role, scoped_department_id
from ..models import Absence, Employee
from ..schemas import AbsenceIn, AbsenceOut, AbsenceUpdate

router = APIRouter(prefix="/absences", tags=["absences"])


def _out(db: Session, a: Absence) -> AbsenceOut:
    o = AbsenceOut.model_validate(a)
    emp = db.get(Employee, a.employee_id)
    o.employee_name = emp.full_name if emp else None
    return o


@router.get("", response_model=list[AbsenceOut])
def list_absences(db: Session = Depends(get_db), user=Depends(get_current_user),
                  status_: str | None = Query(None, alias="status"),
                  type_: str | None = Query(None, alias="type"),
                  employee_id: int | None = None):
    stmt = select(Absence)
    if user.role == Role.dept_head.value:
        dep = scoped_department_id(user)
        if dep is None:
            return []
        stmt = stmt.join(Employee, Employee.id == Absence.employee_id) \
                   .where(Employee.department_id == dep)
    if status_:
        stmt = stmt.where(Absence.status == status_)
    if type_:
        stmt = stmt.where(Absence.type == type_)
    if employee_id:
        stmt = stmt.where(Absence.employee_id == employee_id)
    rows = db.scalars(stmt.order_by(Absence.date_from.desc())).all()
    names = {e.id: e.full_name for e in db.scalars(select(Employee)).all()}
    out = []
    for a in rows:
        o = AbsenceOut.model_validate(a)
        o.employee_name = names.get(a.employee_id)
        out.append(o)
    return out


@router.post("", response_model=AbsenceOut, status_code=status.HTTP_201_CREATED)
def create_absence(body: AbsenceIn, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    emp = db.get(Employee, body.employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    if user.role == Role.admin_hr.value:
        pass
    elif user.role == Role.dept_head.value:
        if body.type != AbsenceType.timeoff:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Руководитель может оформлять только отгул")
        if emp.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Сотрудник вне вашего отдела")
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")

    # отгул — на подтверждение; остальное (факты) — сразу учтено
    approved = body.type != AbsenceType.timeoff
    now = datetime.now(timezone.utc)
    a = Absence(
        employee_id=body.employee_id, type=body.type.value,
        date_from=body.date_from, date_to=body.date_to, note=body.note,
        status=AbsenceStatus.approved.value if approved else AbsenceStatus.submitted.value,
        created_by=user.id,
        approved_by=user.id if approved else None,
        approved_at=now if approved else None,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.patch("/{aid}", response_model=AbsenceOut,
              dependencies=[Depends(require_role(Role.admin_hr))])
def update_absence(aid: int, body: AbsenceUpdate, db: Session = Depends(get_db)):
    a = db.get(Absence, aid)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отсутствие не найдено")
    data = body.model_dump(exclude_unset=True)
    if "type" in data and data["type"] is not None:
        a.type = data.pop("type").value
    for k, v in data.items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.post("/{aid}/approve", response_model=AbsenceOut,
             dependencies=[Depends(require_role(Role.admin_hr))])
def approve_absence(aid: int, db: Session = Depends(get_db),
                    user=Depends(require_role(Role.admin_hr))):
    return _set_status(db, aid, AbsenceStatus.approved.value, user.id)


@router.post("/{aid}/reject", response_model=AbsenceOut,
             dependencies=[Depends(require_role(Role.admin_hr))])
def reject_absence(aid: int, db: Session = Depends(get_db),
                   user=Depends(require_role(Role.admin_hr))):
    return _set_status(db, aid, AbsenceStatus.rejected.value, user.id)


def _set_status(db: Session, aid: int, new_status: str, uid: int) -> AbsenceOut:
    a = db.get(Absence, aid)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отсутствие не найдено")
    a.status = new_status
    a.approved_by = uid
    a.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.delete("/{aid}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role(Role.admin_hr))])
def delete_absence(aid: int, db: Session = Depends(get_db)):
    a = db.get(Absence, aid)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отсутствие не найдено")
    db.delete(a)
    db.commit()
