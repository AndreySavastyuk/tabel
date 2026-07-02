# Редизайн веб-интерфейса в стиле Tiimi — инструкция

Референс: [Tiimi | HR Management System](https://www.behance.net/gallery/121234853/Tiimi-HR-Management-System)
(Fikri Studio). Цель — современный, спокойный, «ненавязчивый» вид: тёмный графитовый
сайдбар с жёлтым активным пунктом, глубокий teal вместо синего для действий, пастельные
статус-бейджи, мягкие карточки.

**Объём работ:** практически весь редизайн — правки токенов и классов в
`web/src/index.css` + мелочи в `web/src/App.tsx` (брендинг) и `web/src/main.tsx` (шрифт).
Логика страниц, API и движок не трогаются.

**Чего НЕ делать:**
- Не тащить градиентные фоны и «презентационные» рамки из кейса — это оформление
  Behance-подачи, а не продукта.
- Не снижать плотность таблиц — это рабочий инструмент, данные важнее воздуха.
- Не вводить UI-библиотеки (Tailwind, MUI и т.п.) — весь стиль живёт в одном CSS-файле.
- Жёлтый использовать только с тёмным текстом поверх и только точечно (активный пункт
  меню, бренд-марка). Жёлтый текст на белом не проходит по контрасту — запрещено.

---

## 1. Дизайн-токены (`:root` в `web/src/index.css`)

Заменить текущий блок `:root` на следующий (старые переменные сохраняют имена —
остальной CSS подхватит их автоматически; добавлены новые группы `--sidebar-*`,
`--brand-*`, `--radius-lg`):

```css
:root {
  /* фон и поверхности */
  --bg: #f6f7f9;
  --panel: #ffffff;
  --surface: #ffffff;
  --surface-muted: #f7faf9;
  --surface-hover: #f0f4f3;
  --border: #e4e8e7;
  --border-strong: #ccd4d2;

  /* текст (лёгкий зелёный подтон вместо сине-серого) */
  --text: #1a2521;
  --text-soft: #35433e;
  --muted: #67736e;
  --muted-light: #96a19c;

  /* фирменные цвета: teal — действия, жёлтый — только акценты */
  --accent: #17685c;
  --accent-dark: #114f46;
  --accent-bg: #e9f3f0;
  --accent-border: #bfd9d2;
  --brand-yellow: #ffd23e;
  --brand-yellow-text: #201d12;

  /* сайдбар (новая группа) */
  --sidebar-bg: #23262c;
  --sidebar-text: #b9bec7;
  --sidebar-muted: #7d838e;
  --sidebar-hover: rgba(255, 255, 255, 0.06);
  --sidebar-border: rgba(255, 255, 255, 0.08);

  /* семантика статусов (пастельные фоны + насыщенный текст) */
  --success: #148358;
  --success-bg: #e6f5ee;
  --warning: #b45309;
  --warning-bg: #fdf3dd;
  --error: #d92d20;
  --error-bg: #fdecea;
  --info: #0e7490;
  --info-bg: #ebf7fa;

  --shadow-sm: 0 1px 2px rgba(23, 28, 26, 0.05);
  --shadow-md: 0 12px 32px rgba(23, 28, 26, 0.08);
  --radius: 10px;      /* было 8px */
  --radius-lg: 14px;   /* крупные карточки/модальные */
  --sidebar-width: 248px;
  font-family: 'Manrope Variable', Inter, 'Segoe UI', system-ui, sans-serif;
  color: var(--text);
  line-height: 1.45;
}
```

Контраст (проверено ориентировочно, при сомнении перепроверить в DevTools):
- `#17685c` на белом ≈ 5.9:1 — ок для текста и кнопок;
- `#201d12` на `#ffd23e` ≈ 11:1 — ок;
- `#b9bec7` на `#23262c` ≈ 7:1 — ок для пунктов меню.

## 2. Шрифт — Manrope (кириллица, геометрия как у Tiimi)

Tiimi свёрстан на геометрическом гротеске (DM Sans). Для кириллицы ближайший
качественный бесплатный аналог — **Manrope** (variable, полная кириллица).

1. **Остановить dev-сервер** (Vite 8 держит `.node`-бинарь — иначе EPERM, см. CLAUDE.md).
2. В `web/`: `npm i @fontsource-variable/manrope`
3. В `web/src/main.tsx` первой строкой импортов: `import '@fontsource-variable/manrope'`
4. `font-family` в `:root` уже обновлён (п. 1); Inter остаётся фолбэком.

Запасной вариант: оставить Inter — стиль не разваливается, теряется только «характер».

## 3. Сайдбар — тёмный + жёлтый активный пункт

Самая заметная часть редизайна. Правки по классам:

```css
.sidebar {
  background: var(--sidebar-bg);
  border-right: none;               /* рамка не нужна на тёмном */
}
.brand {
  border-bottom: 1px solid var(--sidebar-border);
}
.brand-mark {
  background: var(--brand-yellow);  /* было --accent */
  color: var(--brand-yellow-text);
}
.brand-text { color: #ffffff; }
.navgroup-title { color: var(--sidebar-muted); }

.sidenav a { color: var(--sidebar-text); }
.sidenav a:hover { background: var(--sidebar-hover); }
.sidenav a.active {
  background: var(--brand-yellow);
  border-color: transparent;
  color: var(--brand-yellow-text);
  font-weight: 700;
}

/* счётчик: на тёмном фоне — полупрозрачный, на жёлтом активном — инверсия */
.pill {
  background: rgba(255, 255, 255, 0.14);
  color: #ffffff;
}
.sidenav a.active .pill {
  background: var(--brand-yellow-text);
  color: var(--brand-yellow);
}

.sidefoot { border-top: 1px solid var(--sidebar-border); }
.user-avatar {
  background: rgba(255, 210, 62, 0.18);
  color: var(--brand-yellow);
}
.who-name { color: #ffffff; }
.sidefoot .muted { color: var(--sidebar-muted); }
.sidefoot button.ghost {
  background: transparent;
  color: var(--sidebar-text);
  border-color: var(--sidebar-border);
}
.sidefoot button.ghost:hover:not(:disabled) {
  background: var(--sidebar-hover);
  border-color: var(--sidebar-border);
  color: #ffffff;
}
```

Примечания:
- `.pill` используется только как бейдж в навигации (`nav-badge`) — конфликтов нет.
  Если появится вне сайдбара — завести отдельный класс.
- Брейкпоинты (≤1180px иконки, ≤640px горизонтальная полоса) менять не нужно —
  цвета наследуются от `.sidebar`; проверить визуально обе ширины.

## 4. Кнопки, ссылки, фокус

Первичные кнопки и ссылки перекрашиваются сами через `--accent` (teal). Дополнительно:

```css
button:focus-visible,
input:focus-visible,
select:focus-visible,
a:focus-visible {
  outline: 3px solid var(--accent-border);   /* уже так — просто станет teal */
  outline-offset: 2px;
}
```

`button.link` / `button.ghost` тоже подтянутся через переменные — правок не требуют
(hover уже на `--accent-bg`/`--accent-border`).

## 5. Вкладки — uppercase как в Tiimi

```css
.tab {
  text-transform: uppercase;
  font-size: 12px;
  letter-spacing: 0.06em;
  font-weight: 750;
  padding: 10px 14px;
}
.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
```

Проверить самые длинные ярлыки вкладок в «Администрировании» — если uppercase
делает их громоздкими, оставить обычный регистр, но сохранить вес/размер.

## 6. Бейджи статусов — пастель

`--*-bg`-переменные уже смягчены в п. 1; захардкоженные цвета текста заменить:

```css
.st-queued  { background: #eef1f0; color: #4c5853; }
.st-running { background: var(--warning-bg); color: var(--warning); }
.st-done    { background: var(--success-bg); color: var(--success); }
.st-failed  { background: var(--error-bg);  color: var(--error); }
```

То же для `.error` (текст `#991b1b` → `var(--error)`), `.ok-box` (`#166534` →
`var(--success)`), `.warn-txt` (`#92400e` → `var(--warning)`) и ячеек отчётов
`.miss`/`.fix`/`.bad` (цвета текста на переменные; фоны уже пастельные).

## 7. Карточки и метрики

```css
.card { border-radius: var(--radius-lg); }
.metric-card { border-radius: var(--radius-lg); }
.metric-label {
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 11px;
}
.qcard { border-radius: var(--radius-lg); }
```

Карточки готовности в «Закрытии месяца» — цветная полоса сверху (как у kanban-колонок
Tiimi), вместо текущей слева:

```css
.readiness-card {
  border-top: 3px solid var(--warning);
  border-left: 1px solid var(--border);   /* вернуть обычную рамку слева */
  border-radius: var(--radius);
}
.readiness-card.ok       { border-top-color: var(--success); border-left-color: var(--border); }
.readiness-card.blocking { border-top-color: var(--error);   border-left-color: var(--border); }
.readiness-card.warn     { border-top-color: var(--warning); border-left-color: var(--border); }
```

## 8. Таблицы

Заголовки — мелкий uppercase с разрядкой (фирменный приём Tiimi), hover — тёплый
серо-зелёный вместо голубого:

```css
table.grid thead th {
  background: var(--surface-muted);   /* было #f8fafc */
  color: var(--muted);                /* было #475467 */
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
table.grid tbody tr:hover td { background: #f4f8f6; }  /* было #f9fbff */
.totalrow td { background: var(--surface-muted); }
.we { background: #eef3f1; }          /* выходной: был голубой #eef4ff */
```

`table.grid.inner thead th` — тот же `--surface-muted`.

## 9. Календарь

Семантика цветов дней сохраняется (красный праздник, зелёный перенос и т.д.),
меняются только «синие» элементы — они подтянутся через `--accent`
(`.mhours`, `.calday.today`). Дополнительно выровнять серый выходного:

```css
.calday.weekend { background: #e8ecea; }   /* был сине-серый #e2e8f0 */
.cd.weekend     { background: #e8ecea; }
```

## 10. Логин

Правок почти нет: карточка на светлом фоне, кнопка станет teal автоматически.
Опционально — жёлтая бренд-марка над заголовком (тот же `.brand-mark`).

## 11. Печать (`@media print`)

Ничего не менять: сайдбар уже скрывается, фоны белые. После правок открыть
`/employees/:id/report` → печать → убедиться, что пастельные фоны читаемы в ч/б
(они светлее прежних, риска нет).

---

## Порядок выполнения (коммитить по фазам)

| Фаза | Что | Файлы | Эффект |
|---|---|---|---|
| 1 | Токены `:root` + шрифт | `index.css`, `main.tsx`, `package.json` | всё приложение мягко перекрашивается |
| 2 | Тёмный сайдбар | `index.css` (п. 3) | главный визуальный сдвиг |
| 3 | Контролы: вкладки, бейджи, фокус | `index.css` (п. 4–6) | детали |
| 4 | Карточки, таблицы, календарь | `index.css` (п. 7–9) | доводка |
| 5 | Визуальный проход по страницам + правки по месту | — | QA |

Каждая фаза — рабочее состояние; можно останавливаться после любой.

## Чек-лист проверки (после каждой фазы — минимум пп. 1–2)

1. `web/`: `npm run lint` — ноль предупреждений.
2. `web/`: `npm run build` — `tsc -b && vite build` зелёные.
3. Визуально на `:5173` под всеми ролями (`admin/admin`, `buh/buh`, `ruk/ruk`) —
   у ролей разный состав меню, активный пункт и бейджи должны читаться.
4. Ширины 1400 / 1100 (иконочный сайдбар) / 800 / 600 (горизонтальная полоса) px.
5. Страницы с максимумом статусов: «Закрытие месяца» (readiness-карточки),
   «Прогоны» (st-* бейджи), «Отклонения», «Календарь» (легенда), RunView (ячейки
   `.miss`/`.fix`/`.we`).
6. Печать отчёта сотрудника (Ctrl+P на `/employees/:id/report`).
7. Контраст выборочно: активный пункт меню, teal-кнопка, warning-бейдж
   (DevTools → Accessibility → Contrast).

## Критерии готовности

- Ни одного «старого» синего (`#2563eb`, `#eff6ff`, `#e0ecff`, `#eef4ff`, `#f9fbff`) в CSS.
- Жёлтый встречается только: активный пункт меню, бренд-марка, счётчик на активном пункте.
- Плотность таблиц и все брейкпоинты не изменились.
- Тесты/линт/сборка зелёные; движок и API не тронуты.
