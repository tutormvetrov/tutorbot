import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_METRICS_FILE = PROJECT_ROOT / "data" / "runtime_metrics.jsonl"
OPS_STATUS_FILE = PROJECT_ROOT / "data" / "ops_status.json"
TOUCHES_RUNTIME_FILE = PROJECT_ROOT / "data" / "runtime_touches.json"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


_METRICS_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_METRICS_KEEP_LINES = 5000


def _rotate_metrics_if_needed() -> None:
    """Truncate runtime_metrics.jsonl to the last _METRICS_KEEP_LINES lines when it exceeds
    _METRICS_MAX_BYTES.  Runs in-process so no external logrotate dependency is required."""
    try:
        if not RUNTIME_METRICS_FILE.exists():
            return
        if RUNTIME_METRICS_FILE.stat().st_size <= _METRICS_MAX_BYTES:
            return
        lines = RUNTIME_METRICS_FILE.read_text(encoding="utf-8").splitlines()
        kept = lines[-_METRICS_KEEP_LINES:]
        RUNTIME_METRICS_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")
        logger.info(
            "runtime_metrics.jsonl ротирован: оставлено %d строк из %d",
            len(kept),
            len(lines),
        )
    except Exception as exc:
        logger.warning("Не удалось ротировать runtime_metrics.jsonl: %s", exc)


def write_runtime_event(event_type: str, status: str, **payload):
    record = {
        "ts": _utc_timestamp(),
        "event_type": event_type,
        "status": status,
        **payload,
    }
    try:
        RUNTIME_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _rotate_metrics_if_needed()
        with RUNTIME_METRICS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Не удалось записать runtime event %s/%s: %s", event_type, status, exc)


def update_ops_status(**payload):
    record = {
        **load_ops_status(),
        **payload,
        "updated_at": _utc_timestamp(),
    }
    try:
        OPS_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        OPS_STATUS_FILE.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Не удалось обновить ops status: %s", exc)


def update_job_status(job_name: str, status: str, **payload):
    current = load_ops_status()
    jobs = dict(current.get("jobs") or {})
    jobs[job_name] = {
        "status": status,
        "updated_at": _utc_timestamp(),
        **payload,
    }
    update_ops_status(jobs=jobs)


def load_ops_status() -> dict:
    if not OPS_STATUS_FILE.exists():
        return {}
    try:
        return json.loads(OPS_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Не удалось прочитать ops status: %s", exc)
        return {}


def load_touches_runtime() -> dict:
    """Read the runtime pause state for between-lesson touches."""
    if not TOUCHES_RUNTIME_FILE.exists():
        return {"paused": False}
    try:
        return json.loads(TOUCHES_RUNTIME_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Не удалось прочитать runtime_touches.json: %s", exc)
        return {"paused": False}


def set_touches_runtime(paused: bool, by: int | None = None, reason: str | None = None) -> dict:
    record = {
        "paused": bool(paused),
        "updated_at": _utc_timestamp(),
        "updated_by": by,
        "reason": reason,
    }
    try:
        TOUCHES_RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOUCHES_RUNTIME_FILE.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Не удалось записать runtime_touches.json: %s", exc)
    return record


def load_recent_runtime_events(limit: int = 20) -> list[dict]:
    if not RUNTIME_METRICS_FILE.exists():
        return []
    try:
        lines = RUNTIME_METRICS_FILE.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        logger.warning("Не удалось прочитать runtime events: %s", exc)
        return []

    items = []
    for raw in lines[-limit:]:
        try:
            items.append(json.loads(raw))
        except Exception:
            continue
    return items
