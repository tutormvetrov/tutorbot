import json
import logging
from pathlib import Path

from aiogram import html
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from data import config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREVIEW_STATE_FILE = PROJECT_ROOT / "data" / "admin_preview.json"

PREVIEW_BLOCKED_ALERT = "🧪 В режиме preview изменения отключены. Можно смотреть экраны, но не сохранять действия."

ROLE_LABELS = {
    "student": "ученик",
    "parent": "родитель",
    "teacher_admin": "администратор",
}


def _load_preview_payload() -> dict:
    if not PREVIEW_STATE_FILE.exists():
        return {}
    try:
        return json.loads(PREVIEW_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Не удалось прочитать preview state: %s", exc)
        return {}


def _save_preview_payload(payload: dict):
    try:
        PREVIEW_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREVIEW_STATE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Не удалось сохранить preview state: %s", exc)


def get_admin_preview_session(admin_id: int) -> dict | None:
    return (_load_preview_payload().get(str(admin_id)) or None)


def set_admin_preview_session(
    admin_id: int,
    target_id: int,
    role: str,
    full_name: str,
    *,
    synthetic_parent_student_id: int | None = None,
):
    payload = _load_preview_payload()
    session = {
        "target_id": int(target_id),
        "role": role,
        "full_name": full_name or str(target_id),
    }
    if synthetic_parent_student_id:
        session["synthetic_parent_student_id"] = int(synthetic_parent_student_id)
    payload[str(admin_id)] = session
    _save_preview_payload(payload)


def clear_admin_preview_session(admin_id: int):
    payload = _load_preview_payload()
    if str(admin_id) in payload:
        payload.pop(str(admin_id), None)
        _save_preview_payload(payload)


def preview_role_label(role: str | None) -> str:
    return ROLE_LABELS.get((role or "").strip().lower(), "пользователь")


async def get_preview_context(db, actor_id: int) -> dict | None:
    if actor_id != config.ADMIN_ID:
        return None

    session = get_admin_preview_session(actor_id)
    if not session:
        return None

    role = (session.get("role") or "").strip().lower()
    synthetic_parent_student_id = int(session.get("synthetic_parent_student_id") or 0)
    if role == "parent" and synthetic_parent_student_id:
        student = await db.get_user(synthetic_parent_student_id)
        if (
            not student
            or not student.get("is_active", True)
            or student.get("role") != "student"
        ):
            clear_admin_preview_session(actor_id)
            return None

        student_name = student.get("full_name") or str(synthetic_parent_student_id)
        full_name = session.get("full_name") or f"Родитель ученика {student_name}"
        return {
            "admin_id": actor_id,
            "target_id": actor_id,
            "role": "parent",
            "full_name": full_name,
            "user": {
                "telegram_id": actor_id,
                "full_name": full_name,
                "role": "parent",
                "is_active": True,
                "registration_date": student.get("registration_date"),
            },
            "synthetic_parent_student_id": synthetic_parent_student_id,
            "synthetic_parent_student_name": student_name,
        }

    target_id = int(session.get("target_id") or 0)
    if not target_id:
        clear_admin_preview_session(actor_id)
        return None

    user = await db.get_user(target_id)
    if not user or not user.get("is_active", True):
        clear_admin_preview_session(actor_id)
        return None

    if role and user.get("role") != role:
        clear_admin_preview_session(actor_id)
        return None

    return {
        "admin_id": actor_id,
        "target_id": user["telegram_id"],
        "role": user.get("role"),
        "full_name": user.get("full_name") or session.get("full_name") or str(user["telegram_id"]),
        "user": user,
    }


async def resolve_effective_user_id(db, actor_id: int) -> int:
    preview = await get_preview_context(db, actor_id)
    return preview["target_id"] if preview else actor_id


def is_synthetic_parent_preview(preview: dict | None) -> bool:
    return bool(
        preview
        and preview.get("role") == "parent"
        and int(preview.get("synthetic_parent_student_id") or 0)
    )


def _synthetic_parent_student_id(preview: dict | None) -> int:
    return int(preview.get("synthetic_parent_student_id") or 0) if preview else 0


async def get_preview_parent_child_link(db, preview: dict | None, link_id: int) -> dict | None:
    student_id = _synthetic_parent_student_id(preview)
    if not student_id or int(link_id) != student_id:
        return None

    student = await db.get_user(student_id)
    if (
        not student
        or not student.get("is_active", True)
        or student.get("role") != "student"
    ):
        return None

    lessons = list(await db.get_active_lessons(student_id) or [])
    active_homework = list(await db.get_student_homework(student_id, "active") or [])
    balance = await db.get_student_lesson_balance(student_id)
    next_lesson = next((lesson.get("lesson_date") for lesson in lessons if lesson.get("lesson_date")), None)

    return {
        "link_id": student_id,
        "student_id": student_id,
        "child_label": student.get("full_name") or str(student_id),
        "link_status": "linked",
        "lesson_format": student.get("lesson_format"),
        "next_lesson_date": next_lesson,
        "active_homework_count": len(active_homework),
        "lesson_balance": balance,
    }


async def get_preview_parent_children_overview(db, preview: dict | None) -> list[dict]:
    child = await get_preview_parent_child_link(
        db,
        preview,
        _synthetic_parent_student_id(preview),
    )
    return [child] if child else []


async def get_preview_parent_child_schedule(db, preview: dict | None, link_id: int) -> list[dict]:
    child = await get_preview_parent_child_link(db, preview, link_id)
    if not child:
        return []
    return list(await db.get_active_lessons(child["student_id"]) or [])


async def get_preview_parent_child_homework(
    db,
    preview: dict | None,
    link_id: int,
    status: str = "active",
) -> list[dict]:
    child = await get_preview_parent_child_link(db, preview, link_id)
    if not child:
        return []
    return list(await db.get_student_homework(child["student_id"], status) or [])


async def get_preview_parent_child_payments(
    db,
    preview: dict | None,
    link_id: int,
    limit: int = 5,
) -> list[dict]:
    child = await get_preview_parent_child_link(db, preview, link_id)
    if not child:
        return []
    return list(await db.get_student_payments(child["student_id"], limit=limit) or [])


def build_preview_banner(preview: dict) -> str:
    role_label = preview_role_label(preview.get("role"))
    full_name = html.quote(preview.get("full_name") or str(preview.get("target_id") or "—"))
    lines = [
        "🧪 <b>Режим preview</b>\n"
        f"Сейчас открыт контур роли <b>{role_label}</b>: <b>{full_name}</b>"
    ]
    synthetic_student_name = preview.get("synthetic_parent_student_name")
    if synthetic_student_name:
        lines.append(
            f"Основа просмотра: данные ученика <b>{html.quote(str(synthetic_student_name))}</b>."
        )
    lines.append("Изменения отключены: можно смотреть, но нельзя сохранять действия.")
    return "\n".join(lines)


def apply_preview_to_payload(text: str, reply_markup, preview: dict | None):
    if not preview:
        return text, reply_markup

    rows = [list(row) for row in getattr(reply_markup, "inline_keyboard", [])]
    rows.append([
        InlineKeyboardButton(text="⚙️ К админ-панели", callback_data="admin:home"),
        InlineKeyboardButton(text="🛑 Выйти из preview", callback_data="admin:preview:stop"),
    ])

    decorated_text = f"{build_preview_banner(preview)}\n\n{text}" if text else build_preview_banner(preview)
    return decorated_text, InlineKeyboardMarkup(inline_keyboard=rows)
