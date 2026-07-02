# -*- coding: utf-8 -*-
"""Обновление данных месяца из папки с выгрузками СКУД.

Повторяет ровно то, что делает веб-приложение (роутер uploads + создание
прогона + ingestion.process_run), но без запущенного сервера: регистрирует
сырые источники как Upload, создаёт PipelineRun на период месяца и прогоняет
движок синхронно. Идемпотентно по периоду в том смысле, что каждый запуск
создаёт НОВЫЙ прогон; финальным он не делается (утверждение — отдельным
действием в приложении, /runs/{id}/finalize).

Запуск из корня репозитория:
  python -m scripts.update_month "<папка>" [--period YYYY-MM]

<папка> — каталог месяца с файлами StorK.csv, SIGUR.xlsx, report.xls и
ЛЭЗ/lez.xlsx (отсутствующие источники пропускаются). --period по умолчанию
определяется из шапки StorK.csv («Приходы и уходы с DD.MM.YYYY ...»).
Перед запуском БД должна быть мигрирована: `alembic upgrade head`.
"""
import argparse
import calendar
import os
import re
import shutil
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import settings
from api.constants import Role, UploadSource
from api.db import SessionLocal
from api.models import PipelineRun, Upload, User
from api.services import ingestion

# source -> относительный путь файла в папке месяца
SOURCE_FILES = {
    UploadSource.stork.value: "StorK.csv",
    UploadSource.sigur.value: "SIGUR.xlsx",
    UploadSource.hikvision.value: "report.xls",
    UploadSource.lez.value: os.path.join("ЛЭЗ", "lez.xlsx"),
}


def detect_period(folder: str) -> str | None:
    """Период 'YYYY-MM' из шапки StorK.csv ('... с DD.MM.YYYY по ...')."""
    path = os.path.join(folder, "StorK.csv")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        head = f.read(4096).decode("cp1251", errors="ignore")
    m = re.search(r"с\s+(\d{2})\.(\d{2})\.(\d{4})", head)
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    return f"{yyyy}-{mm}"


def register_uploads(db, folder: str, uploaded_by: int | None) -> list[int]:
    """Копирует найденные источники в uploads_path, создаёт Upload, возвращает ids."""
    os.makedirs(settings.uploads_path, exist_ok=True)
    ids = []
    for source, rel in SOURCE_FILES.items():
        src = os.path.join(folder, rel)
        if not os.path.exists(src):
            print(f"  пропуск: нет {rel} (источник {source})")
            continue
        safe = f"{uuid.uuid4().hex}_{os.path.basename(rel)}"
        dst = os.path.join(settings.uploads_path, safe)
        shutil.copy(src, dst)
        up = Upload(filename=os.path.basename(rel), source=source, stored_path=dst,
                    uploaded_by=uploaded_by, status="received")
        db.add(up)
        db.flush()
        ids.append(up.id)
        print(f"  загружен {rel} -> upload #{up.id} ({source})")
    return ids


def main():
    ap = argparse.ArgumentParser(description="Обновить данные месяца из папки выгрузок СКУД")
    ap.add_argument("folder", help="Папка месяца (StorK.csv, SIGUR.xlsx, report.xls, ЛЭЗ/lez.xlsx)")
    ap.add_argument("--period", help="Период YYYY-MM (по умолчанию — из шапки StorK.csv)")
    args = ap.parse_args()

    folder = args.folder
    if not os.path.isdir(folder):
        raise SystemExit(f"Папка не найдена: {folder}")

    period = args.period or detect_period(folder)
    if not period or not re.fullmatch(r"\d{4}-\d{2}", period):
        raise SystemExit("Не удалось определить период; задайте --period YYYY-MM")
    year, month = (int(x) for x in period.split("-"))
    pf = date(year, month, 1)
    pt = date(year, month, calendar.monthrange(year, month)[1])

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(role=Role.admin_hr.value).first()
        uploaded_by = admin.id if admin else None

        print(f"Период {period}: {pf} .. {pt}")
        print(f"Папка: {folder}")
        upload_ids = register_uploads(db, folder, uploaded_by)
        if not upload_ids:
            raise SystemExit("Не найдено ни одного источника — обновление отменено")

        run = PipelineRun(created_by=uploaded_by, upload_ids=upload_ids, status="queued",
                          period_from=pf, period_to=pt, period_label=period)
        db.add(run)
        db.commit()
        run_id = run.id
        print(f"Создан прогон #{run_id}; запускаю обработку...")
    finally:
        db.close()

    # Синхронный прогон (та же функция, что фоновая задача API).
    ingestion.process_run(run_id, SessionLocal)

    db = SessionLocal()
    try:
        run = db.get(PipelineRun, run_id)
        print(f"\nПрогон #{run_id}: статус={run.status}")
        if run.status == "done":
            print(f"  сотрудников={run.n_employees}, дней-записей={run.n_day_records}")
            print(f"  Утвердить финальным: POST /api/runs/{run_id}/finalize "
                  f"(или кнопкой в приложении).")
        else:
            print(f"  ОШИБКА: {run.error_text}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
