# -*- coding: utf-8 -*-
"""Отделы: чтение — всем; изменение — только Кадры/Админ."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import get_current_user, require_role
from ..models import Department
from ..schemas import DepartmentIn, DepartmentOut

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.scalars(select(Department).order_by(Department.name)).all()


@router.post("", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_role(Role.admin_hr))])
def create_department(body: DepartmentIn, db: Session = Depends(get_db)):
    if db.scalar(select(Department).where(Department.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Отдел с таким названием уже есть")
    d = Department(name=body.name, parent_id=body.parent_id)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.patch("/{dep_id}", response_model=DepartmentOut,
              dependencies=[Depends(require_role(Role.admin_hr))])
def update_department(dep_id: int, body: DepartmentIn, db: Session = Depends(get_db)):
    d = db.get(Department, dep_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отдел не найден")
    d.name = body.name
    d.parent_id = body.parent_id
    db.commit()
    db.refresh(d)
    return d
