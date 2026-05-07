# Spec: Parent Role Overhaul — Engagement Mode + Connectivity Fixes

Дата: 2026-05-05
Автор: brainstorm + аудит логики
Статус: к реализации одним изменением

---

## 1. Контекст и цели

Аудит роли «Родитель» вскрыл восемь дефектов разной серьёзности — от критического (родитель при самоудалении уничтожает данные ученика) до косметических (после регистрации показывается клавиатура без только что созданной кнопки ребёнка).

Параллельно владелец проекта попросил дать родителю возможность выбрать степень вовлечённости в учебный процесс ребёнка:

1. **Активное наблюдение** — родитель хочет видеть домашки, учебный план и расписание ребёнка.
2. **Доверительный режим** — родитель оставляет учёбу самому ребёнку и преподавателю; видит только организационное (расписание, оплаты, связь с преподавателем).

Цель спеки — закрыть оба пласта одним связным изменением, без раздувания и без половинчатых решений.

### Не-цели

- Не меняем сценарий регистрации ученика, ученика-в-паре или админа.
- Не вводим отдельную «вкладочную» навигацию.
- Не делаем разные режимы для разных детей одного родителя в первой итерации (один режим = на родителя). Если позже понадобится — расширим до per-link.
- Не трогаем preview-mode админа, кроме точечного фикса (homework:file).

---

## 2. Engagement mode — модель данных и UX

### 2.1 Модель

Добавляем колонку `engagement_mode` в таблицу `users` (только заполняется для `role = 'parent'`):

```sql
ALTER TABLE users
ADD COLUMN IF NOT EXISTS engagement_mode TEXT DEFAULT 'active';
```

Допустимые значения:
- `'active'` — родитель видит всё, что относится к ребёнку (расписание, ДЗ, учебный план, оплаты).
- `'trust'` — родитель видит только организационное (расписание, оплаты, написать преподавателю); домашка и учебный план скрыты.

Default `'active'` сохраняет текущее поведение для уже зарегистрированных родителей.

### 2.2 UX в регистрации

После шага `waiting_for_child_age` добавляется новый шаг `waiting_for_engagement_mode` (5-й и финальный, прогресс становится 6 из 6):

```
🤝 Как вам удобнее быть с учёбой ребёнка?

🎯 «Хочу быть в курсе» — буду видеть расписание, домашку, учебный план и оплаты.
   Подходит, если важно держать руку на пульсе.

🌿 «Доверяю преподавателю» — кабинет покажет только расписание и оплаты,
   без домашки и плана. Учёбу контролирует ребёнок и преподаватель.

Этот выбор можно поменять в любой момент в «Ещё → Профиль».
```

Кнопки: `🎯 Хочу быть в курсе` / `🌿 Доверяю преподавателю`.

После выбора — `_finish_parent_registration()` сохраняет `engagement_mode` и завершает регистрацию.

### 2.3 UX в кабинете

**Кабинет ребёнка (`build_parent_child_hub_text`)** показывает текущий режим строкой:

- active: `🎯 Активное наблюдение`
- trust: `🌿 Доверительный режим`

**Клавиатура `make_parent_child_keyboard(link_id, linked, mode)`:**

active (как сейчас):
```
📌 Учебный план
📅 Расписание │ 📚 Домашка
💰 Оплаты
✉️ Написать преподавателю
◀️ К детям
```

trust:
```
📅 Расписание │ 💰 Оплаты
✉️ Написать преподавателю
◀️ К детям
```

**Защита на уровне callback:** обработчики `parent:child:*:study_plan*` и `parent:child:*:homework*` дополнительно проверяют `engagement_mode == 'active'`. Если `trust` — отвечают alert «Вы выбрали доверительный режим. Сменить можно в Ещё → Профиль.».

### 2.4 Профиль и переключение

`parent_profile_keyboard` получает кнопку режима:

```
👨‍👩‍👧 Открыть детей
🎯 Режим: активное наблюдение           ← или 🌿 Режим: доверие
✉️ Написать преподавателю
🛡 Опасные действия
◀️ Главное меню
```

Callback `parent:engagement:toggle`:
- читает текущий режим;
- меняет на противоположный;
- перерисовывает экран профиля с алертом «Режим обновлён».

---

## 3. Восемь дефектов — описание и фиксы

### 3.1 [CRIT] Самоудаление родителя

**Симптом.** `process_self_delete_confirm` (`callbacks.py:1087`) для роли `parent` вызывает `db.delete_user_fully()` — функция, которая удаляет `homework`, `lessons`, `payments`, `calendar_student_links` по `student_id = telegram_id`. Для родителя это ничего не находит (его telegram_id ≠ student_id), но логика противоречит контракту (для парента есть `delete_parent_preserving_history`, который сохраняет историю оплат через `payments.payer_id := NULL`).

**Фикс.** Ветвление по роли. Для `parent` → `delete_parent_preserving_history`. Для `student` → `delete_user_fully`.

### 3.2 [HIGH] Студенческие callback'и доступны родителю

**Симптом.** `process_menu_choice` (`callbacks.py:387`) обрабатывает `schedule | freeze | payment` без проверки роли. Аналогично `homework`, `hw:active|done|view|file`, `hw_done`, `study_plan*`, `notif:*`, `level_test:*`, `freeze:*`, `freeze_confirm:*`. Для родителя они вернут пустые/нулевые данные или попытаются что-то списать с его telegram_id как со student_id.

**Фикс.** Каждый из этих обработчиков либо явно отбрасывает родителя alert'ом «Этот раздел доступен только ученикам», либо (для `notif:*`) разрешён всем зарегистрированным.

### 3.3 [HIGH] Materials для родителя пуст

**Симптом.** `process_materials` для роли `parent` зовёт `list_student_resources(parent_telegram_id)` — у родителя нет своих ресурсов, возвращается пустой список.

**Фикс.** Для родителя возвращаем глобальные ресурсы (`list_global_resources()`). Если в будущем потребуется агрегировать ресурсы детей — расширим, но сейчас это приведёт к дубликатам/путанице (у родителя ≥2 детей).

### 3.4 [MED] homework:file без preview-mode

**Симптом.** `process_parent_child_homework_file` (`callbacks.py:544`) использует `callback_query.from_user.id` напрямую, без `_resolve_actor_context`. В admin preview синтетический родитель сюда не попадёт.

**Фикс.** Привести к общему паттерну: `parent_id, user, preview = await _resolve_actor_context(...)`, вызов `_get_parent_child_link(... preview)`. Сам `send_document` остаётся реальному `from_user.id` (preview блокируется через `_block_preview_action`, потому что отправка файла — побочный эффект; admin не должен случайно дёрнуть).

### 3.5 [MED] reply:payment без контекста ребёнка

**Симптом.** Кнопка «✉️ Сообщить об оплате» на экране оплат конкретного ребёнка ведёт на общий `reply:payment`. Если у родителя ≥2 детей, преподаватель из контекста сообщения не поймёт, за кого платят.

**Фикс.** Кнопка отправляет `reply:payment:child:<link_id>`. В `start_student_reply` парсим расширенный формат, в контекст-лейбл подставляем имя ребёнка («по оплате за <имя>»). Старый `reply:payment` остаётся валидным (без контекста ребёнка).

### 3.6 [MED] Self-delete снапшот для родителя нерелевантен

**Симптом.** `process_profile_delete_me` (`callbacks.py:1033`) зовёт `get_user_deletion_snapshot`, у которого `homework/lessons/payments_as_student` — это поля по `student_id = telegram_id`. Для родителя они всегда 0 и не несут смысла, но запрос всё равно выполняется. При этом существует профильная функция `get_parent_deletion_snapshot`, которая считает `children_count`, `linked_children_count`, `payments_as_payer`.

**Фикс.** Для роли `parent` использовать `get_parent_deletion_snapshot`; адаптировать `build_self_delete_warning_text`, чтобы читать новые поля (текущая ветка для parent уже читает `parent_links_as_parent` и `payments_as_payer`, но названия не совпадают — приведём к единым ключам).

### 3.7 [LOW] Управление уведомлениями для родителя

**Симптом.** `parent_more_keyboard` не содержит «🔔 Управление уведомлениями». Хотя поле `lesson_reminders` универсально, родитель не может им управлять. С учётом будущих parent-нацеленных нотификаций (Pulse touches, напоминания об оплате) — это важная точка контроля.

**Фикс.** Добавить кнопку `[🔔 Управление уведомлениями] → notif:manage` в `parent_more_keyboard`. Сам `notif:manage` уже работает для любых ролей.

### 3.8 [LOW] Пост-регистрационная клавиатура

**Симптом.** После `_finish_parent_registration` показывается статический `parent_main_keyboard` без кнопки только что созданного ребёнка. Резкий разрыв: «Связь с учеником найдена» — а кнопки ребёнка нет, надо нажать «Мои дети».

**Фикс.** Сразу после insert'а собрать `make_parent_home_keyboard(children)` и показать кабинет с детьми. Текст сообщения использует `build_parent_home_text` + короткий header «✅ Регистрация завершена».

---

## 4. Затрагиваемые файлы

| Файл | Что меняется |
|---|---|
| `utils/db_api/schema.py` | новая миграция `migrate_users_add_engagement_mode` + регистрация в `init_database` |
| `utils/db_api/users.py` | методы `set_parent_engagement_mode`, `get_parent_engagement_mode`; in-INSERT `engagement_mode` в `_finish_parent_registration` (через сам обработчик); поправить `get_parent_deletion_snapshot` (если надо) |
| `states/registration.py` | `Registration.waiting_for_engagement_mode` |
| `keyboards/inline.py` | `parent_engagement_keyboard`, обновлённые `parent_more_keyboard`, `parent_profile_keyboard`, `make_parent_child_keyboard(mode)`, `make_parent_payments_keyboard(link_id)` (передача link_id в reply:payment) |
| `handlers/users/start.py` | новый шаг регистрации; пост-регистрационная клавиатура с детьми; `_finish_parent_registration` сохраняет mode |
| `handlers/users/callbacks.py` | блок-проверки роли, починка homework:file, parent self-delete, materials, reply:payment, mode toggle, child hub чтит engagement_mode |
| `handlers/users/screens.py` | передаёт `engagement_mode` в keyboard builder |
| `utils/ui_text.py` | `build_engagement_mode_intro_text`, обновлённый `build_self_delete_warning_text` parent-ветка, `build_parent_child_hub_text` показывает mode |
| `tests/test_parent_ecosystem.py` | новые тесты на mode + регрессии для всех 8 фиксов |

---

## 5. Тест-план

1. **Engagement mode registration** — родитель проходит регистрацию, выбирает active → запись в БД `engagement_mode='active'`; меню ребёнка содержит «Учебный план», «Домашка».
2. **Engagement mode trust** — родитель выбирает trust → меню ребёнка содержит только «Расписание», «Оплаты», «Написать»; прямой callback на `:study_plan` отвечает alert'ом.
3. **Engagement mode toggle** — кнопка в профиле меняет режим, перерисовка работает.
4. **Self-delete parent** — `delete_parent_preserving_history` вызывается; payments parent'а получают `payer_id = NULL`; ученик не удалён.
5. **Block student callbacks for parent** — для роли parent callback `schedule` / `freeze` / `homework` / `study_plan` отвечают alert'ом, текст сообщения не меняется.
6. **Materials for parent** — возвращаются глобальные ресурсы.
7. **homework:file preview** — admin в preview-mode видит alert (preview-блок), реальный родитель получает файл.
8. **reply:payment with child** — кнопка «Сообщить об оплате» в карточке ребёнка приводит на FSM с лейблом «по оплате за <имя>».
9. **parent_more notifications** — в меню «Ещё» родителя есть кнопка «🔔 Управление уведомлениями».
10. **Post-registration keyboard** — после регистрации виден экран «Кабинет родителя» с кнопкой ребёнка.

Все тесты — в `tests/test_parent_ecosystem.py`.

---

## 6. Риски и компромиссы

- **Один режим на родителя, не на ребёнка.** Если у родителя несколько детей с разной динамикой («старший сам, младшую веду»), режим один на всех. Согласовано: в первой итерации лучше единый, проще объяснить и не размыть UX. Расширение до per-link — отдельная итерация, миграция тривиальна (column на `student_parent`).
- **Trust не блокирует уведомления.** Если в будущем Pulse начнёт слать родителю «у ребёнка просрочка» — это противоречит trust-режиму. На этот случай предусмотрено отдельное `lesson_reminders` (issue 3.7) и pulse-туч-флаг — будут слушать `engagement_mode == 'active'` при выборке кому слать.
- **Старые родители получают `'active'` по умолчанию.** Это совместимо с их текущим опытом (никто не теряет видимости). Активный таскбан — добровольный.
