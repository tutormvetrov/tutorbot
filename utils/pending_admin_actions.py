import json
import time
from pathlib import Path


PENDING_ADMIN_ACTIONS_FILE = Path(__file__).resolve().parents[1] / "data" / "pending_admin_actions.json"
PENDING_BROADCAST_TTL_SECONDS = 30 * 60


def _load_actions() -> dict:
    try:
        return json.loads(PENDING_ADMIN_ACTIONS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_actions(actions: dict) -> None:
    PENDING_ADMIN_ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_ADMIN_ACTIONS_FILE.write_text(
        json.dumps(actions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def mark_pending_broadcast(admin_id: int) -> None:
    actions = _load_actions()
    actions[str(admin_id)] = {
        "action": "broadcast_text",
        "created_at": time.time(),
    }
    _save_actions(actions)


async def clear_pending_broadcast(admin_id: int) -> None:
    actions = _load_actions()
    if actions.pop(str(admin_id), None) is not None:
        _save_actions(actions)


async def has_pending_broadcast(admin_id: int, ttl_seconds: int = PENDING_BROADCAST_TTL_SECONDS) -> bool:
    actions = _load_actions()
    item = actions.get(str(admin_id))
    if not item or item.get("action") != "broadcast_text":
        return False

    created_at = float(item.get("created_at") or 0)
    if time.time() - created_at > ttl_seconds:
        actions.pop(str(admin_id), None)
        _save_actions(actions)
        return False
    return True
