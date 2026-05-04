# Plan: Teacher Pulse - поэтапная реализация

Дата: 04.05.2026
Спека: `docs/superpowers/specs/2026-05-04-teacher-pulse-design.md`

---

## Карта параллельного исполнения

```
Stage 0 (DB)
    |
    v
Stage 1 (pulse_engine + DB mixin)
    |
    +-----+-----+-----+
    |     |     |     |
    v     v     v     |
  St.2  St.3  St.4   |
 (nudge)(dash)(touch) |
    |     |     |     |
    +-----+-----+     |
          |           |
          v           v
        St.5 (briefing)
          |
          v
        St.6 (integration)
```

Stages 2, 3, 4 выполняются параллельно после Stage 1.
Stage 5 зависит от Stage 3 (роутер для callback) и Stage 1.
Stage 6 последний, последовательный.

---

## Stage 0: DB-миграции (фундамент)

**Цель:** Создать все таблицы и колонки, от которых зависят последующие этапы.

**Файлы:**

| Файл | Изменение |
|------|-----------|
| `utils/db_api/schema.py` | Три новых метода миграции в `DatabaseSchemaMixin`: `migrate_homework_nudges()`, `migrate_student_touches()`, `migrate_users_add_touches_enabled()`. Все три вызываются из `create_tables_if_not_exists()` после `migrate_users_add_tariff_text()`. |

**Таблица `homework_nudges`:**

```sql
CREATE TABLE IF NOT EXISTS homework_nudges (
    id SERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES users(telegram_id),
    lesson_id INTEGER NOT NULL REFERENCES lessons(id),
    stage INTEGER NOT NULL DEFAULT 1,
    sent_at TIMESTAMP NOT NULL DEFAULT now(),
    resolved_at TIMESTAMP,
    resolution TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS homework_nudges_open_idx
ON homework_nudges (student_id) WHERE resolved_at IS NULL;
```

**Таблица `student_touches`:**

```sql
CREATE TABLE IF NOT EXISTS student_touches (
    id SERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES users(telegram_id),
    template_type TEXT NOT NULL,
    template_key TEXT,
    context_source TEXT NOT NULL,
    context_snippet TEXT,
    sent_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS student_touches_student_sent_idx
ON student_touches (student_id, sent_at DESC);
```

**Новая колонка:**

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS touches_enabled BOOLEAN DEFAULT true;
```

**Тест:** `make check` - существующие тесты не ломаются.

---

## Stage 1: `pulse_engine` + DB mixin (общее ядро)

**Цель:** Общий движок вычислений и запросов, от которого зависят все 4 компонента. Чистые функции + DB reads, без Telegram I/O.

### Новые файлы

**`utils/pulse_engine.py`:**

- `compute_student_health(db, student_id) -> dict` - возвращает `{"color", "reasons", "days_since_last_lesson", "days_since_last_hw", "balance", "open_nudges", "streak_weeks"}`. Логика светофора по спеке секция 4.
- `compute_all_health(db) -> list[dict]` - здоровье всех активных учеников, сортировка красные-жёлтые-зелёные. Пары агрегируются по `primary_student_id`.
- `build_pulse_text(health_list, today_date) -> str` - форматирование экрана Пульса.
- `build_briefing_text(health_list, today_lessons, today_date) -> str` - форматирование утренней сводки.
- `is_quiet_hours(dt) -> bool` - True если dt между 22:00 и 08:00 МСК.
- `next_active_time(dt) -> datetime` - если тихие часы, возвращает 08:00 МСК.

**`utils/db_api/pulse.py`** - новый mixin `DatabasePulseMixin`:

- `get_all_pulse_data() -> list[dict]` - один запрос: JOIN `users`, `lessons`, `homework`, `payments`, `homework_nudges` для всех активных учеников.
- `get_pulse_student_data(student_id) -> dict` - данные одного ученика.
- `get_open_nudge(student_id, lesson_id) -> dict|None` - открытый nudge для урока.
- `create_nudge(student_id, lesson_id, stage) -> int` - создание nudge.
- `resolve_nudge(nudge_id, resolution) -> None` - закрытие nudge.
- `escalate_nudge(nudge_id, new_stage) -> None` - повышение ступени.
- `get_recent_touches(student_id, since) -> list[dict]` - для rate-limiting (2/неделю).
- `log_touch(student_id, template_type, template_key, context_source, context_snippet) -> None` - запись касания.
- `get_today_lessons(today_start, tomorrow_start) -> list[dict]` - уроки на сегодня (для сводки).
- `get_lessons_needing_nudge() -> list[dict]` - уроки за 24ч без ДЗ и без закрытого nudge.
- `get_touch_candidates() -> list[dict]` - кандидаты на касание: активные, `touches_enabled=true`, с last/next lesson, teacher_comment, HW, goal.

### Изменения в существующих файлах

| Файл | Изменение |
|------|-----------|
| `utils/db_api/postgresql.py` | Добавить `DatabasePulseMixin` в MRO класса `Database` и импорт. |

### Тесты

**`tests/test_pulse_engine.py`:**

- Пороги светофора: баланс 0 = красный, 1 = жёлтый, 2+ = зелёный.
- Тайминг ДЗ: >24ч = красный, >6ч = жёлтый, <6ч = зелёный.
- Разрыв уроков: >14 дней = красный, 7-14 = жёлтый, <7 = зелёный.
- Комбинации: несколько условий, побеждает худший цвет.
- Агрегация пар.
- Формат `build_pulse_text`.
- Формат `build_briefing_text`.
- Граничные условия тихих часов.
- Паттерн `FakeDB` из `tests/test_admin_today.py`.

---

## Stage 2: ДЗ-надзиратель (параллельно)

**Цель:** 3-ступенчатая эскалация когда ДЗ не отправлено после урока.

### Новые файлы

**`utils/nudge_engine.py`:**

- `check_and_send_nudges(bot, db) -> dict` - точка входа для scheduler. Запрашивает `get_lessons_needing_nudge()`, определяет ступень, уважает тихие часы, шлёт сообщения админу.
- `_build_nudge_text(student_name, stage, hours_since_lesson) -> str` - текст по ступеням: мягкий (1), настойчивый (2), финальный (3).
- `_build_nudge_keyboard(student_id, nudge_id, stage) -> InlineKeyboardMarkup` - ступень 1: только «Отправить ДЗ»; ступень 2: + «Пропустить»; ступень 3: + «Урок был без ДЗ».
- `handle_hw_auto_resolve(db, student_id, lesson_date) -> bool` - вызывается при создании ДЗ: закрывает открытые nudge.

### Изменения в существующих файлах

| Файл | Изменение |
|------|-----------|
| `keyboards/inline.py` | Добавить `make_nudge_keyboard(student_id, nudge_id, stage)`. Callbacks: `nudge:hw:{student_id}`, `nudge:skip:{nudge_id}`, `nudge:nohw:{nudge_id}`. |
| `utils/ui_text.py` | Добавить `NUDGE_STAGE_1_TEXT`, `NUDGE_STAGE_2_TEXT`, `NUDGE_STAGE_3_TEXT`, `build_nudge_message()`. |
| `utils/scheduler.py` | Добавить `homework_nudge_job` + регистрация `CronTrigger(minute="0,30")`. |

### Тесты

**`tests/test_nudge_engine.py`:**

- Прогрессия эскалации: ступень 1 через +2ч, ступень 2 через +6ч, ступень 3 через +24ч.
- Авто-закрытие при отправке ДЗ.
- Тихие часы: nudge в 23:00 откладывается на 08:00.
- Парный nudge: один на пару через `primary_student_id`.
- Видимость кнопок по ступеням.

---

## Stage 3: Экран «Пульс» (параллельно)

**Цель:** Админский экран-светофор + команда `/pulse`.

### Новые файлы

**`handlers/users/admin_sections/pulse.py`** - Router:

- Обработчик `admin:pulse`: вызывает `compute_all_health(db)`, `build_pulse_text()`, отправляет с inline-клавиатурой.
- Обработчик `pulse:student:{student_id}`: навигация в карточку ученика (переиспользование из `students.py`).
- Обработчики nudge-callbacks (`nudge:hw:*`, `nudge:skip:*`, `nudge:nohw:*`): закрытие nudge, подтверждение.
- Проверка `_is_admin()` по паттерну `today.py`.

### Изменения в существующих файлах

| Файл | Изменение |
|------|-----------|
| `keyboards/inline.py` | Кнопка «Пульс» в `admin_keyboard` (после «Сегодня»). `make_pulse_keyboard(health_list)` - кнопки учеников со светофором. `make_briefing_keyboard(most_urgent_student_id)`. |
| `utils/ui_text.py` | `PULSE_HEADER`, `PULSE_EMPTY_TEXT`, `build_pulse_screen_text()` (или делегация в `pulse_engine`). |
| `handlers/users/admin_sections/__init__.py` | Импорт `pulse` в список и `__all__`. |
| `handlers/users/__init__.py` | `dp.include_router(pulse.router)` - зарегистрировать ДО `admin.router`. |
| `handlers/users/menu.py` | Обработчик `/pulse` (admin-only, по паттерну `/today`). Также `/pulse off` и `/pulse on` - флаг `pulse_enabled` в `data/ops_status.json`. |

### Тесты

**`tests/test_pulse_dashboard.py`:**

- Генерация текста Пульса с mix красных/жёлтых/зелёных.
- Сортировка (красные первые).
- Отображение пар (одна строка с обоими именами).
- Пустое состояние.
- Генерация клавиатуры.

---

## Stage 4: Межурочные касания (параллельно)

**Цель:** Персонализированные сообщения ученикам между уроками.

### Новые файлы

**`data/touch_templates.json`:**

Структура: `тип -> brand_tone -> [шаблоны]`. Типы: `progress`, `support`, `hw_nudge`, `motivation`. Тона: `warm`, `premium`, `strict`, `neutral`. Плюс `_pair`-варианты. Плейсхолдеры: `{name}`, `{topic}`, `{partner}`, `{N}`.

**`utils/touch_engine.py`:**

- `parse_teacher_comment(comment) -> dict` - keyword/pattern-извлечение. Паттерны: «разобрали X», «тема: X», «сложно далось X», «задание: X», «повторить X», «проблема с X». Возвращает `{"topic", "difficulty", "task", "raw_first_sentence"}`.
- `select_touch_type(comment_data, has_active_hw, streak_weeks) -> str|None` - дерево решений: comment с темой -> "progress", со сложностью -> "support", нет comment но есть ДЗ -> "hw_nudge", streak >= 3 -> "motivation", иначе None.
- `render_touch_message(template_type, student_name, context, brand_tone, speech_style, is_pair, partner_name) -> str` - загрузка шаблона из JSON, случайный выбор варианта, подстановка `choose_form` для ты/Вы.
- `should_send_touch(student_data, touches_this_week, today) -> bool` - rate-limit: max 2/неделю, не в день урока, не в тихие часы, не при балансе 0, не при `touches_enabled=false`.
- `compute_touch_send_time(last_lesson, next_lesson) -> datetime` - середина + сдвиг 2-4 часа.

### Изменения в существующих файлах

| Файл | Изменение |
|------|-----------|
| `utils/scheduler.py` | Добавить `between_lesson_touches_job` + регистрация `CronTrigger(minute=0)` (каждый час). |

### Тесты

**`tests/test_touch_engine.py`:**

- `parse_teacher_comment` с разными форматами заметок.
- `select_touch_type` - каждая ветка дерева решений.
- `render_touch_message` со всеми типами, тонами, стилями, пара/соло.
- `should_send_touch` - rate-limit, день урока, тихие часы, баланс 0, `touches_enabled=false`.
- `compute_touch_send_time` - середина промежутка со сдвигом.

---

## Stage 5: Утренняя сводка

**Цель:** Ежедневное сообщение админу в 09:00 МСК.

### Изменения в существующих файлах

| Файл | Изменение |
|------|-----------|
| `utils/scheduler.py` | Добавить `morning_briefing_job` + регистрация `CronTrigger(hour=9, minute=0)`. Проверка `pulse_enabled` из `ops_status.json`. Если нет уроков И нет проблем - не отправлять. |
| `keyboards/inline.py` | `make_briefing_keyboard` (если не добавлена в Stage 3). Callbacks: `briefing:pulse`, `briefing:hw:{student_id}`. |
| `handlers/users/admin_sections/pulse.py` | Callback-обработчики `briefing:pulse` (переход в Пульс) и `briefing:hw:{student_id}` (переход к отправке ДЗ). |
| `utils/ui_text.py` | `BRIEFING_HEADER`, `BRIEFING_NO_ISSUES`, `BRIEFING_ATTENTION_HEADER`. |

### Тесты

**`tests/test_morning_briefing.py`:**

- Текст сводки с уроками и проблемами.
- Укороченный текст (проблемы без уроков).
- Пропуск при отсутствии уроков и проблем.
- `pulse_enabled=false` подавляет отправку.
- Клавиатура с правильными кнопками.

---

## Stage 6: Интеграция и smoke

**Цель:** Связать всё вместе, проверить end-to-end.

### Задачи

1. **Авто-закрытие nudge при создании ДЗ.** Модифицировать `handlers/users/admin_sections/homework.py`: после создания записи `homework` вызвать `nudge_engine.handle_hw_auto_resolve(db, student_id, lesson_date)`.

2. **Переключатель касаний в карточке ученика.** Модифицировать `handlers/users/admin_sections/students.py`: кнопка «Касания: вкл/выкл» в клавиатуре карточки. Callback `touch:toggle:{student_id}` меняет `users.touches_enabled`.

3. **Порядок регистрации роутеров.** Убедиться, что `pulse.router` зарегистрирован перед `admin.router` в `handlers/users/__init__.py`.

4. **Обновление теста клавиатур.** В `tests/test_keyboards.py` добавить проверку кнопки «Пульс» в `admin_keyboard`.

5. **Дедупликация с `homework_gap_check_job`.** Обзор: нужно ли отключить существующий job или оставить как safety net на первый релиз. Рекомендация: оставить, пометить комментарием для deprecation.

### Тесты

**`tests/test_pulse_integration.py`:**

- E2E: FakeDB с учениками в разных состояниях -> `compute_all_health` -> проверка текста Пульса.
- E2E: симуляция цепочки nudge (урок -> +2ч -> ступень 1 -> +6ч -> ступень 2 -> ДЗ отправлено -> авто-закрытие).
- Форматирование утренней сводки на реалистичных данных.
- Touch engine генерирует валидные сообщения для всех типов шаблонов.

### Ручной smoke-чеклист

- [ ] `/pulse` показывает корректный светофор для текущей базы
- [ ] Кнопка «Пульс» в админ-панели работает
- [ ] Nudge-job срабатывает, сообщение приходит с правильными кнопками
- [ ] «Пропустить» на nudge закрывает цепочку
- [ ] Утренняя сводка приходит в 09:00 с корректными данными
- [ ] `/pulse off` подавляет сводку, `/pulse on` включает обратно
- [ ] Касание приходит ученику между уроками с релевантным контентом
- [ ] Касание не приходит при `touches_enabled=false`

---

## Сводка файлов

### Новые файлы (6 + 6 тестов)

| Файл | Назначение |
|------|-----------|
| `utils/pulse_engine.py` | Общий движок: светофор, тексты |
| `utils/nudge_engine.py` | Логика ДЗ-надзирателя |
| `utils/touch_engine.py` | Парсинг заметок, выбор и рендер касаний |
| `utils/db_api/pulse.py` | DB mixin: все pulse-запросы |
| `handlers/users/admin_sections/pulse.py` | Экран Пульса + callback-обработчики |
| `data/touch_templates.json` | Шаблоны касаний |
| `tests/test_pulse_engine.py` | Тесты движка |
| `tests/test_nudge_engine.py` | Тесты надзирателя |
| `tests/test_touch_engine.py` | Тесты касаний |
| `tests/test_pulse_dashboard.py` | Тесты экрана Пульса |
| `tests/test_morning_briefing.py` | Тесты утренней сводки |
| `tests/test_pulse_integration.py` | Интеграционные тесты |

### Изменяемые файлы (10)

| Файл | Что меняется |
|------|-------------|
| `utils/db_api/schema.py` | 3 миграции |
| `utils/db_api/postgresql.py` | `DatabasePulseMixin` в MRO |
| `utils/scheduler.py` | 3 новых джоба |
| `keyboards/inline.py` | Кнопка Пульс + 3 фабрики клавиатур |
| `utils/ui_text.py` | Тексты nudge/pulse/briefing |
| `handlers/users/admin_sections/__init__.py` | Регистрация pulse |
| `handlers/users/__init__.py` | Включение pulse.router |
| `handlers/users/menu.py` | Команда `/pulse` |
| `handlers/users/admin_sections/homework.py` | Хук авто-закрытия nudge |
| `handlers/users/admin_sections/students.py` | Переключатель касаний |
| `tests/test_keyboards.py` | Проверка кнопки Пульс |
