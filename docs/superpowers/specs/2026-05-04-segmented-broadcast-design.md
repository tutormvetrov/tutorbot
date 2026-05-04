# Сегментные рассылки — дизайн

**Дата:** 2026-05-04
**Статус:** утверждён

---

## Цель

Добавить экран фильтрации сегментов в существующий флоу рассылки. Администратор выбирает
комбинацию фильтров перед тем, как попасть на экран выбора получателей — список уже
предфильтрован и предвыбран, ручная коррекция по-прежнему доступна.

---

## FSM-поток

```
тип рассылки
    → ввод / подтверждение текста
    → waiting_for_segment_filter   ← новое состояние
    → waiting_for_recipients       ← без изменений (предфильтрованный список)
    → отправка
```

Кнопка **"Без фильтров → все ученики"** пропускает экран фильтров и переходит
к `waiting_for_recipients` с полным списком учеников (поведение как до изменений).

---

## Модель данных фильтров

Хранится в FSM под ключом `segment_filters`:

```python
{
    "stages":  [],   # "new" | "regular" | "veteran"
    "levels":  [],   # "A1" | "A2" | "B1" | "B2" | "C1" | "C2"
    "formats": [],   # "online" | "offline"
    "balance": [],   # "has" | "low" | "none"
    "types":   [],   # "solo" | "pair"
}
```

Пустой список в категории — категория не активна.
Если все категории пусты — в выборку попадают все активные ученики.

### Пороги баланса

| Значение | Уроков |
|----------|--------|
| `"none"` | 0      |
| `"low"`  | 1–2    |
| `"has"`  | ≥ 3    |

### Стадия ученика

Вычисляется через существующую `compute_student_stage()` из `utils/ui_text.py`.
Приоритет: `student_stage_override` → авто-вычисление из `cached_first_lesson_date`.

---

## Логика OR-фильтрации

Студент попадает в результирующий список, если хотя бы одно активное значение
из любой категории соответствует его атрибутам:

```python
def _matches_segment_filters(student: dict, filters: dict) -> bool:
    if not any(filters.values()):
        return True
    checks = [
        (filters["stages"],  student["stage"]),
        (filters["levels"],  student["level"]),
        (filters["formats"], student["lesson_format"]),
        (filters["balance"], student["balance_bucket"]),
        (filters["types"],   student["student_type"]),
    ]
    return any(bucket and val in bucket for bucket, val in checks)
```

Пример: выбраны `stage=new` и `format=online` → попадают ученики, которые
являются новыми **или** занимаются онлайн (не обязательно оба условия).

---

## БД: новый запрос

**`get_students_for_broadcast()`** в `utils/db_api/users.py`.

Возвращает для каждого активного не-внутреннего студента:

| Поле | Источник |
|------|----------|
| `telegram_id` | `users` |
| `full_name` | `users` |
| `speech_style` | `users` |
| `level` | `users` |
| `lesson_format` | `users` |
| `cached_first_lesson_date` | `users` |
| `student_stage_override` | `users` |
| `balance` | `SUM(payments.lessons_remaining)` WHERE `lessons_remaining > 0` |
| `is_pair` | `TRUE` если студент состоит в группе с `group_type='pair'` |

После получения строк Python-код вычисляет `stage` и `balance_bucket`, добавляет
`student_type = "pair" if is_pair else "solo"`.

---

## Клавиатура фильтров

Функция `segment_filter_keyboard(filters: dict, students_cache: list)` в `keyboards/inline.py`.

Клавиатура **перерисовывается при каждом нажатии**. Счётчик в кнопке подтверждения
пересчитывается на лету из `students_cache`.

### Макет

```
┌──────────────────────────────────────────────┐
│  🆕 Новый ☐  │  📗 Основной ☐  │  🏅 Давний ☐  │
├──────────────────────────────────────────────┤
│  A1 ☐  │  A2 ☐  │  B1 ☐  │  B2 ☐  │  C1 ☐  │  C2 ☐  │
├──────────────────────────────────────────────┤
│  💻 Онлайн ☐          │        Офлайн ☐  │
├──────────────────────────────────────────────┤
│  💰 Есть ☐  │  Мало (1–2) ☐  │  Нет ☐  │
├──────────────────────────────────────────────┤
│  👤 Один ☐            │          👥 Пара ☐  │
├──────────────────────────────────────────────┤
│  ✖️ Сбросить  │  📤 Показать N чел. →  │
└──────────────────────────────────────────────┘
         ↓ отдельная строка ↓
│       Без фильтров → все ученики       │
```

Активный фильтр отображается как `✅`, неактивный — `☐`.

### Callback-формат

```
bc_filter:stage:new
bc_filter:stage:regular
bc_filter:stage:veteran
bc_filter:level:A1   ... bc_filter:level:C2
bc_filter:format:online
bc_filter:format:offline
bc_filter:balance:has
bc_filter:balance:low
bc_filter:balance:none
bc_filter:type:solo
bc_filter:type:pair
bc_filter:reset          ← сбросить все фильтры
bc_filter:apply          ← перейти к списку получателей
bc_filter:skip           ← пропустить, взять всех
```

---

## Изменения в обработчиках

**`handlers/users/admin_sections/broadcast.py`**

| Функция | Тип | Описание |
|---------|-----|----------|
| `_enter_segment_filter()` | новая | Загружает кэш через `get_students_for_broadcast()`, сохраняет в FSM, показывает клавиатуру |
| `bc_filter_toggle()` | новый handler | Обрабатывает `bc_filter:<cat>:<val>`, тоглит значение в `segment_filters`, перерисовывает клавиатуру |
| `bc_filter_apply()` | новый handler | Применяет `_matches_segment_filters()`, передаёт отфильтрованный список в `_enter_recipient_select()` |
| `bc_filter_skip()` | новый handler | Передаёт полный список в `_enter_recipient_select()` без фильтрации |
| `_matches_segment_filters()` | новая | OR-логика, описана выше |
| `_balance_bucket()` | новая | `int → "has" \| "low" \| "none"` |
| `_enter_recipient_select()` | изменение | Принимает опциональный `preselected_ids: set[int]` для предвыбора |

---

## Затронутые файлы

| Файл | Изменение |
|------|-----------|
| `states/registration.py` | +`waiting_for_segment_filter = State()` |
| `utils/db_api/users.py` | +`get_students_for_broadcast()` |
| `keyboards/inline.py` | +`segment_filter_keyboard()` |
| `handlers/users/admin_sections/broadcast.py` | новые функции и хендлеры (см. выше) |
| `tests/test_fsm_flows.py` | добавить шаг `waiting_for_segment_filter` в тестовый флоу рассылки |

---

## Что не входит в эту итерацию

- Сохранение именованных сегментов (пресеты) — отдельная фича
- Фильтрация по родителям / учителям
- Планировщик рассылок по сегменту (scheduled broadcasts)
