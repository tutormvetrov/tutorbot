import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_METRICS_FILE = PROJECT_ROOT / "data" / "runtime_metrics.jsonl"
OPS_STATUS_FILE = PROJECT_ROOT / "data" / "ops_status.json"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_runtime_event(event_type: str, status: str, **payload):
    record = {
        "ts": _utc_timestamp(),
        "event_type": event_type,
        "status": status,
        **payload,
    }
    try:
        RUNTIME_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
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
