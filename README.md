# TutorBot

Telegram-бот для управления учебным процессом: регистрация учеников и родителей, расписание, домашние задания, оплаты, напоминания и админ-панель.

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
.venv/bin/python scripts/validate_env.py
.venv/bin/python app.py
```

## Конфиг

- `BOT_TOKEN` — токен Telegram-бота.
- `ADMIN_ID` — Telegram ID администратора.
- `PGUSER`, `PGPASSWORD`, `DATABASE`, `PGHOST`, `PGPORT` — параметры PostgreSQL.
- `GOOGLE_CALENDAR_ID`, `GOOGLE_CREDENTIALS_FILE` — опциональная пара для Google Calendar sync.
- `TUTORBOT_TIMEZONE` — бизнесовая timezone бота. По умолчанию `Europe/Moscow`; scheduler, БД и sync теперь должны жить в одном часовом поясе.
- `TUTORBOT_ROOT` — корень проекта для shell-скриптов и watcher.
- `TUTORBOT_SERVICE_NAME` — имя `systemd`-сервиса.
- `TUTORBOT_SYSTEMD_SCOPE` — `system` или `user`.
- `TUTORBOT_BACKUP_DIR` — каталог для резервных копий PostgreSQL.

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

`make check` — это единый quality gate: env validation, lint, mypy, pytest и compileall.

## Quality Gate

Перед релизом проект должен пройти:

```bash
make check
```

CI дублирует тот же набор через `.github/workflows/ci.yml`.

## Структура проекта

- `app.py` — точка входа и запуск планировщика.
- `handlers/` — обработчики сообщений и callback.
- `keyboards/` — inline-клавиатуры.
- `utils/` — БД, календарь, тексты, observability, scheduler.
- `scripts/` — healthcheck, watcher, env validation, backup/restore, smoke check.
- `data/` — конфигурация и runtime-артефакты.
- `deploy/` — `systemd` и `logrotate`.
- `tests/` — unit и flow-тесты.

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
5. выдачу короткого ДЗ.

## Health / Runtime

Текущее состояние бота отражается в:

- `data/ops_status.json`
- `data/runtime_metrics.jsonl`

`scripts/healthcheck.sh` проверяет:

- активный сервис или процесс бота;
- валидность env-конфига;
- наличие и свежесть `ops_status.json`;
- непустой `runtime_metrics.jsonl`, если файл уже существует.

## Release / Rollback

Полный чеклист лежит в [RELEASE_CHECKLIST.md](/srv/tutorbot/RELEASE_CHECKLIST.md).

Короткий порядок:

1. `make backup`
2. `make check`
3. deploy
4. `make smoke`
5. если релиз не прошёл — rollback к предыдущему коду и при необходимости `db_restore.sh`
