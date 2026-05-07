import logging
import tempfile
from pathlib import Path

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from handlers.users.admin_sections.common import get_message_origin, is_admin, q, restore_admin_view
from keyboards.inline import (
    cancel_fsm_keyboard,
    make_admin_study_plan_keyboard,
    make_admin_study_plan_preview_keyboard,
    make_back_button_keyboard,
    make_study_plan_open_keyboard,
)
from states.registration import AdminStudyPlan
from utils.db_api.postgresql import Database
from utils.pdf_learning_plan import parse_learning_plan_pdf
from utils.ui_text import (
    build_action_result_text,
    build_admin_study_plan_preview_text,
    build_admin_study_plan_text,
)

router = Router()
logger = logging.getLogger(__name__)


def _return_view(student_id: int, page: int, source: str) -> str:
    if source in {"actions", "settings", "danger"}:
        return f"admin:student_{source}:{student_id}:{page}"
    return f"admin:student_card:{student_id}:{page}"


async def _render_admin_study_plan(
    message: types.Message,
    db: Database,
    student_id: int,
    page: int,
    source: str = "card",
):
    student = await db.get_user(student_id)
    if not student or student.get("role") != "student":
        await message.edit_text(
            "⚠️ Ученик не найден.",
            reply_markup=make_back_button_keyboard("◀️ К ученикам", "admin:students"),
        )
        return
    active_plan = await db.get_active_learning_plan(student_id)
    history = list(await db.get_learning_plan_history(student_id, limit=5) or [])
    await message.edit_text(
        build_admin_study_plan_text(student["full_name"], active_plan, history),
        reply_markup=make_admin_study_plan_keyboard(student_id, page, source, has_plan=bool(active_plan)),
    )


async def _ask_for_pdf(message: types.Message, student_name: str):
    await message.edit_text(
        "\n".join([
            "📄 <b>Загрузить учебный план</b>",
            "",
            f"Ученик: <b>{q(student_name)}</b>",
            "",
            "Отправьте PDF-файл с трёхмесячным планом. Бот распарсит текст и таблицы, а затем покажет preview перед публикацией.",
        ]),
        reply_markup=cancel_fsm_keyboard,
    )


async def _send_preview(message: types.Message, state: FSMContext):
    data = await state.get_data()
    parsed = data["parsed_pdf"]
    summary = data.get("plan_summary") or ""
    can_publish = len(summary.strip()) >= 20 and (
        parsed.get("status") == "ok" or data.get("plan_summary_manual")
    )
    await message.answer(
        build_admin_study_plan_preview_text(parsed, summary),
        reply_markup=make_admin_study_plan_preview_keyboard(can_publish=can_publish),
    )


@router.callback_query(lambda c: c.data.startswith("admin:study_plan:"))
async def admin_study_plan(callback_query: types.CallbackQuery, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, source = callback_query.data.split(":")
    await _render_admin_study_plan(
        callback_query.message,
        db,
        int(student_id_str),
        int(page_str),
        source,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith("admin:study_plan_upload:"))
async def admin_study_plan_upload_start(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    db: Database,
):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, source = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    if not student or student.get("role") != "student":
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        student_id=student_id,
        student_name=student["full_name"],
        admin_student_card_page=page,
        admin_student_card_source=source,
        admin_return_view=_return_view(student_id, page, source),
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )
    await state.set_state(AdminStudyPlan.waiting_for_pdf)
    await _ask_for_pdf(callback_query.message, student["full_name"])
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "admin:study_plan_upload_again")
async def admin_study_plan_upload_again(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    data = await state.get_data()
    await state.set_state(AdminStudyPlan.waiting_for_pdf)
    await _ask_for_pdf(callback_query.message, data.get("student_name") or "ученик")
    await callback_query.answer()


@router.message(StateFilter(AdminStudyPlan.waiting_for_pdf))
async def admin_study_plan_pdf_received(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Загрузка плана доступна только администратору.")
        return

    document = message.document
    file_name = getattr(document, "file_name", "") if document else ""
    mime_type = getattr(document, "mime_type", "") if document else ""
    if not document or (mime_type != "application/pdf" and not file_name.lower().endswith(".pdf")):
        await message.answer("⚠️ Отправьте именно PDF-файл.", reply_markup=cancel_fsm_keyboard)
        return

    max_pdf_bytes = 10 * 1024 * 1024
    if document.file_size and document.file_size > max_pdf_bytes:
        await message.answer("⚠️ PDF слишком большой (макс. 10 МБ).", reply_markup=cancel_fsm_keyboard)
        return

    try:
        tg_file = await message.bot.get_file(document.file_id)
        suffix = Path(file_name or "plan.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            await message.bot.download_file(tg_file.file_path, destination=tmp.name)
            parsed = parse_learning_plan_pdf(tmp.name)
    except Exception as exc:
        logger.warning("Failed to parse learning plan PDF: %s", exc, exc_info=True)
        await message.answer(
            "⚠️ Не удалось распарсить PDF. Попробуйте другой файл или проверьте, что это текстовый PDF.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    await state.update_data(
        pdf_file_id=document.file_id,
        pdf_file_unique_id=getattr(document, "file_unique_id", None),
        pdf_file_name=file_name or "learning-plan.pdf",
        pdf_mime_type=mime_type or "application/pdf",
        parsed_pdf={
            "text": parsed.text,
            "summary": parsed.summary,
            "status": parsed.status,
            "warnings": parsed.warnings,
            "pages_count": parsed.pages_count,
            "tables_count": parsed.tables_count,
            "file_name": file_name or "learning-plan.pdf",
            "mime_type": mime_type or "application/pdf",
        },
        plan_summary=parsed.summary,
        plan_summary_manual=False,
    )
    await _send_preview(message, state)


@router.callback_query(lambda c: c.data == "admin:study_plan_edit_summary")
async def admin_study_plan_edit_summary(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminStudyPlan.waiting_for_summary)
    await callback_query.message.edit_text(
        "✏️ Отправьте новую короткую выжимку для ученика.\n\n"
        "Она будет показана в разделе «Учебный план» и в еженедельном обзоре.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminStudyPlan.waiting_for_summary))
async def admin_study_plan_summary_received(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Редактирование доступно только администратору.")
        return
    summary = (message.text or "").strip()
    if len(summary) < 20:
        await message.answer("⚠️ Выжимка слишком короткая. Дайте хотя бы 1–2 содержательные строки.")
        return
    await state.update_data(plan_summary=summary, plan_summary_manual=True)
    await state.set_state(AdminStudyPlan.waiting_for_pdf)
    await _send_preview(message, state)


@router.callback_query(lambda c: c.data == "admin:study_plan_publish")
async def admin_study_plan_publish(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    data = await state.get_data()
    summary = (data.get("plan_summary") or "").strip()
    if len(summary) < 20:
        await callback_query.answer("Сначала заполните выжимку.", show_alert=True)
        return
    parsed = data["parsed_pdf"]
    if parsed.get("status") != "ok" and not data.get("plan_summary_manual"):
        await callback_query.answer("Сначала вручную проверьте и сохраните выжимку.", show_alert=True)
        return

    student_id = int(data["student_id"])
    plan_id = await db.publish_learning_plan(
        student_id,
        summary=summary,
        parsed_text=parsed.get("text") or "",
        parser_status=parsed.get("status") or "ok",
        parser_warnings="\n".join(parsed.get("warnings") or []),
        file_id=data["pdf_file_id"],
        file_unique_id=data.get("pdf_file_unique_id"),
        file_name=data.get("pdf_file_name"),
        mime_type=data.get("pdf_mime_type"),
        created_by=callback_query.from_user.id,
    )

    recipients = await db.get_study_plan_recipients(student_id)
    for recipient_id in recipients:
        try:
            await callback_query.bot.send_message(
                recipient_id,
                "📌 <b>Учебный план обновлён</b>\n\n"
                "Я добавил новый план и чек-лист подготовки к ближайшему уроку.",
                reply_markup=make_study_plan_open_keyboard(),
            )
        except Exception as exc:
            logger.warning("Failed to notify study plan recipient %s: %s", recipient_id, exc)

    await state.clear()
    await restore_admin_view(
        callback_query.bot,
        db,
        data.get("admin_origin_chat_id"),
        data.get("admin_origin_message_id"),
        data.get("admin_return_view"),
    )
    await callback_query.message.answer(
        build_action_result_text(
            "Учебный план опубликован",
            f"План #{plan_id} сохранён как активный. Предыдущий активный план, если был, перенесён в историю.",
            next_step="Ученик уже получил сообщение с кнопкой «Открыть учебный план».",
        ),
        reply_markup=make_back_button_keyboard("◀️ К карточке ученика", data.get("admin_return_view") or "admin:students"),
    )
    await callback_query.answer("Опубликовано.")


@router.callback_query(lambda c: c.data.startswith("admin:study_plan_item:"))
async def admin_study_plan_item_start(
    callback_query: types.CallbackQuery,
    state: FSMContext,
    db: Database,
):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _, _, student_id_str, page_str, source = callback_query.data.split(":")
    student_id = int(student_id_str)
    page = int(page_str)
    student = await db.get_user(student_id)
    if not student:
        await callback_query.answer("Ученик не найден.", show_alert=True)
        return
    await state.clear()
    await state.update_data(student_id=student_id, page=page, source=source)
    await state.set_state(AdminStudyPlan.waiting_for_checklist_item)
    await callback_query.message.edit_text(
        f"➕ Отправьте пункт чек-листа для <b>{q(student['full_name'])}</b>.\n\n"
        "Он добавится к подготовке к ближайшему уроку.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminStudyPlan.waiting_for_checklist_item))
async def admin_study_plan_item_received(message: types.Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Доступно только администратору.")
        return
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("⚠️ Пункт слишком короткий.", reply_markup=cancel_fsm_keyboard)
        return
    data = await state.get_data()
    student_id = int(data["student_id"])
    await db.add_teacher_checklist_item(student_id, title)
    await state.clear()
    await message.answer(
        build_action_result_text(
            "Пункт добавлен",
            f"Новый пункт чек-листа: <b>{q(title)}</b>",
            next_step="Он появится в разделе ученика «Учебный план».",
        ),
        reply_markup=make_back_button_keyboard(
            "◀️ К учебному плану",
            f"admin:study_plan:{student_id}:{int(data.get('page') or 0)}:{data.get('source') or 'card'}",
        ),
    )
