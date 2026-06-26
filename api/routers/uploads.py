# -*- coding: utf-8 -*-
"""Загрузка сырых выгрузок СКУД. Создание/просмотр — Кадры/Админ (просмотр и
Бухгалтер). Файлы сохраняются на диск; путь хранится в Upload.stored_path."""
import os
import shutil
import uuid

from fastapi import (APIRouter, Depends, File, Form, UploadFile, status)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import Role, UploadSource
from ..db import get_db
from ..deps import require_role
from ..models import Upload
from ..schemas import UploadOut

router = APIRouter(prefix="/uploads", tags=["uploads"])

UPLOAD_DIR = os.path.join(settings.workdir, "_uploads")


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
def upload_file(source: UploadSource = Form(...), file: UploadFile = File(...),
                db: Session = Depends(get_db),
                user=Depends(require_role(Role.admin_hr))):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload')}"
    dst = os.path.join(UPLOAD_DIR, safe)
    with open(dst, "wb") as out:
        shutil.copyfileobj(file.file, out)
    up = Upload(filename=file.filename or safe, source=source.value, stored_path=dst,
                uploaded_by=user.id, status="received")
    db.add(up)
    db.commit()
    db.refresh(up)
    return up


@router.get("", response_model=list[UploadOut],
            dependencies=[Depends(require_role(Role.admin_hr, Role.accountant))])
def list_uploads(db: Session = Depends(get_db)):
    return db.scalars(select(Upload).order_by(Upload.id.desc())).all()
