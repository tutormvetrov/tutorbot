# TutorBot

Telegram-бот для управления учебным процессом: регистрация учеников, родителей и учебных пар, расписание, домашние задания, учебные планы, оплаты, напоминания, рассылки и админ-панель.

## Основные возможности

- Кабинет ученика: `📌 Учебный план`, домашние задания, расписание, оплаты, заморозка, профиль, контакты и реквизиты.
- Учебный план: админ загружает PDF для ученика или пары, бот парсит текст и таблицы через PyMuPDF, показывает preview, просит ручную выжимку при слабом парсинге и публикует план только после подтверждения.
- Чек-лист подготовки: авто-пункты к ближайшему уроку, ручные пункты преподавателя, отметки выполнения и прогресс.
- Учебные пары: саморегистрация пары, создание пары из админки, deep-link для второго участника, общий баланс, темп, ДЗ и учебный план через основной профиль. Названия пар строятся семантически: общая фамилия, разные фамилии или ручное название.
- Домашние задания: вложения, отложенная доставка в тихие часы, кнопка `Отправить сейчас`, утренняя пакетная доставка, reply-flow по ДЗ и черновик нового ДЗ по статистике частых материалов ученика.
- Родительский кабинет: дети, расписание, ДЗ, оплаты, реквизиты и учебный план ребёнка.
- Оплаты: учёт баланса, история оплат, глобальная тарифная сетка по размеру группы и длительности занятия, защита воскресного автообнуления от уже внесённых оплат и отдельная финансовая панель администратора.
- Регистрация: пошаговый сценарий с короткими вопросами, прогрессом, компактной строкой уже собранных данных и отдельным финальным экраном контактов.
- Админ-панель: ученики, пары, родители, финансы, учебный процесс, рассылки, preview ролей, мониторинг, рабочие заметки и операционные экраны.
- Рассылки: текст, форматирование, ссылки и медиа через предпросмотр, сегментный выбор получателей и восстановление черновика при потере FSM-состояния.
- Scheduler: напоминания об уроках, follow-up после урока, pre-lesson bookmark, отложенная доставка ДЗ, воскресный обзор учебного плана, sync/monitoring jobs.

## Быстрый старт

1. Создайте `.env` по образцу `.env.example`.
2. Заполните обязательные переменные: `BOT_TOKEN`, `ADMIN_ID`, `PGUSER`, `PGPASSWORD`, `DATABASE`, `PGHOST`, `PGPORT`.
3. Если нужен Google Calendar sync, заполните обе переменные `GOOGLE_CALENDAR_ID` и `GOOGLE_CREDENTIALS_FILE`.
4. Установите runtime-зависимости:

```bash
.venv/bin/pip install -r requirements.txt
```

5. Проверьте конфиг и запустите бота:

```bash
.venv/bin/python scripts/validate_env.py --mode local
.venv/bin/python app.py
```

## Конфиг

- `BOT_TOKEN` - токен Telegram-бота.
- `ADMIN_ID` - Telegram ID администратора.
- `PGUSER`, `PGPASSWORD`, `DATABASE`, `PGHOST`, `PGPORT` - параметры PostgreSQL.
- `GOOGLE_CALENDAR_ID`, `GOOGLE_CREDENTIALS_FILE` - опциональная пара для Google Calendar sync.
- `TUTORBOT_TIMEZONE` - бизнесовая timezone бота. По умолчанию `Europe/Moscow`; scheduler, БД и sync теперь должны жить в одном часовом поясе.
- `TUTORBOT_ROOT` - корень проекта для shell-скриптов и watcher.
- `TUTORBOT_SERVICE_NAME` - имя `systemd`-сервиса.
- `TUTORBOT_SYSTEMD_SCOPE` - `system` или `user`.
- `TUTORBOT_BACKUP_DIR` - каталог для резервных копий PostgreSQL.
- `RATE_LIMIT_USER_SECONDS` - минимальный интервал между действиями обычного пользователя. По умолчанию `0.7`.
- `RATE_LIMIT_ADMIN_SECONDS` - минимальный интервал между действиями администратора. По умолчанию `0.25`.
- `RATE_LIMIT_CALLBACK_SECONDS` - мягкий лимит повторных callback-нажатий. По умолчанию `0.5`.

Бизнесовые тексты, ссылки и платёжные реквизиты живут в `data/teacher_info.json`.
Актуальные поля, которые используются интерфейсом:

- `contacts.vk_call`, `contacts.google_meet`, `contacts.calendar_url` - ссылки для занятий и календаря.
- `contacts.level_test_url` - ссылка на тест уровня.
- `contacts.materials_url` или `contacts.filen_url` - ссылка на учебные материалы.
- `requisites.*` - реквизиты; цена занятия для учеников теперь предпочтительно берётся из таблицы тарифов в админке.

## Development

Установка dev-зависимостей:

```bash
make install-dev
```

Основные команды:

```bash
make validate-env
make lint
make typecheck
make test
make compile
make check
```

`make check` - это единый quality gate: env validation, lint, mypy, pytest и compileall.

### Регенерация инструкций к боту

В боте есть кнопки скачивания DOCX-инструкций для четырёх ролей (взрослый ученик, школьник, родитель, преподаватель). Файлы лежат в `docs/user_guides/` и регенерируются скриптом:

```bash
python scripts/build_user_guides.py
```

После любого заметного изменения главного меню, регистрации или появления новой фичи запусти этот скрипт и закоммить обновлённые `.docx`. `python-docx` требуется только для регенерации - в рантайме бот отправляет статические файлы.

## Quality Gate

Перед релизом проект должен пройти:

```bash
make check
```

CI дублирует тот же набор через `.github/workflows/ci.yml`.

Текущий ориентир покрытия: полный `pytest` собирает 544 теста.

## Структура проекта

- `app.py` - точка входа и запуск планировщика.
- `handlers/` - обработчики сообщений и callback.
- `keyboards/` - inline-клавиатуры.
- `utils/` - БД, календарь, тексты, observability, scheduler, rate/chat-action helpers и служебные файлы устойчивости FSM.
- `utils/db_api/` - миксины доступа к БД: users, lessons, homework, payments, study plans, calendar links.
- `utils/pdf_learning_plan.py` - парсинг PDF-планов через PyMuPDF.
- `utils/homework_delivery.py` - расчёт тихих часов и слотов отложенной доставки ДЗ.
- `scripts/` - healthcheck, watcher, env validation, backup/restore, smoke check.
- `data/` - конфигурация и runtime-артефакты.
- `deploy/` - `systemd` и `logrotate`.
- `tests/` - unit и flow-тесты.

## Deploy

Файлы для продакшена:

- `deploy/tutorbot.service`
- `deploy/logrotate/tutorbot`
- `scripts/healthcheck.sh`
- `scripts/release_smoke.sh`
- `scripts/db_backup.sh`
- `scripts/db_restore.sh`

Базовый deploy:

```bash
sudo cp deploy/tutorbot.service /etc/systemd/system/tutorbot.service
sudo cp deploy/logrotate/tutorbot /etc/logrotate.d/tutorbot
sudo systemctl daemon-reload
sudo systemctl enable --now tutorbot
```

`deploy/tutorbot.service` теперь делает `ExecStartPre` через `scripts/validate_env.py`, поэтому сервис не стартует с битым конфигом.

Если менялся `requirements.txt`, перед рестартом обновите зависимости в рабочем окружении:

```bash
.venv/bin/pip install -r requirements.txt
```

## Backup / Restore

Резервная копия PostgreSQL:

```bash
make backup
```

Восстановление PostgreSQL:

```bash
TUTORBOT_ALLOW_RESTORE=1 ./scripts/db_restore.sh /path/to/backup.sql.gz
```

По умолчанию restore сначала делает свежий pre-restore backup. Если это не нужно:

```bash
TUTORBOT_ALLOW_RESTORE=1 TUTORBOT_SKIP_PRE_RESTORE_BACKUP=1 ./scripts/db_restore.sh /path/to/backup.sql.gz
```

По умолчанию restore теперь откажется работать поверх запущенного бота. Если это осознанный live-restore:

```bash
TUTORBOT_ALLOW_RESTORE=1 TUTORBOT_ALLOW_LIVE_RESTORE=1 ./scripts/db_restore.sh /path/to/backup.sql.gz
```

Новые backup-файлы создаются с `DROP`-инструкциями (`pg_dump --clean --if-exists`), а plain SQL restore перед загрузкой очищает `public` schema, чтобы rollback был предсказуемым.

## Smoke Check

После релиза:

```bash
make smoke
```

`make smoke` прогоняет:

- `scripts/validate_env.py`
- `scripts/healthcheck.sh`

И затем стоит вручную проверить:

1. `/start` у администратора.
2. `/admin`.
3. `/sync`.
4. список учеников и одну карточку.
5. выдачу короткого ДЗ и, если сейчас тихие часы, появление отложенной доставки.
6. карточку пары и deep-link второго участника.
7. админский flow учебного плана: PDF -> preview -> правка выжимки -> публикация.
8. ученическую кнопку `📌 Учебный план`: PDF, чек-лист, отметка пункта.
9. финансы: `Финансы`, добавление оплаты, история оплат и вечерняя сводка.
10. тарифы: `Учебный процесс` -> `💳 Тарифы`, затем `Реквизиты` у ученика.
11. рассылка: ввод текста, предпросмотр, выбор сегмента и отправка тестовой группе.

## Health / Runtime

Текущее состояние бота отражается в:

- `data/ops_status.json`
- `data/runtime_metrics.jsonl`

`scripts/healthcheck.sh` проверяет:

- активный сервис или процесс бота;
- валидность env-конфига;
- наличие и свежесть `ops_status.json`;
- непустой `runtime_metrics.jsonl`, если файл уже существует.

В мониторинге админки отображаются, в частности:

- `queued_homework_delivery` - очередь отложенной доставки ДЗ;
- `study_plan_weekly_digest` - воскресный обзор учебного плана;
- календарный sync, lesson reminders, teacher follow-up и pre-lesson bookmark jobs.

## Release / Rollback

Полный чеклист лежит в [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

Короткий порядок:

1. `make backup`
2. `make check`
3. deploy
4. `make smoke`
5. если релиз не прошёл - rollback к предыдущему коду и при необходимости `db_restore.sh`
