from aiogram import html, types

from data import config
from data.config import load_teacher_info
from keyboards.inline import make_back_button_keyboard
from utils.brand import choose_tone_variant
from utils.speech import choose_form


def is_admin(user_id: int) -> bool:
    return bool(config.ADMIN_ID) and user_id == config.ADMIN_ID


def q(value) -> str:
    return html.quote(str(value)) if value is not None else "—"


def message_to_html(message: types.Message) -> str:
    text = (message.text or "").strip()
    if not text:
        return ""
    if message.entities:
        formatted = (message.html_text or "").strip()
        if formatted:
            return formatted
    return html.quote(text)


def message_or_caption_to_html(message: types.Message) -> str:
    raw = (message.text or message.caption or "").strip()
    if not raw:
        return ""
    if message.entities or getattr(message, "caption_entities", None):
        formatted = (getattr(message, "html_text", "") or "").strip()
        if formatted:
            return formatted
    return html.quote(raw)


def extract_homework_payload(message: types.Message) -> dict | None:
    description = message_or_caption_to_html(message)
    attachment = None
    if message.document:
        attachment = {
            "file_id": message.document.file_id,
            "file_unique_id": message.document.file_unique_id,
            "file_name": message.document.file_name,
            "mime_type": message.document.mime_type,
        }

    if not description and not attachment:
        return None

    return {
        "description": description,
        "attachment": attachment,
    }


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


def parse_admin_student_picker_callback_data(callback_data: str) -> tuple[str, int, int]:
    parts = callback_data.split(":")
    if len(parts) != 5 or parts[0] != "admin" or parts[1] != "student_pick_select":
        raise ValueError(f"Unsupported admin student picker callback: {callback_data}")
    flow = parts[2]
    student_id = int(parts[3])
    page = int(parts[4])
    return flow, student_id, page


def extract_broadcast_payload(message: types.Message) -> dict | None:
    preview_text = message_or_caption_to_html(message)
    origin_chat_id, origin_message_id = get_message_origin(message, message.from_user.id)

    text = (message.text or "").strip()
    if text:
        return {
            "mode": "text",
            "text": preview_text,
            "preview": preview_text,
        }

    media_labels = [
        ("animation", "🎞 <b>GIF-анимация</b>"),
        ("sticker", "🧩 <b>Стикер</b>"),
        ("photo", "🖼 <b>Фото</b>"),
        ("video", "🎬 <b>Видео</b>"),
        ("document", "📎 <b>Документ</b>"),
        ("voice", "🎤 <b>Голосовое сообщение</b>"),
    ]
    for attr, label in media_labels:
        if getattr(message, attr, None):
            preview = label
            if preview_text:
                preview += f"\n\n{preview_text}"
            return {
                "mode": "copy",
                "preview": preview,
                "source_chat_id": origin_chat_id,
                "source_message_id": origin_message_id,
            }

    return None


def get_level_test_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("level_test_url", "") or info.get("level_test_url", "")


def build_level_test_broadcast_text(speech_style: str | None = None) -> str:
    url = get_level_test_url()
    intro = choose_tone_variant(
        "Я подготовил короткий тест, который поможет точнее определить",
        "Я подготовил короткий тест, который поможет точнее определить",
        "Я подготовил короткий тест, который поможет точнее определить",
        "Я подготовил небольшой тест, который поможет точнее определить",
    )
    second_line = choose_tone_variant(
        "Так будет проще подобрать подходящую программу занятий и темп.",
        "Так будет проще подобрать подходящую программу занятий и темп.",
        "Так будет проще подобрать подходящую программу занятий и темп.",
        "Так будет легче подобрать подходящий формат занятий и темп.",
    )
    if url:
        safe_url = html.quote(url)
        return (
            "🧪 <b>Тест уровня языка</b>\n\n"
            f"{intro} {choose_form(speech_style, 'ваш', 'твой')} текущий уровень.\n"
            f"{second_line}\n\n"
            f"👉 <a href=\"{safe_url}\">Пройти тест</a>"
        )
    return (
        "🧪 <b>Тест уровня языка</b>\n\n"
        f"Я подготовил короткий тест для определения {choose_form(speech_style, 'вашего', 'твоего')} текущего уровня.\n"
        "Ссылка будет отправлена чуть позже."
    )


class MessageEditor:
    def __init__(self, bot, chat_id: int, message_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id

    async def edit_text(self, text: str, reply_markup=None):
        await self.bot.edit_message_text(
            text=text,
            chat_id=self.chat_id,
            message_id=self.message_id,
            reply_markup=reply_markup,
        )


def get_message_origin(message: types.Message, fallback_chat_id: int | None = None) -> tuple[int | None, int | None]:
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) or fallback_chat_id
    message_id = getattr(message, "message_id", None)
    return chat_id, message_id


ADMIN_STUDENT_PICKER_PAGE_SIZE = 5


def admin_picker_back_view(flow: str) -> str:
    if flow == "calendar_aliases":
        return "admin:cat:service"
    if flow in {"preview_student", "preview_parent"}:
        return "admin:preview"
    return "admin:cat:education"


async def render_admin_student_picker(message: types.Message, db, flow: str, page: int = 0):
    from keyboards.inline import make_admin_student_picker_keyboard
    from utils.ui_text import build_admin_student_picker_text

    students = await db.get_students_overview()
    if not students:
        await message.edit_text(
            "⚠️ Нет зарегистрированных учеников.",
            reply_markup=make_back_button_keyboard("◀️ Назад", admin_picker_back_view(flow)),
        )
        return

    await message.edit_text(
        build_admin_student_picker_text(students, page, ADMIN_STUDENT_PICKER_PAGE_SIZE, flow),
        reply_markup=make_admin_student_picker_keyboard(students, flow, page, ADMIN_STUDENT_PICKER_PAGE_SIZE),
    )


async def restore_admin_view(bot, db, chat_id: int | None, message_id: int | None, view: str | None):
    if not view or chat_id is None or message_id is None:
        return False

    target = MessageEditor(bot, chat_id, message_id)

    if view in {"admin:home", "back_to_admin"}:
        from handlers.users.admin import render_admin_home

        await render_admin_home(target, db)
        return True

    if view == "admin:finance":
        from handlers.users.admin_sections.finance import render_admin_finance

        await render_admin_finance(target, db)
        return True

    if view.startswith("admin:cat:"):
        from handlers.users.admin import render_admin_category

        category = view.split(":", 2)[2]
        await render_admin_category(target, category)
        return True

    if view.startswith("admin:student_card:"):
        from handlers.users.admin_sections.students import _render_admin_student_card

        _, _, student_id_str, page_str = view.split(":")
        await _render_admin_student_card(target, db, int(student_id_str), int(page_str))
        return True

    if view.startswith("admin:student_actions:"):
        from handlers.users.admin_sections.students import _render_admin_student_actions

        _, _, student_id_str, page_str = view.split(":")
        await _render_admin_student_actions(target, db, int(student_id_str), int(page_str))
        return True

    if view.startswith("admin:student_settings:"):
        from handlers.users.admin_sections.students import _render_admin_student_settings

        _, _, student_id_str, page_str = view.split(":")
        await _render_admin_student_settings(target, db, int(student_id_str), int(page_str))
        return True

    if view.startswith("admin:student_danger:"):
        from handlers.users.admin_sections.students import _render_admin_student_danger

        _, _, student_id_str, page_str = view.split(":")
        await _render_admin_student_danger(target, db, int(student_id_str), int(page_str))
        return True

    if view.startswith("admin:students:page:"):
        from handlers.users.admin_sections.students import _render_admin_students_page

        page = int(view.split(":")[3])
        await _render_admin_students_page(target, db, page=page)
        return True

    if view == "admin:parents":
        from handlers.users.admin_sections.parents import _render_admin_parents_page

        await _render_admin_parents_page(target, db, page=0)
        return True

    if view.startswith("admin:parents:page:"):
        from handlers.users.admin_sections.parents import _render_admin_parents_page

        page = int(view.split(":")[3])
        await _render_admin_parents_page(target, db, page=page)
        return True

    if view.startswith("admin:parent_card:"):
        from handlers.users.admin_sections.parents import _render_admin_parent_card

        _, _, parent_id_str, page_str = view.split(":")
        await _render_admin_parent_card(target, db, int(parent_id_str), int(page_str))
        return True

    if view.startswith("admin:parent_danger:"):
        from handlers.users.admin_sections.parents import _render_admin_parent_danger

        _, _, parent_id_str, page_str = view.split(":")
        await _render_admin_parent_danger(target, db, int(parent_id_str), int(page_str))
        return True

    if view.startswith("admin:student_pick:"):
        parts = view.split(":")
        flow = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        await render_admin_student_picker(target, db, flow=flow, page=page)
        return True

    if view.startswith("admin:student_payments:"):
        from handlers.users.admin_sections.payments import _render_admin_payments

        parts = view.split(":")
        student_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else None
        source = parts[4] if len(parts) > 4 else "card"
        await _render_admin_payments(target, db, student_id, page=page, source=source)
        return True

    if view == "admin:all_homework":
        from handlers.users.admin_sections.homework import _render_admin_homework_list

        await _render_admin_homework_list(target, db)
        return True

    if view in {"admin:service:monitoring", "admin:service:context", "admin:cat:service"}:
        from handlers.users.admin import render_admin_service_monitoring

        await render_admin_service_monitoring(target)
        return True

    return False
