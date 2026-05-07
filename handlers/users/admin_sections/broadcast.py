from datetime import date

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from utils.brand import choose_tone_variant
from keyboards.inline import (
    broadcast_keyboard,
    broadcast_preview_keyboard,
    cancel_fsm_keyboard,
    make_back_button_keyboard,
    make_recipient_select_keyboard,
    make_reschedule_offer_keyboard,
    make_teacher_reply_keyboard,
    segment_filter_keyboard,
)
from utils.scheduler import build_reschedule_slot_payloads
from states.registration import AdminBroadcast
from utils.db_api.postgresql import Database
from utils.ui_text import (
    ADMIN_BROADCAST_EDIT_TEXT,
    ADMIN_BROADCAST_EMPTY_RECIPIENTS_TEXT,
    ADMIN_BROADCAST_ENTER_TEXT,
    ADMIN_BROADCAST_START_TEXT,
    admin_broadcast_recipients_text,
    build_broadcast_preview_block,
    build_broadcast_send_result_text,
    compute_student_stage,
)

from handlers.users.admin_sections.common import (
    build_level_test_broadcast_text,
    extract_broadcast_payload,
    get_message_origin,
    is_admin,
)

router = Router()

_EMPTY_FILTERS: dict = {"stages": [], "levels": [], "formats": [], "balance": [], "types": []}


def build_illness_broadcast_text(_: str | None = None) -> str:
    follow_up = choose_tone_variant(
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
    )
    return (
        "⚠️ <b>Внимание</b>\n\n"
        "Сегодняшнего урока не будет.\n"
        "Причина: заболел.\n\n"
        f"{follow_up}"
    )


def build_force_majeure_broadcast_text(_: str | None = None) -> str:
    follow_up = choose_tone_variant(
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
        "Ниже предложены ближайшие варианты переноса.",
    )
    return (
        "⚠️ <b>Внимание</b>\n\n"
        "Сегодняшнего урока не будет.\n"
        "Причина: форс-мажор.\n\n"
        f"{follow_up}"
    )


BROADCAST_TEMPLATES = {
    "illness": build_illness_broadcast_text,
    "force_majeure": build_force_majeure_broadcast_text,
    "level_test": build_level_test_broadcast_text,
}


def _resolve_broadcast_text(kind: str | None, speech_style: str | None, fallback_text: str) -> str:
    if not kind:
        return fallback_text
    template = BROADCAST_TEMPLATES.get(kind)
    if callable(template):
        return template(speech_style)
    if isinstance(template, str) and template:
        return template
    return fallback_text


def _balance_bucket(balance: int) -> str:
    if balance == 0:
        return "none"
    if balance <= 2:
        return "low"
    return "has"


def _matches_segment_filters(student: dict, filters: dict) -> bool:
    if not any(filters.values()):
        return True
    checks = [
        (filters["stages"],  student.get("stage", "")),
        (filters["levels"],  student.get("level", "")),
        (filters["formats"], student.get("lesson_format", "")),
        (filters["balance"], student.get("balance_bucket", "")),
        (filters["types"],   student.get("learning_mode", "")),
    ]
    return any(bucket and val in bucket for bucket, val in checks)


def _build_recipient_select_text(
    broadcast_preview: str,
    selected_count: int,
    total_count: int,
    broadcast_mode: str = "text",
) -> str:
    return admin_broadcast_recipients_text(
        broadcast_preview,
        selected_count,
        total_count,
        mode=broadcast_mode,
    )


async def _enter_segment_filter(target, state: FSMContext, db: Database, broadcast_preview: str):
    students = await db.get_students_for_broadcast()

    if not students:
        msg = ADMIN_BROADCAST_EMPTY_RECIPIENTS_TEXT
        back_kb = make_back_button_keyboard("◀️ К панели", "admin:home")
        if hasattr(target, 'message'):
            await target.message.edit_text(msg, reply_markup=back_kb)
            await target.answer()
        else:
            await target.answer(msg, reply_markup=back_kb)
        await state.clear()
        return

    today = date.today()
    enriched = []
    for s in students:
        stage = compute_student_stage(
            s.get("cached_first_lesson_date"),
            override=s.get("student_stage_override"),
            today=today,
        )
        enriched.append({
            "telegram_id": s["telegram_id"],
            "full_name": s["full_name"],
            "speech_style": s.get("speech_style") or "formal",
            "level": s.get("level") or "",
            "lesson_format": s.get("lesson_format") or "online",
            "balance_bucket": _balance_bucket(s.get("balance") or 0),
            "learning_mode": "pair" if s.get("is_pair") else "solo",
            "stage": stage,
        })

    filters = dict(_EMPTY_FILTERS)
    await state.update_data(broadcast_students_cache=enriched, segment_filters=filters)
    await state.set_state(AdminBroadcast.waiting_for_segment_filter)

    text = (
        "🎯 <b>Фильтр получателей</b>\n\n"
        "Выберите сегменты. Ученик попадёт в рассылку, если совпадает <b>хотя бы один</b> фильтр.\n"
        "Без фильтров — рассылка уйдёт <b>всем</b> активным ученикам."
    )
    kb = segment_filter_keyboard(filters, len(enriched))
    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


async def _enter_recipient_select(
    target,
    state: FSMContext,
    db: Database,
    broadcast_preview: str,
    preselected_ids: set[int] | None = None,
):
    data = await state.get_data()
    raw = data.get("broadcast_students_cache")
    if raw is None:
        raw = await db.get_all_students()

    if not raw:
        msg = ADMIN_BROADCAST_EMPTY_RECIPIENTS_TEXT
        back_kb = make_back_button_keyboard("◀️ К панели", "admin:home")
        if hasattr(target, 'message'):
            await target.message.edit_text(msg, reply_markup=back_kb)
            await target.answer()
        else:
            await target.answer(msg, reply_markup=back_kb)
        await state.clear()
        return

    cache = [
        {
            'telegram_id': s['telegram_id'],
            'full_name': s['full_name'],
            'speech_style': s.get('speech_style') or 'formal',
        }
        for s in raw
    ]
    initial_selected = preselected_ids if preselected_ids is not None else set()
    await state.update_data(recipient_ids=list(initial_selected), students_cache=cache)
    await state.set_state(AdminBroadcast.waiting_for_recipients)

    total = len(cache)
    data = await state.get_data()
    text = _build_recipient_select_text(
        broadcast_preview,
        len(initial_selected),
        total,
        data.get("broadcast_mode", "text"),
    )
    kb = make_recipient_select_keyboard(cache, initial_selected)
    if hasattr(target, 'message'):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


async def _show_broadcast_preview(target, state: FSMContext, broadcast_preview: str):
    await state.set_state(AdminBroadcast.waiting_for_text_confirm)
    data = await state.get_data()
    mode = data.get("broadcast_mode", "text")
    text = (
        "📢 <b>Предпросмотр рассылки</b>\n\n"
        "Именно так сообщение увидят выбранные ученики:\n\n"
        f"{build_broadcast_preview_block(mode, broadcast_preview)}\n\n"
        "Если всё выглядит хорошо, можно перейти к выбору получателей."
    )
    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=broadcast_preview_keyboard)
        await target.answer()
    else:
        await target.answer(text, reply_markup=broadcast_preview_keyboard)


@router.callback_query(lambda c: c.data == 'admin:broadcast')
async def admin_broadcast_start(callback_query: types.CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await callback_query.message.edit_text(
        ADMIN_BROADCAST_START_TEXT,
        reply_markup=broadcast_keyboard,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data.startswith('broadcast:'))
async def admin_broadcast_select(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    kind = callback_query.data.split(':', 1)[1]
    origin_chat_id, origin_message_id = get_message_origin(callback_query.message, callback_query.from_user.id)
    await state.clear()
    await state.update_data(
        admin_return_view="admin:home",
        admin_origin_chat_id=origin_chat_id,
        admin_origin_message_id=origin_message_id,
    )

    if kind == 'custom':
        await state.set_state(AdminBroadcast.waiting_for_text)
        await state.update_data(broadcast_kind="custom")
        await callback_query.message.edit_text(
            ADMIN_BROADCAST_ENTER_TEXT,
            reply_markup=cancel_fsm_keyboard,
        )
        await callback_query.answer()
        return

    template = BROADCAST_TEMPLATES.get(kind, '')
    broadcast_text = template() if callable(template) else template
    await state.update_data(
        broadcast_kind=kind,
        broadcast_mode="text",
        broadcast_text=broadcast_text,
        broadcast_preview=broadcast_text,
        broadcast_source_chat_id=None,
        broadcast_source_message_id=None,
    )
    await _show_broadcast_preview(callback_query, state, broadcast_text)


@router.message(StateFilter(AdminBroadcast.waiting_for_text))
async def admin_broadcast_text_entered(message: types.Message, state: FSMContext):
    payload = extract_broadcast_payload(message)
    if not payload:
        await message.answer(
            "⚠️ Отправьте текст, стикер, GIF или другое сообщение, которое нужно разослать.",
            reply_markup=cancel_fsm_keyboard,
        )
        return
    await state.update_data(
        broadcast_kind="custom",
        broadcast_mode=payload["mode"],
        broadcast_text=payload.get("text"),
        broadcast_preview=payload["preview"],
        broadcast_source_chat_id=payload.get("source_chat_id"),
        broadcast_source_message_id=payload.get("source_message_id"),
    )
    await _show_broadcast_preview(message, state, payload["preview"])


@router.callback_query(lambda c: c.data == 'bc_confirm', StateFilter(AdminBroadcast.waiting_for_text_confirm))
async def admin_broadcast_confirm_text(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    data = await state.get_data()
    await _enter_segment_filter(
        callback_query,
        state,
        db,
        data.get('broadcast_preview') or data.get('broadcast_text', ''),
    )


@router.callback_query(lambda c: c.data == 'bc_edit_text', StateFilter(AdminBroadcast.waiting_for_text_confirm))
async def admin_broadcast_edit_text(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminBroadcast.waiting_for_text)
    await callback_query.message.edit_text(
        ADMIN_BROADCAST_EDIT_TEXT,
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data == 'bc_back_preview',
    StateFilter(AdminBroadcast.waiting_for_recipients, AdminBroadcast.waiting_for_segment_filter),
)
async def admin_broadcast_back_preview(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    await _show_broadcast_preview(
        callback_query,
        state,
        data.get("broadcast_preview") or data.get("broadcast_text", ""),
    )


# ── segment filter handlers ───────────────────────────────────────────────────

@router.callback_query(
    lambda c: c.data.startswith("bc_filter:") and len(c.data.split(":")) == 3,
    StateFilter(AdminBroadcast.waiting_for_segment_filter),
)
async def bc_filter_toggle(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    _, cat, val = callback_query.data.split(":")
    data = await state.get_data()
    filters = data.get("segment_filters", dict(_EMPTY_FILTERS))

    bucket = filters.get(cat, [])
    filters[cat] = [v for v in bucket if v != val] if val in bucket else bucket + [val]
    await state.update_data(segment_filters=filters)

    students = data.get("broadcast_students_cache", [])
    count = sum(1 for s in students if _matches_segment_filters(s, filters))
    await callback_query.message.edit_reply_markup(reply_markup=segment_filter_keyboard(filters, count))
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data == "bc_filter:reset",
    StateFilter(AdminBroadcast.waiting_for_segment_filter),
)
async def bc_filter_reset(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    filters = dict(_EMPTY_FILTERS)
    await state.update_data(segment_filters=filters)
    data = await state.get_data()
    count = len(data.get("broadcast_students_cache", []))
    await callback_query.message.edit_reply_markup(reply_markup=segment_filter_keyboard(filters, count))
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data == "bc_filter:apply",
    StateFilter(AdminBroadcast.waiting_for_segment_filter),
)
async def bc_filter_apply(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    filters = data.get("segment_filters", dict(_EMPTY_FILTERS))
    students = data.get("broadcast_students_cache", [])
    preselected = {s["telegram_id"] for s in students if _matches_segment_filters(s, filters)}
    broadcast_preview = data.get("broadcast_preview") or data.get("broadcast_text", "")
    await _enter_recipient_select(callback_query, state, db, broadcast_preview, preselected)


@router.callback_query(
    lambda c: c.data == "bc_filter:skip",
    StateFilter(AdminBroadcast.waiting_for_segment_filter),
)
async def bc_filter_skip(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    broadcast_preview = data.get("broadcast_preview") or data.get("broadcast_text", "")
    await _enter_recipient_select(callback_query, state, db, broadcast_preview, preselected_ids=None)


# ── recipient select handlers ─────────────────────────────────────────────────

@router.callback_query(
    lambda c: c.data.startswith('bc_toggle:'),
    StateFilter(AdminBroadcast.waiting_for_recipients),
)
async def bc_toggle_recipient(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(':')[1])
    data = await state.get_data()
    selected = set(data.get('recipient_ids', []))
    if student_id in selected:
        selected.discard(student_id)
    else:
        selected.add(student_id)
    await state.update_data(recipient_ids=list(selected))

    students = data.get('students_cache', [])
    broadcast_preview = data.get('broadcast_preview') or data.get('broadcast_text', '')
    text = _build_recipient_select_text(
        broadcast_preview,
        len(selected),
        len(students),
        data.get("broadcast_mode", "text"),
    )
    await callback_query.message.edit_text(text, reply_markup=make_recipient_select_keyboard(students, selected))
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data in ('bc_all', 'bc_none'),
    StateFilter(AdminBroadcast.waiting_for_recipients),
)
async def bc_select_all_none(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    students = data.get('students_cache', [])
    selected = {student['telegram_id'] for student in students} if callback_query.data == 'bc_all' else set()
    await state.update_data(recipient_ids=list(selected))

    broadcast_preview = data.get('broadcast_preview') or data.get('broadcast_text', '')
    text = _build_recipient_select_text(
        broadcast_preview,
        len(selected),
        len(students),
        data.get("broadcast_mode", "text"),
    )
    await callback_query.message.edit_text(text, reply_markup=make_recipient_select_keyboard(students, selected))
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'bc_send', StateFilter(AdminBroadcast.waiting_for_recipients))
async def bc_send(callback_query: types.CallbackQuery, state: FSMContext, db: Database | None = None):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    data = await state.get_data()
    selected_ids = set(data.get('recipient_ids', []))
    if not selected_ids:
        await callback_query.answer("Выберите хотя бы одного получателя!", show_alert=True)
        return

    broadcast_mode = data.get("broadcast_mode", "text")
    broadcast_text = data.get('broadcast_text', '')
    broadcast_kind = data.get("broadcast_kind")
    source_chat_id = data.get("broadcast_source_chat_id")
    source_message_id = data.get("broadcast_source_message_id")
    students_cache = {
        student["telegram_id"]: student
        for student in data.get("students_cache", [])
    }
    reschedule_slots = (
        await build_reschedule_slot_payloads(db)
        if db is not None and broadcast_kind in {"illness", "force_majeure"}
        else []
    )
    await state.clear()

    sent = 0
    for student_id in selected_ids:
        try:
            if broadcast_mode == "copy" and source_chat_id and source_message_id:
                await callback_query.bot.copy_message(
                    chat_id=student_id,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                    reply_markup=make_teacher_reply_keyboard("broadcast"),
                )
            else:
                student = students_cache.get(student_id)
                personalized_text = _resolve_broadcast_text(
                    broadcast_kind,
                    student.get("speech_style") if student else None,
                    broadcast_text,
                )
                reply_markup = make_teacher_reply_keyboard("broadcast")
                if reschedule_slots:
                    personalized_text += "\n\nВыберите удобный вариант переноса кнопкой ниже."
                    reply_markup = make_reschedule_offer_keyboard(reschedule_slots)
                await callback_query.bot.send_message(
                    student_id,
                    personalized_text,
                    reply_markup=reply_markup,
                )
            sent += 1
        except Exception:
            continue

    await callback_query.message.edit_text(
        build_broadcast_send_result_text(sent, len(selected_ids)),
        reply_markup=make_back_button_keyboard("◀️ К панели", "admin:home"),
    )
    await callback_query.answer()
