# ROADMAP — закрытие месяца, отклонения, объяснение дня, период прогона

Статус: **РЕАЛИЗОВАНО — шаги 0–4** (объяснение дня, период/финализация, очередь
отклонений, центр закрытия). Проверено: pytest 93 passed/1 skipped, ruff clean,
oxlint clean, vite build, alembic upgrade head/downgrade base (5 ревизий).
Не закоммичено; на рабочей БД нужен `alembic upgrade head`.

Четыре приоритетные фичи — это **не четыре независимые задачи, а четыре слоя одной оси**:
«период → проблемы дня → разбор → закрытие». Они склеиваются тремя общими основаниями,
которые строятся **один раз** (шаг 0) и переиспользуются.

**Сквозной принцип: движок `engine/*` НЕ меняется ни в одной фиче.** Вся нормализация
кодов отклонений, объяснения и оси периода живут в API-слое поверх неизменного вывода
движка → golden/parity-тесты против легаси остаются байт-в-байт.

## Решения владельца (зафиксированы)

1. **Период прогона:** поддерживаем и цельный месяц, и произвольный диапазон — для
   создания прогонов и для diff. **Закрытие месяца — только по цельному месяцу**
   (`period_label='YYYY-MM'`); диапазонные прогоны это инструмент анализа/сверки,
   они не «закрывают месяц».
2. **Норма неполного месяца:** пропорция по числу рабочих дней, для всех графиков
   (см. §3, шаг 2).
3. **Жёсткие блокеры закрытия (→ HTTP 409):** прогон не `done` · нерешённые алиасы > 0 ·
   сотрудники без графика > 0 · сотрудники без отдела > 0. Остальное (неподтверждённые
   отгулы, открытые отклонения, «потерянные» ФИО) — предупреждения в чек-листе, не блок.

---

## 1. Проверенные дефекты, которые план обязан учесть

Найдены критиком и подтверждены прямым чтением кода. Это правки **в самом плане**, не в текущем коде.

| # | Дефект | Где | Решение в плане |
|---|--------|-----|-----------------|
| 1 | `dev_code()` нельзя распознавать re-entry по `DEV_LABELS[DEV_REENTRY]` (`"Выход с территории > 30 мин"`) — фактическая строка это `f"Выход с территории {mins} мин (...)"`, `startswith` по лейблу всегда False | [engine/compute.py:332](engine/compute.py#L332) vs [engine/model.py:109](engine/model.py#L109) | Распознавать по **литеральному префиксу** `"Выход с территории "`; unit-тест на фактическую строку с минутами, а не на лейбл |
| 2 | `period_norm` суммирует **цельные** месячные `ScheduleNorm`, не масштабируется днями периода → процент неполного месяца занижен. Parity-тест «полный span» это маскирует | [engine/compute.py:256-260](engine/compute.py#L256) | Явная правка расчёта нормы (пропорция, §3 шаг 2) + **отдельный** фикстур-тест на половину месяца |
| 3 | Имя Pydantic-схемы `PeriodOut` уже занято (свод сотрудника за прогон) | [api/schemas.py:340](api/schemas.py#L340) | Новую схему месяца назвать `MonthPeriodOut`; `PeriodOut` не трогаем |
| 4 | Добавление `thresholds` в `return compute_analytics` ломает распаковку 6-кортежа в двух местах | [api/services/ingestion.py:148](api/services/ingestion.py#L148), [tests/test_ingestion_roundtrip.py:65](tests/test_ingestion_roundtrip.py#L65) | Менять атомарно в одном PR; вернуть `dataclass`/`namedtuple`, чтобы будущие добавления не ломали распаковку |
| 5 | `latest_run_for_day` при равном `created_at` недетерминирован; legacy-прогоны имеют `period`/`is_final` = NULL | [api/services/employee_stats.py:17-30](api/services/employee_stats.py#L17) | Тай-брейк `created_at → max(run_id)`; `is_final` читать как `is True` (NULL = не финальный); «тот же период» для дедупа определять по месяцу `work_date`, а не по `run.period_label` |

---

## 2. Общие основания (шаг 0) — без миграций, нулевой parity-риск

### 2.1 `dev_code()` — стабильная нормализация кода отклонения
- Новый модуль `api/services/deviation_codes.py`: чистые функции
  `dev_code(item: str) -> str` и `detail_of(item: str) -> str | None`.
- 6 машинных кодов (`ONLY_INTERNAL`/`ONLY_LEZ`/`MISSING_ENTRY`/`MISSING_EXIT`/
  `TIME_MISMATCH`/`IMPLAUSIBLE_HOURS`) возвращаются как есть.
- re-entry-строка распознаётся по **литеральному префиксу** `"Выход с территории "`
  → код `REENTRY_GAP`, минуты/время отдаются отдельно как `detail`.
- Зеркало на фронте — `devCode()` в [api.ts](web/src/api.ts) рядом с `DEV_LABELS`.
- Движок не трогаем; `report.py` (`write_deviations_sheet`) не трогаем.

### 2.2 `run.thresholds` + расширение `DayRecordOut`
- В `ingestion.process_run` сохранять фактически применённый словарь порогов
  (`{**emodel.THRESHOLDS, **load_thresholds(db)}`, [ingestion.py:46](api/services/ingestion.py#L46))
  в `run.thresholds` (колонка JSON уже есть, [models.py:151](api/models.py#L151)).
  `compute_analytics` начинает возвращать `thresholds` (см. дефект #4 — атомарно).
- Расширить `DayRecordOut` ([schemas.py:315](api/schemas.py#L315)) полями
  `raw_hours`, `original_start`, `day_norm`, `schedule_code` — колонки уже в БД
  ([models.py:191-200](api/models.py#L191)) и пишутся в `_persist`. **Миграции нет.**

### 2.3 `latest_run_for_day` — единый выбор актуального прогона
- Helper поверх `_dedup_latest` ([employee_stats.py:17](api/services/employee_stats.py#L17)) с
  детерминированным тай-брейком `created_at → max(run_id)`.
- Семантика стабильна с самого шага 1: «helper может вернуть финальный прогон».
  Реализация эволюционирует в шаге 2 (приоритет `is_final`), контракт потребителей — нет.
- Все потребители (карточка, объяснение, центр закрытия) зовут **один** helper.

---

## 3. Шаги реализации

### Шаг 1 — Объяснение расчёта по дню (ф.3)
**Без миграций, нулевой parity-риск. Даёт быстрый видимый эффект.**

- **API:** `GET /employees/{emp_id}/days/{work_date}/explain` (роли: admin_hr, accountant,
  dept_head — только свой отдел через `_require_access`, [employees.py:24-27](api/routers/employees.py#L24)).
  `work_date` в формате `DD.MM.YYYY` (строгий pattern). Опц. `?run_id=N` фиксирует прогон;
  по умолчанию — `latest_run_for_day`.
- **Сервис:** `api/services/explain.py::build_day_explanation(db, emp_id, work_date, run_id=None)`.
  Грузит `DayRecordRow` + `AccessEvent` (по `run_id`+`emp_id`+сутки) + `Schedule` **по
  `day_records.schedule_code`** (снимок прогона, не текущий `Employee.schedule_id`) +
  `thresholds` (`run.thresholds ?? load_thresholds`, с пометкой источника). `formula[]`
  строится из уже сохранённых чисел — **без пересчёта движком**.
- **Схемы:** `DayExplainOut`, `RawEvent`, `FormulaStep`, `ScheduleBrief`.
- **Фронт:** дата дня в [EmployeeCard.tsx:199](web/src/pages/EmployeeCard.tsx#L199) кликабельна →
  панель `DayExplain.tsx` (5 блоков: сырые события · выбор входа/выхода · обед+окно графика ·
  норма+пороги · пошаговая формула). Ссылка «Объяснить» из таба отклонений RunView с `?run_id`.
- **Edge-cases:** день без событий (absence/выходной) → показать причину, не пустую панель ·
  `original_start=NULL` у старых строк → «фикс. применено» без «фактически было» ·
  `schedule_code` нет в `schedules` → «график не назначен» · **ночные смены: MVP фильтрует
  события по календарным суткам `work_date` — явно помечаем как ограничение** (движок
  сопоставляет события окну смены, [shifts.py:143](engine/shifts.py#L143); для ночных объяснение
  может отличаться — не подаём как «точную трассировку» для них).
- **Тесты:** `tests/test_explain.py` (latest vs run_id · 404 · 403 dept-scope · fallback
  thresholds · день без событий · тай-брейк по `max(run_id)`).

### Шаг 2 — Период прогона: явный период, обрезка, финализация, diff (ф.4)
**Самый аккуратный шаг — реальная правка нормы + parity. Делать с золотыми тестами.**

- **Миграция (ревизия A, down_revision=`d4c8b9a637ce`)**, всё через `op.batch_alter_table`
  (SQLite): `pipeline_runs` += `is_final` Boolean · `period_label` String(7) ·
  `finalized_at` DateTime · `finalized_by` Integer FK users.id; индексы `ix_pipeline_runs_is_final`,
  `ix_pipeline_runs_period_label`. `period_from`/`period_to` уже есть ([models.py:148-149](api/models.py#L148)) —
  начинают заполняться.
- **Норма неполного месяца (пропорция по рабочим дням, все графики):**
  ```
  для каждого месяца m в периоде:
      wd_полн(m)   = рабочих дней во всём календарном месяце m   (через weekend_fn)
      wd_период(m) = рабочих дней m, попавших в [period_from, period_to]
      вклад(m)     = ScheduleNorm[(график, m)] × wd_период(m) / wd_полн(m)
  period_norm = Σ вклад(m)
  ```
  Реализуется как новый параметр границ периода в расчёте `period_norm`
  ([compute.py:256-260](engine/compute.py#L256)) — **движок остаётся вызываемым с тем же входом;
  правка в API-слое агрегации либо в чистой функции, не в parse/compute**.
  **Инвариант parity:** период покрывает месяц целиком ⇒ `wd_период == wd_полн` ⇒ коэффициент 1 ⇒
  результат идентичен текущему. Предпраздничный день (−1ч) даёт погрешность ≤1ч на стыке — принято.
- **API:** `POST /runs` += `period` (`'YYYY-MM'`) **или** `period_from`/`period_to` (ровно один способ) ·
  `GET /runs?period=` · `POST /runs/{id}/finalize` (требует `status=='done'`, снимает `is_final` со
  всех **пересекающихся** прогонов в одной транзакции, тай-брейк конфликта `max(finalized_at)`) ·
  `POST /runs/{id}/unfinalize` · `GET /runs/final?period=` · `GET /runs/{a}/diff/{b}` (сравнение по
  стабильному ключу `(employee_id, work_date)` в пересечении периодов; `added`/`removed`/`changed`).
  Экспорт `timesheet.xlsx`: если по периоду есть **чужой** финальный прогон → 409 (или `?allow_nonfinal`).
- **Обрезка на персистенции:** в `_persist` отбрасывать `DayRecordRow` вне `[period_from, period_to]`;
  `inject_absence_records` — только внутри пересечения периода; `is_final`-прогон заморожен от re-ingest.
- **Дедуп:** `latest_run_for_day` эволюционирует — при наличии `is_final`-прогона того же месяца
  (по месяцу `work_date`) берём его безусловно, иначе `max(created_at)→max(run_id)`.
- **Фронт:** форма периода в [Runs.tsx:79-97](web/src/pages/Runs.tsx#L79) (переключатель
  Месяц `<input type=month>` | Диапазон) · колонка «Период» + бейдж «★ финальный» · кнопка
  «Утвердить/Снять» в RunView · новая страница `RunDiff.tsx`.
- **Тесты:** parity «период=полный месяц ⇒ идентично» · **узкий период: percent по пропорции** ·
  finalize при `status!='done'` → 409 · «ровно один финальный» · дедуп «финальный старый > поздний
  нефинальный» · legacy NULL-период детерминирован · diff по `(emp, work_date)`.

### Шаг 3 — Рабочая очередь отклонений (ф.2)

- **Миграция (ревизия B, down_revision=A):**
  - `deviation_items`: `id` PK · `run_id` FK index · `employee_id` FK index · **`department_id`
    FK index** (денорм для скоупа dept_head, не строка `dept_name`) · `work_date` String(10) ·
    `dev_code` String(40) index · `dedup_key` String(80) **UNIQUE** index · `detail` Text ·
    `status` String(12) default `'new'` · **`is_present` Boolean default True** (анти-«висячий
    resolved») · `assignee_id` FK users.id index · `dept_name` String(255) (только отображение) ·
    `resolution_note` Text · `first_seen_at`/`last_seen_at` DateTime · `resolved_by` FK · `resolved_at`
    DateTime. Композитный индекс `(status, department_id)`.
  - `deviation_comments`: `id` PK · `deviation_id` FK index · `author_id` FK · `body` Text ·
    `old_status`/`new_status` String(12) · `created_at` DateTime. `cascade='all, delete-orphan'`.
  - `constants.DeviationStatus`: `new`/`in_progress`/`accepted`/`fixed`/`ignored`.
- **Ключ дедупа (центральное решение):** `dedup_key = f"{employee_id}|{work_date}|{dev_code}"` —
  **run-независим**. re-entry: один item на день (минуты в `detail`, **не** в ключе).
- **Ресинк в `_persist`** (после пересчёта day_records прогона):
  - существующий ключ → update `run_id`/`last_seen_at`/`detail`, `is_present=True`;
    **`status`/`assignee`/`comments` НЕ трогаем** (защита от гонки с ручным PATCH);
  - новый ключ → INSERT `status='new'`;
  - отклонение исчезло → `is_present=False` + системный комментарий, **не удалять** (аудит).
  - upsert через SELECT-then-INSERT с `IntegrityError → retry-as-update` (portable SQLite↔PG).
- **API:** `GET /deviations` (фильтры status/dev_code/dept/assignee/employee, dept_head форсит свой
  отдел) · `GET /deviations/count` (бейдж) · `GET /deviations/{id}` (+комментарии) ·
  `PATCH /deviations/{id}` (status/assignee/note → пишет строку в comments) ·
  `POST /deviations/bulk` (массовые; чужие id у dept_head → `skipped`, не 403 целиком) ·
  `POST /deviations/{id}/comments`.
- **Фронт:** страница `Deviations.tsx` (фильтры · массовый выбор · `.assignbar`) · навбейдж счётчика ·
  таб RunView переходит на серверный `GET /deviations?run_id=`.
- **Тесты:** dedup run-независим (повторный прогон не плодит дубль, сохраняет status/assignee/comments) ·
  `is_present=False` при исчезновении · status не затирается ресинком · re-entry → один item ·
  конкурентный insert → upsert без падения · dept-скоуп по `department_id` · bulk-skip.

### Шаг 4 — Центр закрытия месяца (ф.1)
**Чистый агрегатор над готовыми осями. Идёт последним.**

- **Миграция (ревизия C, down_revision=B):** `period_states`: `id` PK · `period` String(7) UNIQUE
  index · `active_run_id` FK pipeline_runs.id index · `status` String(12) default `'open'`
  (`open`/`closing`/`closed`) · `closed_by` FK · `closed_at`/`reopened_at` DateTime · `note` Text ·
  `updated_at` DateTime. `constants.PeriodCloseStatus`.
- **API (схема месяца — `MonthPeriodOut`, не `PeriodOut`!):**
  - `GET /periods` — список месяцев (DISTINCT `period_label`, NULL отсекаются) + статус закрытия.
  - `GET /periods/{period}/closing-summary` — **главный эндпоинт**: 7 блоков **серверными COUNT**
    (не списками), `period` валидируется regex `YYYY-MM` (иначе 422). `no_department` и
    `no_schedule` — **два раздельных** COUNT (комбинированный фильтр даёт AND).
    **Гейт `export_ready` (решение владельца):**
    `run.status=='done' AND aliases.unresolved==0 AND no_schedule==0 AND no_department==0`.
    Предупреждения (не блок): `absences_pending`, `deviations.open`, «потерянные» ФИО
    (`access_events.employee_id IS NULL`, distinct raw_name).
    Счётчик `resolved` берётся **LEFT JOIN от актуальных day_records** (только `is_present=True AND
    status in (accepted/fixed/ignored)`) — висячие резолюции не считаются.
  - `POST /periods/{period}/close` (admin_hr; 409 со списком блокеров при жёстких) ·
    `POST /periods/{period}/reopen` · `PUT /periods/{period}/active-run` (явный выбор финального
    среди перезапусков).
  - dept_head: блоки `aliases`/`без отдела` скрыты (он их не разрешает); отклонения/отсутствия — по
    своему отделу.
- **Фронт:** `MonthClose.tsx` — селектор месяца + бейдж статуса · 7 карточек-блоков с кнопками-
  переходами (алиасы → `/aliases`, без отдела/графика → `/employees?...`, отсутствия →
  `/absences?status=submitted`, отклонения → таб, прогон → `/runs/:id`) · чек-лист готовности ·
  кнопка «Закрыть месяц» (disabled при жёстких блокерах) · «Экспорт» финального прогона.
- **Тесты:** 7 блоков как COUNT · раздельные `no_department`/`no_schedule` · `by_code` не раздут
  (нормализация re-entry) · `export_ready` по новому гейту · `resolved` по `is_present` ·
  close с блокерами → 409 · close/reopen идемпотентны · regex периода.

---

## 4. Порядок миграций alembic

Текущий head: `d4c8b9a637ce` (phase2). Все ALTER — через `op.batch_alter_table` (render_as_batch
для SQLite, см. `alembic/env.py`). Строковые «энумы» `String(12)`, Python `default=`, без `server_default`.

1. **Шаг 0 / Шаг 1 — без миграций** (колонки `day_records`/`pipeline_runs.thresholds` уже в схеме).
2. **Ревизия A** (шаг 2): `pipeline_runs` += `is_final`, `period_label`, `finalized_at`,
   `finalized_by` + индексы.
3. **Ревизия B** (шаг 3): `deviation_items` + `deviation_comments` + индексы.
4. **Ревизия C** (шаг 4): `period_states`.

`deviation_resolutions` из исходного дизайна ф.1 **консолидирована** в `deviation_items` (ф.2) —
одна сущность, ключ совпадает. Отдельная колонка `pipeline_runs.period` не нужна — её роль
выполняет `period_label`.

---

## 5. Первый срез (делаем сразу по команде)

Шаг 0 + ядро шага 1 — нулевой parity-риск, миграций нет, демонстрируемый результат
(клик по дню → полная трассировка расчёта). Атомарный PR:

**Бэкенд (основание-0):**
- `api/services/deviation_codes.py` (НОВЫЙ): `dev_code()`/`detail_of()` + unit-тест на фактическую
  строку re-entry из `compute.py:332`.
- `api/services/ingestion.py`: `compute_analytics` возвращает `thresholds` (dataclass/namedtuple);
  `process_run` пишет `run.thresholds`; **обновить распаковку в `ingestion.py:148` и
  `tests/test_ingestion_roundtrip.py:65` в этом же PR** (дефект #4).
- `api/schemas.py`: `DayRecordOut` += `raw_hours`/`original_start`/`day_norm`/`schedule_code`.

**Бэкенд (шаг 1):**
- `api/services/explain.py` (НОВЫЙ) + `latest_run_for_day` (выделить из `_dedup_latest`,
  детерминированный тай-брейк).
- `api/routers/employees.py`: `GET /employees/{emp_id}/days/{work_date}/explain` + схемы
  `DayExplainOut`/`RawEvent`/`FormulaStep`/`ScheduleBrief`.

**Фронт (шаг 1):**
- `web/src/api.ts`: типы + `api.get(/explain)` + `devCode()` + расширение `DayRecord`.
- `web/src/pages/EmployeeCard.tsx`: кликабельная дата дня.
- `web/src/pages/DayExplain.tsx` (НОВЫЙ): панель 5 блоков.

**Тесты:** `tests/test_explain.py` + `tests/test_deviation_codes.py` + правка распаковки кортежа.

---

## 6. Оставшиеся продуктовые вопросы (не блокируют старт)

- Кто, кроме admin_hr, может закрывать/переоткрывать месяц (бухгалтер?).
- Нужен ли промежуточный статус `closing` или достаточно `open`/`closed`; блокирует ли `closed`
  повторный импорт/прогон в месяц (read-only-период) или только помечает.
- Гранулярность re-entry: один item на день (принято для MVP) vs item на эпизод.
- Severity/приоритет на отклонениях (`ONLY_INTERNAL` как потенциально дисциплинарный кейс).
- Нужно ли объяснение дня в xlsx (доп. лист) или достаточно UI.
- Поведение очереди при `unfinalize → re-ingest` финального периода.
