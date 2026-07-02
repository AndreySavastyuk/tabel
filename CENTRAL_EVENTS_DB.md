# Центральная база событий СКУД

Краткая инструкция для организации единой базы, куда 5-10 источников СКУД
отправляют события в JSON, а приложение табеля и внешние системы получают из
нее события, присутствие/отсутствие и данные за период.

## 1. Общая схема

```text
Контроллеры/СКУД -> API приема -> PostgreSQL -> API запросов -> Табель/отчеты
```

Основная идея: все источники пишут в одну центральную БД через API. Приложение
табеля не подключается к каждому контроллеру отдельно, а читает нормализованные
данные из центрального хранилища.

Для промышленной эксплуатации использовать PostgreSQL. SQLite оставить только
для локальной разработки.

## 2. Входящее событие

Минимальный JSON:

```json
{
  "controller": "SCD-012-015",
  "name": "Орлов Сергей Олегович",
  "event": "Вход",
  "date": "26.06.2026 18:29:13",
  "identify_type": "Жетон"
}
```

Поля:

| Поле | Назначение |
|---|---|
| `controller` | Код источника/контроллера |
| `name` | ФИО как пришло из источника |
| `event` | `Вход` или `Выход` |
| `date` | Дата и время события |
| `identify_type` | Способ идентификации: жетон, палец, лицо, код и т.п. |

Желательно добавить, если источник может отдать:

```json
{
  "external_event_id": "123456789",
  "employee_external_id": "000123",
  "card_id": "A1B2C3"
}
```

`external_event_id` сильно упрощает защиту от дублей. `employee_external_id`
лучше ФИО для сопоставления сотрудников.

## 3. Основные таблицы

### 3.1. Источники

```sql
create table access_sources (
    id bigserial primary key,
    code varchar(64) not null unique,
    display_name varchar(255) not null,
    timezone varchar(64) not null default 'Europe/Moscow',
    is_active boolean not null default true
);
```

`code` соответствует входящему `controller`.

### 3.2. Сырые события

```sql
create table raw_access_events (
    id bigserial primary key,
    source_id bigint not null references access_sources(id),
    controller_code varchar(64) not null,

    raw_name varchar(255) not null,
    normalized_name varchar(255) not null,
    employee_id bigint null references employees(id),
    employee_external_id varchar(128) null,
    card_id varchar(128) null,

    event_kind varchar(16) not null,
    event_ts timestamptz not null,

    identify_type varchar(128) not null,
    identify_code varchar(32) not null,
    external_event_id varchar(128) null,

    payload jsonb not null,
    payload_hash char(64) not null,
    received_at timestamptz not null default now(),

    constraint ck_raw_access_event_kind
        check (event_kind in ('entry', 'exit'))
);
```

Нормализация:

| Вход | В БД |
|---|---|
| `Вход` | `event_kind='entry'` |
| `Выход` | `event_kind='exit'` |
| `Жетон` | `identify_code='token'` |
| `Палец` | `identify_code='finger'` |
| `Лицо` | `identify_code='face'` |
| `Код` | `identify_code='pin'` |
| `Неизвестно` | `identify_code='unknown'` |

### 3.3. Индексы

```sql
create unique index uq_raw_access_external_event
on raw_access_events (source_id, external_event_id)
where external_event_id is not null;

create unique index uq_raw_access_payload_hash
on raw_access_events (source_id, payload_hash);

create index ix_raw_access_employee_ts
on raw_access_events (employee_id, event_ts);

create index ix_raw_access_source_ts
on raw_access_events (source_id, event_ts);

create index ix_raw_access_ts
on raw_access_events (event_ts);
```

Если событий станет много, таблицу можно партиционировать по месяцу через
`event_ts`.

## 4. Дедупликация

Прием событий должен быть идемпотентным: повторная отправка того же события не
должна создавать дубль.

Если есть `external_event_id`, уникальность:

```text
source_id + external_event_id
```

Если `external_event_id` нет, считать `payload_hash` по нормализованным полям:

```text
controller | normalized_name | event_kind | event_ts | identify_type
```

При конфликте уникального индекса использовать `ON CONFLICT DO NOTHING`.

## 5. Сопоставление сотрудников

ФИО из СКУД нельзя считать надежным ID. В текущем проекте уже есть нужные
таблицы:

- `employees` - сотрудники;
- `employee_aliases` - варианты ФИО из разных источников.

Алгоритм:

1. Сохранить событие с `raw_name`.
2. Построить `normalized_name`.
3. Если есть `employee_external_id` - искать сотрудника по нему.
4. Иначе искать подтвержденный alias в `employee_aliases`.
5. Если сотрудник не найден - оставить `employee_id=null` и вывести в список
   несопоставленных.

Автоматически склеивать похожие ФИО без проверки не нужно.

## 6. API приема событий

### 6.1. Отправить одно событие

```http
POST /api/access-events
Authorization: Bearer <source-token>
Content-Type: application/json
```

```json
{
  "controller": "SCD-012-015",
  "name": "Орлов Сергей Олегович",
  "event": "Вход",
  "date": "26.06.2026 18:29:13",
  "identify_type": "Жетон"
}
```

Ответ:

```json
{
  "received": 1,
  "inserted": 1,
  "duplicates": 0,
  "failed": 0
}
```

### 6.2. Отправить пачку событий

```http
POST /api/access-events/batch
Authorization: Bearer <source-token>
Content-Type: application/json
```

```json
[
  {
    "controller": "SCD-012-015",
    "name": "Орлов Сергей Олегович",
    "event": "Вход",
    "date": "26.06.2026 18:29:13",
    "identify_type": "Жетон"
  }
]
```

Ограничение пачки: например, до 1000 событий за запрос.

## 7. API запросов

API чтения нужно отделить от API приема. Источники СКУД пишут события, а табель,
дашборды и отчеты читают данные через отдельные endpoints.

Все даты в query-параметрах лучше принимать в ISO-формате:

```text
2026-06-26T00:00:00+03:00
```

Для совместимости можно дополнительно поддержать `DD.MM.YYYY HH:MM:SS`, но
внутри API сразу приводить к `timestamptz`.

### 7.1. События за период

```http
GET /api/access-events?from=2026-06-26T00:00:00+03:00&to=2026-06-27T00:00:00+03:00
```

Дополнительные фильтры:

```text
employee_id=123
controller=SCD-012-015
event_kind=entry
identify_code=token
limit=500
offset=0
```

Ответ:

```json
{
  "items": [
    {
      "id": 10001,
      "controller": "SCD-012-015",
      "employee_id": 123,
      "name": "Орлов Сергей Олегович",
      "event": "Вход",
      "event_kind": "entry",
      "date": "2026-06-26T18:29:13+03:00",
      "identify_type": "Жетон",
      "identify_code": "token"
    }
  ],
  "total": 1,
  "limit": 500,
  "offset": 0
}
```

Назначение: аудит, отладка, просмотр первичных событий.

### 7.2. Текущее присутствие

```http
GET /api/presence/current
```

Фильтры:

```text
department_id=5
controller=SCD-012-015
at=2026-06-26T18:30:00+03:00
```

Ответ:

```json
{
  "at": "2026-06-26T18:30:00+03:00",
  "items": [
    {
      "employee_id": 123,
      "name": "Орлов Сергей Олегович",
      "status": "present",
      "last_event": "Вход",
      "last_event_at": "2026-06-26T18:29:13+03:00",
      "controller": "SCD-012-015"
    }
  ]
}
```

Правило расчета: для каждого сотрудника берется последнее событие на момент
`at`. Если последнее событие `entry` - сотрудник присутствует, если `exit` -
отсутствует. Если событий нет - статус `unknown`.

### 7.3. Отсутствующие сейчас

```http
GET /api/presence/absent?at=2026-06-26T18:30:00+03:00
```

Ответ:

```json
{
  "at": "2026-06-26T18:30:00+03:00",
  "items": [
    {
      "employee_id": 124,
      "name": "Иванов Иван Иванович",
      "status": "absent",
      "last_event": "Выход",
      "last_event_at": "2026-06-26T17:50:00+03:00"
    }
  ]
}
```

Назначение: оперативный список отсутствующих. Для кадрового табеля этот endpoint
не заменяет расчет рабочего времени, он показывает только состояние по последней
проходке.

### 7.4. Присутствие за день

```http
GET /api/presence/daily?date=2026-06-26
```

Фильтры:

```text
employee_id=123
department_id=5
```

Ответ:

```json
{
  "date": "2026-06-26",
  "items": [
    {
      "employee_id": 123,
      "name": "Орлов Сергей Олегович",
      "first_entry": "2026-06-26T08:58:00+03:00",
      "last_exit": "2026-06-26T18:29:13+03:00",
      "events_count": 8,
      "has_entry": true,
      "has_exit": true,
      "status": "complete"
    }
  ]
}
```

`status`:

| Значение | Смысл |
|---|---|
| `complete` | Есть вход и выход |
| `missing_entry` | Есть выход, но нет входа |
| `missing_exit` | Есть вход, но нет выхода |
| `no_events` | Нет событий за день |

### 7.5. Данные сотрудника за период

```http
GET /api/employees/123/access-summary?from=2026-06-01&to=2026-06-30
```

Ответ:

```json
{
  "employee_id": 123,
  "name": "Орлов Сергей Олегович",
  "from": "2026-06-01",
  "to": "2026-06-30",
  "days": [
    {
      "date": "2026-06-26",
      "first_entry": "08:58",
      "last_exit": "18:29",
      "events_count": 8,
      "identify_types": ["Жетон", "Палец"],
      "status": "complete"
    }
  ]
}
```

Назначение: быстрый просмотр первичных проходов сотрудника без запуска полного
расчета табеля.

### 7.6. Несопоставленные события

```http
GET /api/access-events/unmatched?from=2026-06-01&to=2026-06-30
```

Ответ:

```json
{
  "items": [
    {
      "raw_name": "Орлов С. О.",
      "normalized_name": "орлов с о",
      "events_count": 14,
      "first_event_at": "2026-06-02T08:55:00+03:00",
      "last_event_at": "2026-06-26T18:29:13+03:00",
      "controllers": ["SCD-012-015"]
    }
  ]
}
```

Назначение: экран для администратора, где ФИО из источников привязываются к
карточкам сотрудников.

## 8. Интеграция с расчетом табеля

В текущем проекте уже есть расчетные таблицы:

- `access_events` - события конкретного `pipeline_run`;
- `day_records` - рассчитанные дни;
- `period_summaries` - итоги периода.

Новую таблицу `raw_access_events` лучше считать постоянным журналом, а
`access_events` оставить расчетным снимком.

Поток:

```text
raw_access_events -> выборка за период -> pipeline_run -> access_events -> day_records/period_summaries
```

Это важно: если сырые события позже изменились или добавились, старый расчетный
прогон остается воспроизводимым.

## 9. Минимальные технические требования

- Вся кодировка: UTF-8.
- Все даты в БД: `timestamptz`.
- Часовой пояс источника хранить в `access_sources.timezone`.
- API приема и API чтения работают только по HTTPS.
- Для каждого источника отдельный токен.
- Приложение не получает права суперпользователя в БД.
- Дубли не считаются ошибкой приема.
- Ошибочные события логируются с причиной.
- Для чтения больших периодов обязательна пагинация.

## 10. План внедрения

1. Перейти на PostgreSQL в проде.
2. Добавить миграции для `access_sources` и `raw_access_events`.
3. Реализовать `POST /api/access-events` и `POST /api/access-events/batch`.
4. Реализовать API запросов из раздела 7.
5. Добавить сопоставление `raw_name`/`employee_external_id` с сотрудником.
6. Добавить экран несопоставленных событий.
7. Научить расчет табеля брать события из `raw_access_events` за период.
8. Сверить один месяц со старой файловой схемой.
9. После сверки сделать центральную БД основным источником.

## 11. Вопросы перед разработкой

1. Может ли источник отдавать уникальный ID события?
2. Может ли источник отдавать табельный номер, ID сотрудника или ID карты?
3. События будут приходить онлайн или пачками по расписанию?
4. Нужно ли API для внешних систем только на чтение или также для правки
   сопоставлений сотрудников?
5. Какой период хранения сырых событий требуется?
