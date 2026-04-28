from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    waiting_for_role = State()
    waiting_for_full_name = State()
    waiting_for_age = State()
    waiting_for_language = State()
    waiting_for_level = State()
    waiting_for_pair_partner_name = State()
    waiting_for_child_name = State()
    waiting_for_child_age = State()
    waiting_for_student_info = State()


class FreezeConfirm(StatesGroup):
    waiting_for_confirm = State()


class AdminAddLesson(StatesGroup):
    waiting_for_lesson_student = State()
    waiting_for_lesson_date = State()


class AdminAddPayment(StatesGroup):
    waiting_for_payment_student = State()
    waiting_for_payment_amount = State()
    waiting_for_payment_count = State()


class AdminPricing(StatesGroup):
    waiting_for_rate = State()


class AdminAddStudent(StatesGroup):
    waiting_for_name = State()
    waiting_for_telegram_id = State()


class AdminCreatePair(StatesGroup):
    waiting_for_partner_name = State()


class AdminBroadcast(StatesGroup):
    waiting_for_text = State()
    waiting_for_text_confirm = State()
    waiting_for_recipients = State()


class AdminManageStudent(StatesGroup):
    waiting_for_student = State()


class AdminStudentsDirectory(StatesGroup):
    browsing = State()
    waiting_for_search = State()


class AdminParentsDirectory(StatesGroup):
    browsing = State()
    waiting_for_search = State()


class AdminAddHomework(StatesGroup):
    waiting_for_student = State()
    waiting_for_description = State()
    waiting_for_deadline = State()


class AdminEditHomework(StatesGroup):
    waiting_for_description = State()
    waiting_for_deadline = State()


class AdminNotes(StatesGroup):
    waiting_for_text = State()


class AdminManageLessons(StatesGroup):
    waiting_for_student = State()


class AdminWriteToStudent(StatesGroup):
    waiting_for_message = State()


class AdminLessonFollowup(StatesGroup):
    waiting_for_lesson_comment = State()
    waiting_for_lesson_bookmark = State()
    waiting_for_lesson_duration = State()


class AdminStudyPlan(StatesGroup):
    waiting_for_pdf = State()
    waiting_for_summary = State()
    waiting_for_checklist_item = State()


class StudentReply(StatesGroup):
    waiting_for_message = State()


class AdminCalendarAliases(StatesGroup):
    waiting_for_student = State()
    waiting_for_aliases = State()
