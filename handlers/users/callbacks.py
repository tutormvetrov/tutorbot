"""Обратная совместимость — composite router + реэкспорт."""
from aiogram import Router

from handlers.users._cb_helpers import *  # noqa: F401,F403
from handlers.users.cb_navigation import router as _nav_router
from handlers.users.cb_parent import router as _parent_router
from handlers.users.cb_reply import router as _reply_router
from handlers.users.cb_profile import router as _profile_router
from handlers.users.cb_freeze import router as _freeze_router
from handlers.users.cb_misc import router as _misc_router
from handlers.users.cb_guides import router as _guides_router
from handlers.users.cb_guides import GUIDE_ALLOWED_BY_ROLE  # noqa: F401

# Явные реэкспорты для внешних импортов (start.py, menu.py, тесты)
from handlers.users.cb_profile import (  # noqa: F401
    _build_contacts_text, _get_materials_url, process_materials,
    process_requisites, process_profile_delete_me, process_self_delete_confirm,
    process_self_delete_review,
)
from handlers.users.cb_reply import start_student_reply  # noqa: F401
from handlers.users._cb_helpers import _get_learning_student_id  # noqa: F401
from handlers.users.cb_navigation import (  # noqa: F401
    process_menu_choice,
    process_study_plan, process_study_plan_file, process_study_plan_toggle,
    back_to_menu, cancel_fsm,
)
from handlers.users.cb_misc import (  # noqa: F401
    process_homework, process_homework_list, process_homework_detail,
    process_homework_attachment, process_homework_done,
    process_lesson_presence, process_reschedule_pick,
    process_notif_manage, process_notif_action,
    process_more, process_progress,
    process_lesson_feedback,
    process_work_rules, process_work_rules_accept,
    lesson_followup_no_show, admin_no_show_from_card, no_show_confirm, no_show_cancel,
)
from handlers.users.cb_parent import (  # noqa: F401
    process_parent_home, process_parent_engagement_toggle,
    process_parent_child_schedule, process_parent_child_homework_detail,
    process_parent_child_homework_file, process_parent_child_homework,
    process_parent_child_payments, process_parent_child_study_plan,
    process_parent_child_study_plan_file, process_parent_child_progress,
    process_parent_child_requisites, process_parent_child_home,
)
from handlers.users.cb_freeze import (  # noqa: F401
    process_freeze_reason, process_freeze_confirm,
)

router = Router()
router.include_router(_nav_router)
router.include_router(_parent_router)
router.include_router(_reply_router)
router.include_router(_profile_router)
router.include_router(_freeze_router)
router.include_router(_misc_router)
router.include_router(_guides_router)
