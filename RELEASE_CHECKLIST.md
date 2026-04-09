# Release Checklist

## Before Release

- [ ] Рабочая ветка чистая, без неожиданных изменений.
- [ ] `.env` заполнен и проходит `make validate-env`.
- [ ] Сделан backup базы: `make backup`.
- [ ] При необходимости сохранены runtime-файлы:
  - `data/ops_status.json`
  - `data/runtime_metrics.jsonl`
  - `data/fsm_storage.json`
  - `data/calendar_sync_report.json`
- [ ] Пройден quality gate: `make check`.

## Deploy

- [ ] Обновлён код на сервере.
- [ ] Обновлены зависимости, если они менялись.
- [ ] Актуальны `deploy/tutorbot.service` и `deploy/logrotate/tutorbot`.
- [ ] Выполнено:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tutorbot
```

- [ ] Проверено, что сервис поднялся без `ExecStartPre`-ошибок.

## Smoke Check

- [ ] Выполнен `make smoke`.
- [ ] Ручная проверка:
  - [ ] `/start`
  - [ ] `/admin`
  - [ ] `/sync`
  - [ ] список учеников
  - [ ] карточка ученика
  - [ ] выдача короткого ДЗ
- [ ] Проверены `data/ops_status.json` и `data/runtime_metrics.jsonl`.

## Rollback

- [ ] Остановить или перезапустить сервис в безопасное состояние.
- [ ] Вернуть предыдущую версию кода.
- [ ] Если релиз затронул данные — восстановить базу:

```bash
TUTORBOT_ALLOW_RESTORE=1 ./scripts/db_restore.sh /path/to/backup.sql.gz
```

- [ ] Перед restore бот остановлен, либо для осознанного live-restore явно указан `TUTORBOT_ALLOW_LIVE_RESTORE=1`.

- [ ] Повторить `make smoke`.

## Notes

- Release считается завершённым только после успешного smoke check.
- Если smoke check не проходит, релиз не закрыт и должен быть либо исправлен, либо откатан.
