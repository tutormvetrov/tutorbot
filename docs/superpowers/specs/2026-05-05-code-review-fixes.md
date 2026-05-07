# План исправлений по код-ревью (2026-05-05)

## Контекст

Внедрены три фичи: разделение учеников (school/adult), ручная привязка родитель↔ученик, кнопка обнуления баланса. Код-ревью выявил 14 проблем разной серьёзности. Цель — устранить все, не сломав 412 проходящих тестов.

Источник изменений — текущая сессия, файлы:
- `handlers/users/admin_sections/payments.py`
- `handlers/users/admin_sections/parents.py`
- `handlers/users/admin_sections/finance.py`
- `handlers/users/start.py`
- `utils/db_api/users.py`
- `utils/db_api/balance_transactions.py`
- `keyboards/inline.py`

## Правила выполнения

1. **После каждого таска**: `cd /srv/tutorbot && .venv-dev/bin/pytest tests/ -q` — все 412 тестов должны проходить.
2. **После всех тасков**: `sudo systemctl restart tutorbot` и проверить `tail /srv/tutorbot/bot.log`.
3. **Не трогать** функциональность вне списка — это узкий патч-набор, не рефакторинг.
4. **Тексты** — по-русски, без англицизмов.
5. **Запрещённое**: amend существующих коммитов, force push, изменение схемы БД (структура таблиц не трогается).

---

## Task 1: Race condition в writeoff — обернуть в транзакцию

**Файл:** `/srv/tutorbot/utils/db_api/balance_transactions.py`

Добавить новый атомарный метод после `add_balance_transaction`:

```python
async def writeoff_negative_balance(
    self,
    student_id: int,
    note: str,
) -> int | None:
    """Обнуляет отрицательный баланс одной транзакцией.

    Возвращает добавленное количество уроков (>0) либо None,
    если баланс уже >= 0 на момент выполнения.
    """
    async with self.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(amount_lessons), 0)::int AS balance
                FROM balance_transactions
                WHERE student_id = $1
                FOR UPDATE
                """,
                student_id,
            )
            balance = int(row["balance"]) if row else 0
            if balance >= 0:
                return None
            amount = abs(balance)
            await conn.execute(
                """
                INSERT INTO balance_transactions
                    (student_id, type, amount_lessons, note)
                VALUES ($1, 'admin_writeoff', $2, $3)
                """,
                student_id, amount, note,
            )
            return amount
```

> Примечание: `FOR UPDATE` на агрегатном select сам по себе не блокирует строки, но `BEGIN/COMMIT` гарантирует, что между чтением и вставкой не пройдёт `lesson_completion_job`, потому что он использует другое соединение с собственной транзакцией.

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/payments.py`

В `admin_balance_writeoff_execute` (строки ~324-350) заменить блок чтения баланса + `add_balance_transaction` на:

```python
amount = await db.writeoff_negative_balance(
    student_id=student_id,
    note=f"Списание задолженности (admin {callback_query.from_user.id})",
)
if amount is None:
    await callback_query.answer("Баланс уже не отрицательный.", show_alert=True)
    await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
    return

await _render_admin_payments(callback_query.message, db, student_id, page=page, source=source)
await callback_query.answer(f"Баланс обнулён (+{amount}).")
```

Удалить код, который читал balance и вычислял `amount = abs(balance)` отдельно.

---

## Task 2: Хрупкая проверка `endswith("0")` → парсить число

**Файл:** `/srv/tutorbot/utils/db_api/users.py:1219` (метод `deactivate_parent_student_link`)

Заменить:
```python
return not result.endswith("0")
```
на:
```python
# asyncpg возвращает "UPDATE N" — извлекаем число
try:
    affected = int(result.split()[-1])
except (ValueError, IndexError):
    affected = 0
return affected > 0
```

Также посмотреть строку с `reactivated = not result.endswith("0")` в этом же файле (около переактивации) и применить то же исправление, если она тоже относится к UPDATE/DELETE с возможным affected > 9. Если контекст другой — оставить.

---

## Task 3: Заглушение всех Exception → конкретный TelegramBadRequest

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/payments.py:103-111`

Заменить:
```python
async def _render_pricing_rates(message: types.Message, db: Database):
    rates = list(await db.get_pricing_rates() or [])
    try:
        await message.edit_text(
            build_pricing_rates_text(rates),
            reply_markup=make_pricing_rates_keyboard(rates),
        )
    except Exception:
        pass
```

на:
```python
from aiogram.exceptions import TelegramBadRequest
# (импорт добавить в верх файла, рядом с другими aiogram-импортами)

async def _render_pricing_rates(message: types.Message, db: Database):
    rates = list(await db.get_pricing_rates() or [])
    try:
        await message.edit_text(
            build_pricing_rates_text(rates),
            reply_markup=make_pricing_rates_keyboard(rates),
        )
    except TelegramBadRequest as exc:
        # "message is not modified" — текст идентичен, ничего не делаем
        if "not modified" not in str(exc):
            raise
```

---

## Task 4: Упростить разбор `rate_raw` в admin_payment_amount_entered

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/payments.py:445-450`

Заменить:
```python
pricing_ctx = await db.get_student_pricing_context(student_id) if student_id else None
rate_raw = pricing_ctx.get("rate") if pricing_ctx else None
if rate_raw and not isinstance(rate_raw, (int, float)):
    rate = float(rate_raw.get("amount", 0) if hasattr(rate_raw, "get") else 0)
else:
    rate = float(rate_raw or 0)
```

на:
```python
def _extract_rate_amount(rate_obj) -> float:
    """rate_obj может быть None, числом или asyncpg.Record/dict с полем amount."""
    if rate_obj is None:
        return 0.0
    if isinstance(rate_obj, (int, float)):
        return float(rate_obj)
    try:
        return float(rate_obj["amount"] or 0)
    except (KeyError, TypeError):
        return 0.0
```

Вынести `_extract_rate_amount` как module-level функцию (рядом с `_student_return_view`). В `admin_payment_amount_entered`:

```python
pricing_ctx = await db.get_student_pricing_context(student_id) if student_id else None
rate = _extract_rate_amount(pricing_ctx.get("rate") if pricing_ctx else None)
```

---

## Task 5: Сохранять страницу при привязке/отвязке родителя

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/parents.py`

Текущие callback-форматы:
- `admin:parent:link_student:{parent_id}` — добавить `:{page}`
- `admin:parent:pick_student:{parent_id}:{student_id}` — добавить `:{page}`
- `admin:parent:unlink:{link_id}:{parent_id}` — добавить `:{page}`
- `admin:parent:unlink_confirm:{link_id}:{parent_id}` — добавить `:{page}`

В `keyboards/inline.py` (или там, где формируется карточка родителя — `make_admin_parent_card_keyboard`) page уже известна — добавить её в URL обеих кнопок («➕ Привязать ученика» и «✕ Отвязать»).

В каждом из 4 обработчиков:
1. Парсить `page` дополнительным элементом, fallback `0` если отсутствует.
2. В рендер карточки родителя передавать сохранённую `page`, а не жёсткий `0`.
3. Кнопка «◀️ Назад» в picker'е тоже должна вести на правильную страницу.

После изменения проверить, что тест `test_admin_parent_management` (если есть для этих handler'ов) обновлён.

---

## Task 6: Helper для парсинга админских callback

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/common.py`

Добавить функцию (рядом с существующим `parse_admin_student_picker_callback_data`):

```python
def parse_admin_callback(data: str, expected_min_parts: int) -> list[str]:
    """Сплитит callback по ':' и валидирует минимальную длину.

    При недостатке частей — поднимает ValueError с понятным сообщением.
    Используется в обработчиках admin:* для устойчивости к опечаткам в шаблонах.
    """
    parts = data.split(":")
    if len(parts) < expected_min_parts:
        raise ValueError(
            f"callback {data!r}: ожидалось ≥{expected_min_parts} частей, получено {len(parts)}"
        )
    return parts
```

В `parents.py` (4 обработчика linking) и в `payments.py` (writeoff_ask, writeoff_do) заменить `callback_query.data.split(":")` на:

```python
parts = parse_admin_callback(callback_query.data, expected_min_parts=N)
```

Где `N` — минимальное число частей для каждого конкретного callback. Если при разборе будет `ValueError` — пусть всплывёт; глобальный error handler в `app.py:88-95` поймает и покажет «⚠️ Внутренняя ошибка».

Импорт добавить через `from handlers.users.admin_sections.common import parse_admin_callback`.

---

## Task 7: Транзакция и сохранение informal в toggle_student_type

**Файл:** `/srv/tutorbot/utils/db_api/users.py:1162-1177`

Заменить тело метода на:

```python
async def toggle_student_type(self, telegram_id: int) -> str:
    """Переключает тип ученика. Сохраняет informal-style при возврате в adult."""
    async with self.pool.acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow(
                "SELECT student_type, speech_style FROM users WHERE telegram_id = $1",
                telegram_id,
            )
            current_type = (user["student_type"] if user else "adult") or "adult"
            current_style = (user["speech_style"] if user else "formal") or "formal"

            if current_type == "schoolchild":
                # Возврат в adult: если до этого был informal — восстановить informal,
                # иначе — formal (нельзя оставить schoolchild для взрослого).
                new_type = "adult"
                new_style = "informal" if current_style == "informal" else "formal"
            else:
                new_type = "schoolchild"
                new_style = "schoolchild"

            await conn.execute(
                "UPDATE users SET student_type = $1, speech_style = $2 WHERE telegram_id = $3",
                new_type, new_style, telegram_id,
            )
            return new_type
```

> Полное сохранение informal через цикл `adult(informal) → schoolchild → adult` всё ещё теряет сигнал (мы не запоминаем, что предыдущий стиль был informal — `current_style` будет `schoolchild` в момент обратного перехода). Это известный компромисс из спеки. Этот патч не решает его полностью, но гарантирует, что **исходный** informal не теряется при первом же тоггле.

---

## Task 8: Вынести SELECT-with-JOIN в метод БД

**Файл:** `/srv/tutorbot/utils/db_api/users.py`

Добавить рядом с `deactivate_parent_student_link`:

```python
async def get_parent_student_link(self, link_id: int):
    """Возвращает запись student_parent с присоединённым именем ученика."""
    return await self.execute(
        """
        SELECT sp.id, sp.parent_id, sp.student_id, sp.student_info, sp.is_active,
               u.full_name AS student_name
        FROM student_parent sp
        LEFT JOIN users u ON u.telegram_id = sp.student_id
        WHERE sp.id = $1
        """,
        link_id, fetchrow=True,
    )
```

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/parents.py:505-509`

Заменить inline-запрос на:
```python
link = await db.get_parent_student_link(link_id)
```

---

## Task 9: Поправить UX copy в подтверждении writeoff

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/payments.py:312-320`

Заменить:
```python
"Создаётся запись «Списание задолженности».",
```
на:
```python
"Будет создана запись «Списание задолженности».",
```

---

## Task 10: Параллельные запросы в finance

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/finance.py:31-35`

Заменить:
```python
income_week = await db.get_income_period(_week_start())
income_month = await db.get_income_period(_month_start())
discipline = list(await db.get_payment_discipline() or [])
tariff_stats = list(await db.get_tariff_stats() or [])
forecast_data = list(await db.get_forecast_data() or [])
```

на:
```python
import asyncio  # если ещё не импортирован — добавить в верх файла

income_week, income_month, discipline_raw, tariff_raw, forecast_raw = await asyncio.gather(
    db.get_income_period(_week_start()),
    db.get_income_period(_month_start()),
    db.get_payment_discipline(),
    db.get_tariff_stats(),
    db.get_forecast_data(),
)
discipline = list(discipline_raw or [])
tariff_stats = list(tariff_raw or [])
forecast_data = list(forecast_raw or [])
```

---

## Task 11: Note списания — содержит admin id

Уже включено в Task 1 (передаётся `f"Списание задолженности (admin {callback_query.from_user.id})"`). Проверить, что в обработчике этот формат используется.

Также: в `_TX_LABEL` ничего менять не надо — отображается «Списание», а полный note (с admin id) виден только если транзакция показывается с note. Если в `build_transaction_history_text` note не печатается — оставить как есть; добавлять в UI не нужно.

---

## Task 12: Защита от дубля при привязке родителя

**Файл:** `/srv/tutorbot/utils/db_api/users.py:1198-1212` (метод `create_parent_student_link`)

Перед INSERT добавить проверку на существующую активную связь:

```python
async def create_parent_student_link(self, parent_id: int, student_id: int) -> int | None:
    """Создаёт связь. Если активная связь уже существует — возвращает None."""
    async with self.pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchval(
                """
                SELECT id FROM student_parent
                WHERE parent_id = $1 AND student_id = $2 AND is_active = true
                """,
                parent_id, student_id,
            )
            if existing:
                return None
            student = await conn.fetchrow(
                "SELECT full_name FROM users WHERE telegram_id = $1",
                student_id,
            )
            student_info = student["full_name"] if student else str(student_id)
            return await conn.fetchval(
                """
                INSERT INTO student_parent (parent_id, student_id, student_info, is_active)
                VALUES ($1, $2, $3, true)
                RETURNING id
                """,
                parent_id, student_id, student_info,
            )
```

**Файл:** `/srv/tutorbot/handlers/users/admin_sections/parents.py:481-493` (`admin_parent_pick_student`)

Обработать `None`:
```python
link_id = await db.create_parent_student_link(parent_id, student_id)
if link_id is None:
    await callback_query.answer("Связь уже существует.", show_alert=True)
    await _render_admin_parent_card(callback_query.message, db, parent_id, page)
    return
student = await db.get_user(student_id)
student_name = q(student["full_name"]) if student else str(student_id)
await callback_query.answer(f"✅ {student_name} привязан(а)")
await _render_admin_parent_card(callback_query.message, db, parent_id, page)
```

> `page` берётся из callback (см. Task 5). Если Task 5 ещё не выполнен — оставить `0` временно.

---

## Task 13: Логировать устаревшие callback в process_student_type

**Файл:** `/srv/tutorbot/handlers/users/start.py:288-293`

Заменить:
```python
async def process_student_type(callback_query: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != Registration.waiting_for_student_type.state:
        await callback_query.answer()
        return
```

на:
```python
import logging
logger = logging.getLogger(__name__)  # если нет в верху файла

async def process_student_type(callback_query: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != Registration.waiting_for_student_type.state:
        logger.info(
            "stale student_type callback: user=%s state=%s data=%s",
            callback_query.from_user.id, current_state, callback_query.data,
        )
        await callback_query.answer()
        return
```

> Если `logger` уже определён в файле — переиспользовать его, не плодить.

---

## Task 14: Индекс на student_parent для производительности

**Файл:** `/srv/tutorbot/utils/db_api/schema.py`

Найти место, где создаются индексы (поиск по `CREATE INDEX`). Добавить:

```python
async def migrate_student_parent_index(self):
    await self.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_student_parent_student_active
        ON student_parent (student_id, is_active)
        """,
        execute=True,
    )
```

Зарегистрировать вызов в `create_all_tables()` (порядок — после создания `student_parent` и других индексов).

---

## Финальная проверка

1. `cd /srv/tutorbot && .venv-dev/bin/pytest tests/ -q` — 412 passed.
2. `sudo systemctl restart tutorbot` — без ошибок старта.
3. `tail -50 /srv/tutorbot/bot.log` — нет новых исключений.
4. Ручная проверка через бота:
   - Регистрация ученика → экран выбора типа → выбрать «🎒 Школьник» → дойти до конца.
   - Админ → ученик → «Финансы» → «Обнулить баланс» → подтвердить.
   - Админ → родитель → «➕ Привязать ученика» → выбрать → проверить, что вернулись на ту же страницу списка родителей.
   - Админ → родитель → «✕ Отвязать» → подтвердить → та же страница.

Все 14 тасков нужно выполнить — порядок не строгий, но рекомендуется снизу вверх (Task 14, 13, 12...): мелкие правки сначала, чтобы рефакторинг writeoff (Task 1) и helper парсинга (Task 6) делать на чистом фоне.
