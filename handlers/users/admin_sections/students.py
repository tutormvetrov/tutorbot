"""Обратная совместимость — composite router + реэкспорт."""
from aiogram import Router

from handlers.users.admin_sections._students_helpers import *  # noqa: F401,F403
from handlers.users.admin_sections.students_list import router as _list_router
from handlers.users.admin_sections.students_pairs import router as _pairs_router
from handlers.users.admin_sections.students_card import router as _card_router
from handlers.users.admin_sections.students_settings import router as _settings_router
from handlers.users.admin_sections.students_lifecycle import router as _lifecycle_router
from handlers.users.admin_sections.students_freeze import router as _freeze_router

# Явные реэкспорты для common.py и pulse.py (ленивые импорты)
from handlers.users.admin_sections._students_helpers import (  # noqa: F401
    _render_admin_student_card, _render_admin_student_actions,
    _render_admin_student_settings, _render_admin_student_danger,
    _render_admin_students_page, _sort_admin_students,
)
from handlers.users.admin_sections.students_card import _show_student_card  # noqa: F401

# Реэкспорты обработчиков для тестов
from handlers.users.admin_sections.students_list import (  # noqa: F401
    admin_students,
    admin_students_page,
    admin_students_filter,
    admin_students_sort,
    admin_students_reset,
    admin_students_search_clear,
    admin_students_search_start,
    admin_students_search_back,
    admin_students_search_submit,
)
from handlers.users.admin_sections.students_pairs import (  # noqa: F401
    admin_pairs,
    admin_pair_create_start,
    admin_pair_create_primary_selected,
    admin_pair_create_partner_entered,
    admin_pair_invite_link,
    admin_pair_card,
)
from handlers.users.admin_sections.students_card import (  # noqa: F401
    admin_student_card,
    admin_student_actions,
    admin_student_settings,
    admin_student_danger,
    admin_write_to_student_start,
    admin_write_to_student_send,
    admin_student_duration_start,
    admin_student_duration_save,
    admin_student_preferred_name_start,
    admin_student_preferred_name_save,
    admin_student_tariff_start,
    admin_assign_tariff,
    lesson_followup_comment_start,
    lesson_followup_comment_save,
    lesson_followup_bookmark_start,
    lesson_followup_bookmark_save,
    lesson_followup_no_material,
)
from handlers.users.admin_sections.students_settings import (  # noqa: F401
    admin_student_format_toggle,
    admin_student_speech_style_toggle,
    admin_student_type_toggle,
    admin_student_stage,
    admin_student_stage_set,
    admin_lesson_format_toggle_list,
    admin_speech_style_toggle_list,
)
from handlers.users.admin_sections.students_lifecycle import (  # noqa: F401
    admin_student_deactivate_prompt,
    admin_student_deactivate_review,
    admin_student_deactivate_confirm_direct,
    admin_student_delete_prompt,
    admin_student_delete_review,
    admin_student_delete_confirm_direct,
    admin_select_student_manage,
    admin_deactivate_student_review,
    admin_deactivate_student_confirm,
    admin_delete_student_review,
    admin_delete_student_confirm,
    admin_add_student_start,
    admin_add_student_name,
    admin_add_student_id,
)

router = Router()
router.include_router(_list_router)
router.include_router(_pairs_router)
router.include_router(_card_router)
router.include_router(_settings_router)
router.include_router(_lifecycle_router)
router.include_router(_freeze_router)
