# -*- coding: utf-8 -*-
"""Рабочая очередь отклонений: список/счётчик/карточка, смена статуса и
назначение (одиночно и массово), комментарии. Стабильный ключ отклонения
переживает перезапуск прогона. Руководитель видит/правит только свой отдел."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.model import DEV_LABELS

from ..constants import DeviationStatus, Role
from ..db import get_db
from ..deps import get_current_user, scoped_department_id
from ..models import DeviationComment, DeviationItem, Employee, User
from ..schemas import (DeviationBulkIn, DeviationCommentIn, DeviationCommentOut,
                       DeviationDetailOut, DeviationItemOut, DeviationPatch)

router = APIRouter(prefix="/deviations", tags=["deviations"])

_VALID = {s.value for s in DeviationStatus}
_TERMINAL = {DeviationStatus.accepted.value, DeviationStatus.fixed.value,
             DeviationStatus.ignored.value}
_UNSET = object()


def _decorate(db: Session, items) -> list[DeviationItemOut]:
    """DeviationItem[] -> DeviationItemOut[] с именами и числом комментариев (без N+1)."""
    if not items:
        return []
    eids = {it.employee_id for it in items}
    aids = {it.assignee_id for it in items if it.assignee_id}
    emp_names = {e.id: e.full_name for e in db.scalars(select(Employee).where(Employee.id.in_(eids)))}
    user_names = {}
    if aids:
        user_names = {u.id: (u.full_name or u.username)
                      for u in db.scalars(select(User).where(User.id.in_(aids)))}
    counts = {did: c for did, c in db.execute(
        select(DeviationComment.deviation_id, func.count())
        .where(DeviationComment.deviation_id.in_([it.id for it in items]))
        .group_by(DeviationComment.deviation_id))}
    out = []
    for it in items:
        o = DeviationItemOut.model_validate(it)
        o.employee_name = emp_names.get(it.employee_id)
        o.dev_label = DEV_LABELS.get(it.dev_code, it.dev_code)
        o.assignee_name = user_names.get(it.assignee_id) if it.assignee_id else None
        o.comment_count = counts.get(it.id, 0)
        out.append(o)
    return out


def _load_scoped(db: Session, user, dev_id: int) -> DeviationItem:
    it = db.get(DeviationItem, dev_id)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отклонение не найдено")
    if user.role == Role.dept_head.value:
        dep = scoped_department_id(user)
        if dep is None or it.department_id != dep:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Отклонение вне вашего отдела")
    return it


def _apply_change(db: Session, it: DeviationItem, user, *, new_status=None,
                  note=None, assignee_id=_UNSET):
    if new_status is not None and new_status != it.status:
        if new_status not in _VALID:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Недопустимый статус: {new_status}")
        db.add(DeviationComment(deviation_id=it.id, author_id=user.id,
                                old_status=it.status, new_status=new_status, body=note))
        it.status = new_status
        it.resolved_by = user.id if new_status in _TERMINAL else None
        it.resolved_at = datetime.now(timezone.utc) if new_status in _TERMINAL else None
    elif note:
        db.add(DeviationComment(deviation_id=it.id, author_id=user.id, body=note))
    if note:
        it.resolution_note = note
    if assignee_id is not _UNSET:
        it.assignee_id = assignee_id


@router.get("", response_model=list[DeviationItemOut])
def list_deviations(status_f: Optional[str] = Query(None, alias="status"),
                    dev_code: Optional[str] = None, dept: Optional[int] = None,
                    assignee_id: Optional[int] = None, employee_id: Optional[int] = None,
                    run_id: Optional[int] = None, include_absent: bool = False,
                    limit: int = Query(500, le=2000), offset: int = 0,
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    stmt = select(DeviationItem)
    if user.role == Role.dept_head.value:
        dep = scoped_department_id(user)
        if dep is None:
            return []
        stmt = stmt.where(DeviationItem.department_id == dep)
    elif dept is not None:
        stmt = stmt.where(DeviationItem.department_id == dept)
    if not include_absent:
        stmt = stmt.where(DeviationItem.is_present.is_(True))
    if status_f:
        stmt = stmt.where(DeviationItem.status == status_f)
    if dev_code:
        stmt = stmt.where(DeviationItem.dev_code == dev_code)
    if assignee_id is not None:
        stmt = stmt.where(DeviationItem.assignee_id == assignee_id)
    if employee_id is not None:
        stmt = stmt.where(DeviationItem.employee_id == employee_id)
    if run_id is not None:
        stmt = stmt.where(DeviationItem.run_id == run_id)
    stmt = stmt.order_by(DeviationItem.status, DeviationItem.work_date).limit(limit).offset(offset)
    return _decorate(db, db.scalars(stmt).all())


@router.get("/count")
def deviations_count(dept: Optional[int] = None, run_id: Optional[int] = None,
                     db: Session = Depends(get_db), user=Depends(get_current_user)):
    stmt = select(DeviationItem.status, func.count()).where(DeviationItem.is_present.is_(True))
    if user.role == Role.dept_head.value:
        dep = scoped_department_id(user)
        if dep is None:
            return {"by_status": {}, "open": 0, "total": 0}
        stmt = stmt.where(DeviationItem.department_id == dep)
    elif dept is not None:
        stmt = stmt.where(DeviationItem.department_id == dept)
    if run_id is not None:
        stmt = stmt.where(DeviationItem.run_id == run_id)
    by_status = {s: c for s, c in db.execute(stmt.group_by(DeviationItem.status))}
    open_n = by_status.get("new", 0) + by_status.get("in_progress", 0)
    return {"by_status": by_status, "open": open_n, "total": sum(by_status.values())}


@router.post("/bulk")
def bulk_deviations(body: DeviationBulkIn, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    if not body.ids:
        return {"updated": 0, "skipped": 0}
    if body.status is not None and body.status not in _VALID:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Недопустимый статус: {body.status}")
    items = db.scalars(select(DeviationItem).where(DeviationItem.id.in_(body.ids))).all()
    is_head = user.role == Role.dept_head.value
    dep = scoped_department_id(user)
    updated, skipped = 0, len(body.ids) - len(items)     # ненайденные id
    assignee = body.assignee_id if body.assignee_id is not None else _UNSET
    for it in items:
        if is_head and (dep is None or it.department_id != dep):
            skipped += 1
            continue
        _apply_change(db, it, user, new_status=body.status, note=body.note, assignee_id=assignee)
        updated += 1
    db.commit()
    return {"updated": updated, "skipped": skipped}


@router.get("/{dev_id}", response_model=DeviationDetailOut)
def get_deviation(dev_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    it = _load_scoped(db, user, dev_id)
    base = _decorate(db, [it])[0]
    out = DeviationDetailOut(**base.model_dump())
    authors = {c.author_id for c in it.comments if c.author_id}
    names = {}
    if authors:
        names = {u.id: (u.full_name or u.username)
                 for u in db.scalars(select(User).where(User.id.in_(authors)))}
    comments = []
    for c in it.comments:
        o = DeviationCommentOut.model_validate(c)
        o.author_name = names.get(c.author_id) if c.author_id else None
        comments.append(o)
    out.comments = comments
    return out


@router.patch("/{dev_id}", response_model=DeviationItemOut)
def patch_deviation(dev_id: int, body: DeviationPatch, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    it = _load_scoped(db, user, dev_id)
    data = body.model_dump(exclude_unset=True)
    _apply_change(db, it, user, new_status=data.get("status"), note=data.get("note"),
                  assignee_id=data["assignee_id"] if "assignee_id" in data else _UNSET)
    db.commit()
    return _decorate(db, [it])[0]


@router.post("/{dev_id}/comments", response_model=DeviationCommentOut)
def add_comment(dev_id: int, body: DeviationCommentIn, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    it = _load_scoped(db, user, dev_id)
    c = DeviationComment(deviation_id=it.id, author_id=user.id, body=body.body)
    db.add(c)
    db.commit()
    db.refresh(c)
    o = DeviationCommentOut.model_validate(c)
    o.author_name = user.full_name or user.username
    return o
