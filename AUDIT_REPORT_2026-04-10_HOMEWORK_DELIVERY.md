# Audit: Delayed Homework Delivery

## Deployment Follow-up — 28.04.2026

- Feature remains integrated after the later `Учебный план` release.
- Runtime schema creation was checked via `Database.create_all_tables()` on the live project environment.
- Service was restarted successfully after dependency/schema updates.
- Latest quality gate: `make check` passed with 188 tests.
- Latest smoke checks: local `make smoke` and runtime `scripts/release_smoke.py --mode runtime` passed.

## Method
- Static code review
- Full automated regression run
- Handler-level clickthrough with focused tests for create, edit, send-now, scheduler flush, reply routing, admin UI and health

## Commands
- `python -m pytest -q`
- `python -m mypy`
- `python -m ruff check .`
- `python -m compileall -q handlers utils tests scripts app.py loader.py`
- `python scripts/validate_env.py --mode local`

## Checked Scenarios
| Scenario | Result | Notes |
|---|---|---|
| Create homework during allowed hours | Pass | Immediate send is preserved |
| Create homework during quiet hours | Pass | Queue row is created for `10:00`, admin sees `Отправить сейчас` |
| Edit homework during allowed hours | Pass | Immediate update send is preserved |
| Edit homework during quiet hours | Pass | Update goes into queue and appears in admin card |
| Delete queued homework | Pass | Covered by `ON DELETE CASCADE` in queue schema |
| Manual `Отправить сейчас` | Pass | Sends actual current version and clears queue |
| Morning batch flush | Pass | Multiple queued items for one student collapse into one message |
| Reply after single send | Pass | Uses `reply:homework:{id}` |
| Reply after batch send | Pass | Uses generic `reply:homework` |
| Admin active homework list | Pass | Shows queued badge |
| Admin homework manage card | Pass | Shows delivery status and `Отправить сейчас` when queued |
| Health / monitoring | Pass | New scheduler job and delivery counters are rendered |

## Integration Checks
- Homework persistence is unchanged. Homework still saves immediately in DB.
- Student and parent homework views remain read path only and do not depend on queue fields.
- Existing reminder job for due-tomorrow homework still works.
- Scheduler setup now includes a dedicated `queued_homework_delivery` job every 5 minutes.
- New callback `hw_send_now:{homework_id}` does not overlap with edit and delete callbacks.
- Batched morning delivery keeps reply-flow usable without inventing fake homework IDs.

## Issues Found During Integration
1. `next_homework_delivery_slot()` compared timezone-aware `business_now()` with naive `10:00`.
   Fix: slot is now built via `current.replace(...)`, preserving timezone context.
2. Old tests and fake DB stubs assumed the pre-queue contract.
   Fix: test doubles were upgraded with queue methods and deterministic daytime patches.
3. Health screen still contained leftover service wording and had no queue metrics.
   Fix: screen was rewritten cleanly and extended with queued delivery counters.

## Residual Unknowns
- Real Telegram client behavior for live night-to-morning notification timing was not checked in this local run.
- First live boot with the new schema has now been observed through the 28.04.2026 deployment flow.
- Real scheduler observation of the next `10:00` batch is still useful as an operational follow-up.

## Verdict
- Feature is integrated cleanly with homework-flow, reply-flow, scheduler, admin UI and health.
- Automated and handler-level coverage is sufficient for deploy readiness.
- Remaining uncertainty is only in live Telegram UX and live scheduler execution after deploy.
