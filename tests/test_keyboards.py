import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from datetime import datetime

from keyboards.inline import (
    admin_education_keyboard,
    admin_keyboard,
    admin_service_keyboard,
    admin_students_keyboard,
    make_admin_education_keyboard,
    make_admin_inbox_keyboard,
    make_admin_inbox_item_keyboard,
    make_admin_parent_card_keyboard,
    make_admin_parent_danger_keyboard,
    make_admin_parents_list_keyboard,
    make_admin_student_card_keyboard,
    make_admin_students_list_keyboard,
    make_admin_today_keyboard,
    make_contacts_keyboard,
    make_first_lesson_invite_keyboard,
    make_homework_item_keyboard,
    make_lesson_delete_confirm_keyboard,
    make_lesson_followup_keyboard,
    make_lesson_presence_keyboard,
    make_materials_keyboard,
    make_parent_home_keyboard,
    make_parent_payments_keyboard,
    make_profile_danger_keyboard,
    make_pricing_rates_keyboard,
    make_schedule_keyboard,
    make_self_delete_review_keyboard,
    make_study_plan_keyboard,
    make_teacher_reply_keyboard,
    parent_main_keyboard,
    parent_more_keyboard,
    parent_profile_keyboard,
    payment_keyboard,
    profile_keyboard,
    student_main_keyboard,
    student_more_keyboard,
)


class KeyboardHelpersTest(unittest.TestCase):
    def test_student_main_menu_puts_schedule_first_and_drops_duplicate_requisites(self):
        texts = [button.text for row in student_main_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in student_main_keyboard.inline_keyboard for button in row if button.callback_data]

        self.assertEqual(student_main_keyboard.inline_keyboard[0][0].text, "📅 Расписание")
        self.assertEqual(len(student_main_keyboard.inline_keyboard), 5)
        self.assertIn("schedule", callbacks)
        self.assertIn("study_plan", callbacks)
        self.assertIn("homework", callbacks)
        self.assertIn("materials", callbacks)
        self.assertIn("reply:general", callbacks)
        self.assertIn("more", callbacks)
        self.assertNotIn("requisites", callbacks)
        self.assertNotIn("💳 Реквизиты", texts)

    def test_student_main_menu_drops_freeze_and_profile(self):
        texts = [button.text for row in student_main_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in student_main_keyboard.inline_keyboard for button in row if button.callback_data]

        self.assertNotIn("❄️ Заморозка", texts)
        self.assertNotIn("👤 Профиль", texts)
        self.assertNotIn("freeze", callbacks)
        self.assertNotIn("profile", callbacks)
        self.assertIn("👤 Ещё", texts)

    def test_student_more_keyboard_contains_all_nested_actions(self):
        texts = [button.text for row in student_more_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in student_more_keyboard.inline_keyboard for button in row if button.callback_data]

        self.assertIn("👤 Профиль", texts)
        self.assertIn("🔔 Управление уведомлениями", texts)
        self.assertIn("🧪 Тест уровня", texts)
        self.assertIn("❄️ Заморозка", texts)
        self.assertIn("🛡 Опасные действия", texts)
        self.assertIn("◀️ Главное меню", texts)
        self.assertIn("profile", callbacks)
        self.assertIn("notif:manage", callbacks)
        self.assertIn("level_test:now", callbacks)
        self.assertIn("freeze", callbacks)
        self.assertIn("profile:danger", callbacks)
        self.assertIn("back_to_menu", callbacks)

    def test_parent_main_menu_drops_profile_and_adds_more(self):
        callbacks = [button.callback_data for row in parent_main_keyboard.inline_keyboard for button in row if button.callback_data]
        texts = [button.text for row in parent_main_keyboard.inline_keyboard for button in row]

        self.assertIn("parent:home", callbacks)
        self.assertIn("materials", callbacks)
        self.assertIn("contacts", callbacks)
        self.assertIn("reply:general", callbacks)
        self.assertIn("more", callbacks)
        self.assertNotIn("requisites", callbacks)
        self.assertNotIn("💳 Реквизиты", texts)
        self.assertNotIn("👤 Профиль", texts)
        self.assertNotIn("profile", callbacks)
        self.assertIn("👤 Ещё", texts)

    def test_parent_more_keyboard_contains_profile_and_danger(self):
        texts = [button.text for row in parent_more_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in parent_more_keyboard.inline_keyboard for button in row if button.callback_data]

        self.assertIn("👤 Профиль родителя", texts)
        self.assertIn("🛡 Опасные действия", texts)
        self.assertIn("◀️ Главное меню", texts)
        self.assertIn("profile", callbacks)
        self.assertIn("profile:danger", callbacks)
        self.assertIn("back_to_menu", callbacks)

    def test_parent_main_menu_drops_duplicate_requisites(self):
        callbacks = [button.callback_data for row in parent_main_keyboard.inline_keyboard for button in row if button.callback_data]
        texts = [button.text for row in parent_main_keyboard.inline_keyboard for button in row]

        self.assertIn("parent:home", callbacks)
        self.assertIn("materials", callbacks)
        self.assertIn("contacts", callbacks)
        self.assertNotIn("requisites", callbacks)
        self.assertNotIn("💳 Реквизиты", texts)

    def test_schedule_keyboard_exposes_calendar_url(self):
        kb = make_schedule_keyboard("https://calendar.google.com/example")
        urls = [button.url for row in kb.inline_keyboard for button in row if getattr(button, "url", None)]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("https://calendar.google.com/example", urls)
        self.assertIn("back_to_menu", callbacks)

    def test_schedule_keyboard_without_calendar_url_keeps_back_button(self):
        kb = make_schedule_keyboard()
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertEqual(callbacks, ["back_to_menu"])

    def test_materials_keyboard_renders_resources_with_primary_first(self):
        resources = [
            {"id": 1, "student_id": None, "label": "Аудио", "url": "https://filen.io/a", "provider": "filen", "is_primary": False},
            {"id": 2, "student_id": None, "label": "Курс B1", "url": "https://docs.google.com/c", "provider": "gdocs", "is_primary": True},
        ]
        kb = make_materials_keyboard(resources, website_url="https://site")
        urls = [button.url for row in kb.inline_keyboard for button in row if getattr(button, "url", None)]
        texts = [button.text for row in kb.inline_keyboard for button in row]
        # Primary should appear before others.
        self.assertEqual(urls[0], "https://docs.google.com/c")
        self.assertIn("⭐", texts[0])
        self.assertIn("https://filen.io/a", urls)

    def test_materials_keyboard_falls_back_to_website_when_empty(self):
        kb = make_materials_keyboard([], website_url="https://teacher.example")
        urls = [button.url for row in kb.inline_keyboard for button in row if getattr(button, "url", None)]
        self.assertEqual(urls, ["https://teacher.example"])

    def test_first_lesson_invite_keyboard_exposes_payment_actions(self):
        kb = make_first_lesson_invite_keyboard()
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("requisites", callbacks)
        self.assertIn("payment", callbacks)
        self.assertIn("reply:payment", callbacks)

    def test_study_plan_keyboard_exposes_pdf_and_checklist_toggles(self):
        kb = make_study_plan_keyboard(
            {"id": 7},
            [
                {"id": 1, "title": "Открыть ДЗ", "status": "pending"},
                {"id": 2, "title": "Повторить материал", "status": "done"},
            ],
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("📄 Открыть PDF-план", texts)
        self.assertIn("☐ Открыть ДЗ", texts)
        self.assertIn("✅ Повторить материал", texts)
        self.assertIn("study_plan:file:7", callbacks)
        self.assertIn("study_plan:toggle:1", callbacks)
        self.assertIn("study_plan:toggle:2", callbacks)

    def test_pricing_rates_keyboard_supports_arbitrary_group_size(self):
        kb = make_pricing_rates_keyboard([
            {"group_size": 3, "duration_minutes": 75, "amount": 6000, "currency": "RUB"}
        ])
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("3 уч. · 75 мин · 6000 RUB", texts)

    def test_lesson_presence_keyboard_contains_expected_buttons(self):
        kb = make_lesson_presence_keyboard(42)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✅ Буду вовремя", texts)
        self.assertIn("⏱ Немного задержусь", texts)
        self.assertIn("✉️ Написать преподавателю", texts)
        self.assertIn("lesson_presence:on_time:42", callbacks)
        self.assertIn("lesson_presence:late:42", callbacks)
        self.assertIn("reply:lesson:42", callbacks)

    def test_contacts_keyboard_keeps_expected_links(self):
        kb = make_contacts_keyboard(
            vk_call_url="https://vk.com/call/join/example",
            google_meet_url="https://meet.google.com/example",
        )
        self.assertEqual(kb.inline_keyboard[0][0].text, "📞 VK Звонок")
        self.assertEqual(kb.inline_keyboard[0][0].url, "https://vk.com/call/join/example")
        self.assertEqual(kb.inline_keyboard[1][0].text, "📹 Google Meet (VPN)")
        self.assertEqual(kb.inline_keyboard[1][0].url, "https://meet.google.com/example")

    def test_contacts_keyboard_no_longer_carries_calendar_or_materials_links(self):
        # The Google Calendar URL now lives on the Schedule screen and the
        # materials URL has its own top-level entry. Contacts keeps only
        # connection-related links so the schedule shortcut isn't ambiguous.
        kb = make_contacts_keyboard(
            booking_url="https://t.me/teacher",
            vk_call_url="https://vk.com/call/example",
            google_meet_url="https://meet.google.com/example",
            website_url="https://teacher.example",
        )
        urls = [button.url for row in kb.inline_keyboard for button in row if getattr(button, "url", None)]
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertNotIn("📅 Открыть расписание", texts)
        self.assertNotIn("📁 Учебные материалы", texts)
        self.assertIn("https://t.me/teacher", urls)
        self.assertIn("https://teacher.example", urls)

    def test_student_payment_keyboard_groups_payment_actions(self):
        texts = [button.text for row in payment_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in payment_keyboard.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✉️ Сообщить об оплате", texts)
        self.assertIn("💳 Реквизиты", texts)
        self.assertIn("reply:payment", callbacks)
        self.assertIn("payment:requisites", callbacks)

    def test_parent_profile_keyboard_stays_parent_specific(self):
        texts = [button.text for row in parent_profile_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in parent_profile_keyboard.inline_keyboard for button in row if button.callback_data]

        self.assertEqual(
            texts,
            [
                "👨‍👩‍👧 Открыть детей",
                "✉️ Написать преподавателю",
                "🛡 Опасные действия",
                "◀️ Главное меню",
            ],
        )
        self.assertIn("parent:home", callbacks)
        self.assertIn("reply:general", callbacks)
        self.assertIn("profile:danger", callbacks)

    def test_parent_payments_keyboard_exposes_requisites_and_back(self):
        kb = make_parent_payments_keyboard(7)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✉️ Сообщить об оплате", texts)
        self.assertIn("💳 Реквизиты", texts)
        self.assertIn("◀️ К ребёнку", texts)
        self.assertIn("reply:payment", callbacks)
        self.assertIn("parent:child:7:requisites", callbacks)
        self.assertIn("parent:child:7", callbacks)

    def test_profile_danger_is_second_step(self):
        texts = [button.text for row in profile_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in profile_keyboard.inline_keyboard for button in row if button.callback_data]
        danger_texts = [button.text for row in make_profile_danger_keyboard().inline_keyboard for button in row]
        review_texts = [button.text for row in make_self_delete_review_keyboard().inline_keyboard for button in row]

        self.assertIn("🛡 Опасные действия", texts)
        self.assertIn("profile:danger", callbacks)
        self.assertEqual(danger_texts, ["🗑 Удалить профиль", "◀️ Назад в профиль"])
        self.assertEqual(review_texts, ["⚠️ Я понимаю последствия", "◀️ Назад"])

    def test_admin_students_list_keyboard_matches_actual_search_scope(self):
        students = [
            {"telegram_id": 1, "full_name": "Анна Иванова"},
            {"telegram_id": 2, "full_name": "Борис Петров"},
        ]
        kb = make_admin_students_list_keyboard(
            students,
            page=0,
            page_size=5,
            active_filter="attention",
            active_sort="balance",
            has_query=True,
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("🔎 Поиск: имя, ID, язык", texts)
        self.assertIn("🧹 Сбросить", texts)
        self.assertIn("• Нужно внимание", texts)
        self.assertIn("• Баланс", texts)
        self.assertIn("✖️ Очистить поиск", texts)
        self.assertIn("admin:students:search", callbacks)
        self.assertIn("admin:students:filter:attention", callbacks)
        self.assertIn("admin:students:sort:balance", callbacks)
        self.assertIn("admin:students:search_clear", callbacks)

    def test_admin_parents_list_keyboard_matches_actual_search_scope(self):
        parents = [
            {"telegram_id": 701, "full_name": "Мария Иванова"},
            {"telegram_id": 702, "full_name": "Елена Петрова"},
        ]
        kb = make_admin_parents_list_keyboard(parents, page=0, page_size=5, has_query=True)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("🔎 Поиск: имя или ID", texts)
        self.assertIn("✖️ Очистить поиск", texts)
        self.assertIn("admin:parents:search", callbacks)
        self.assertIn("admin:parents:search_clear", callbacks)
        self.assertIn("admin:parent_card:701:0", callbacks)
        self.assertIn("admin:parent_card:702:0", callbacks)

    def test_admin_card_keyboards_expose_current_actions(self):
        student_kb = make_admin_student_card_keyboard(
            telegram_id=555,
            page=2,
            lesson_format="offline",
            speech_style="formal",
            lesson_duration_minutes=120,
        )
        parent_card_kb = make_admin_parent_card_keyboard(telegram_id=701, page=2)
        parent_danger_kb = make_admin_parent_danger_keyboard(telegram_id=701, page=2)

        student_callbacks = [button.callback_data for row in student_kb.inline_keyboard for button in row if button.callback_data]
        parent_card_callbacks = [button.callback_data for row in parent_card_kb.inline_keyboard for button in row if button.callback_data]
        parent_danger_callbacks = [button.callback_data for row in parent_danger_kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("admin:student_actions:555:2", student_callbacks)
        self.assertIn("admin:student_settings:555:2", student_callbacks)
        self.assertIn("admin:student_danger:555:2", student_callbacks)
        self.assertIn("admin:parent_preview_select:701:2", parent_card_callbacks)
        self.assertIn("admin:parent_danger:701:2", parent_card_callbacks)
        self.assertIn("admin:parent_deactivate_prompt:701:2", parent_danger_callbacks)
        self.assertIn("admin:parent_delete_prompt:701:2", parent_danger_callbacks)

    def test_admin_section_keyboards_no_longer_expose_legacy_danger_entrypoints(self):
        student_texts = [button.text for row in admin_students_keyboard.inline_keyboard for button in row]
        education_texts = [button.text for row in admin_education_keyboard.inline_keyboard for button in row]
        service_texts = [button.text for row in admin_service_keyboard.inline_keyboard for button in row]

        self.assertIn("📋 Список учеников", student_texts)
        self.assertIn("👨‍👩‍👧 Родители", student_texts)
        self.assertIn("👤 Добавить ученика", student_texts)
        self.assertNotIn("🏫 Формат занятий", student_texts)
        self.assertNotIn("🗣 Обращение", student_texts)
        self.assertNotIn("🗑 Деактивировать", student_texts)
        self.assertNotIn("💀 Полный сброс", student_texts)
        # Education keyboard is now verb-style
        self.assertNotIn("📊 Мониторинг", service_texts)
        self.assertNotIn("🧠 Контекст и проект", service_texts)
        # Flat service keyboard has individual items
        self.assertIn("🏥 Здоровье бота", service_texts)
        self.assertIn("📝 Рабочие заметки", service_texts)
        self.assertIn("🧪 Просмотр ролей", service_texts)

    def test_homework_item_keyboard_keeps_detail_and_attachment_actions(self):
        active_kb = make_homework_item_keyboard(42, "active")
        attachment_kb = make_homework_item_keyboard(42, "active", has_attachment=True)

        active_texts = [button.text for row in active_kb.inline_keyboard for button in row]
        active_callbacks = [button.callback_data for row in active_kb.inline_keyboard for button in row if button.callback_data]
        attachment_texts = [button.text for row in attachment_kb.inline_keyboard for button in row]
        attachment_callbacks = [button.callback_data for row in attachment_kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✅ Отметить как выполненное", active_texts)
        self.assertIn("✉️ Написать по ДЗ", active_texts)
        self.assertIn("hw_done:42", active_callbacks)
        self.assertIn("reply:homework:42", active_callbacks)
        self.assertIn("📎 Открыть файл", attachment_texts)
        self.assertIn("hw:file:42:active", attachment_callbacks)

    def test_reply_and_followup_keyboards_keep_expected_callbacks(self):
        reply_kb = make_teacher_reply_keyboard("general")
        followup_kb = make_lesson_followup_keyboard(42, 555)
        reply_callbacks = [button.callback_data for row in reply_kb.inline_keyboard for button in row if button.callback_data]
        followup_callbacks = [button.callback_data for row in followup_kb.inline_keyboard for button in row if button.callback_data]

        self.assertEqual(reply_callbacks, ["reply:general"])
        self.assertIn("lesson_followup:comment:42", followup_callbacks)
        self.assertIn("lesson_followup:bookmark:42:555", followup_callbacks)
        self.assertIn("lesson_followup:no_material:42:555", followup_callbacks)

    def test_lesson_delete_keyboard_keeps_calendar_option_when_available(self):
        kb = make_lesson_delete_confirm_keyboard(42, can_delete_from_calendar=True)
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("lesson_delete:42:db", callbacks)
        self.assertIn("lesson_delete:42:calendar", callbacks)

    def test_admin_home_keyboard_has_today_and_inbox(self):
        texts = [button.text for row in admin_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in admin_keyboard.inline_keyboard for button in row if button.callback_data]
        self.assertEqual(
            texts,
            [
                "🎯 Сегодня",
                "👥 Ученики",
                "📚 Учебный процесс",
                "💬 Inbox",
                "📢 Рассылка",
                "⚙️ Сервис",
                "◀️ Главное меню",
            ],
        )
        self.assertIn("admin:today", callbacks)
        self.assertIn("admin:inbox", callbacks)
        self.assertNotIn("🧪 Просмотр ролей", texts)

    def test_admin_service_keyboard_is_flat(self):
        service_texts = [button.text for row in admin_service_keyboard.inline_keyboard for button in row]
        service_callbacks = [button.callback_data for row in admin_service_keyboard.inline_keyboard for button in row if button.callback_data]
        self.assertIn("🏥 Здоровье бота", service_texts)
        self.assertIn("🔄 Синхронизация Calendar", service_texts)
        self.assertIn("🧭 Алиасы Calendar", service_texts)
        self.assertIn("📋 Отчёт синхронизации", service_texts)
        self.assertIn("🎨 Тональность бренда", service_texts)
        self.assertIn("📝 Рабочие заметки", service_texts)
        self.assertIn("🧪 Просмотр ролей", service_texts)
        self.assertNotIn("📊 Мониторинг", service_texts)
        self.assertNotIn("🧠 Контекст и проект", service_texts)

    def test_admin_students_keyboard_has_no_format_or_speech_buttons(self):
        student_texts = [button.text for row in admin_students_keyboard.inline_keyboard for button in row]
        self.assertNotIn("🏫 Формат занятий", student_texts)
        self.assertNotIn("🗣 Обращение", student_texts)
        self.assertIn("📋 Список учеников", student_texts)
        self.assertIn("👨‍👩‍👧 Родители", student_texts)
        self.assertIn("👥 Пары", student_texts)
        self.assertIn("👤 Добавить ученика", student_texts)

    def test_make_admin_education_keyboard_with_freeze_count(self):
        kb_zero = make_admin_education_keyboard(0)
        kb_three = make_admin_education_keyboard(3)
        texts_zero = [button.text for row in kb_zero.inline_keyboard for button in row]
        texts_three = [button.text for row in kb_three.inline_keyboard for button in row]
        callbacks_zero = [button.callback_data for row in kb_zero.inline_keyboard for button in row if button.callback_data]

        self.assertIn("❄️ Заявки на заморозку", texts_zero)
        self.assertNotIn("❄️ Заявки на заморозку (0)", texts_zero)
        self.assertIn("❄️ Заявки на заморозку (3)", texts_three)
        self.assertIn("admin:freezes", callbacks_zero)
        self.assertIn("💳 Тарифы", texts_zero)

    def test_make_admin_today_keyboard_exposes_expected_callbacks(self):
        snapshot = {
            "lessons_today": [],
            "unpaid_count": 2,
            "missing_homework_count": 1,
            "pending_freeze_count": 3,
            "unanswered_replies_count": 0,
        }
        kb = make_admin_today_keyboard(snapshot)
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("admin:today:lessons", callbacks)
        self.assertIn("admin:today:unpaid", callbacks)
        self.assertIn("admin:today:missing_hw", callbacks)
        self.assertIn("admin:freezes", callbacks)
        self.assertIn("admin:inbox", callbacks)
        self.assertIn("admin:home", callbacks)
        self.assertIn("❄️ Заявки на заморозку (3)", texts)


class AdminInboxKeyboardTest(unittest.TestCase):
    def test_make_admin_inbox_keyboard_empty_has_mark_all_and_back(self):
        kb = make_admin_inbox_keyboard([])
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("✓ Отметить всё прочитанным", texts)
        self.assertIn("◀️ К панели", texts)
        self.assertIn("admin:inbox:mark_all_read", callbacks)
        self.assertIn("admin:home", callbacks)

    def test_make_admin_inbox_keyboard_with_events_shows_item_buttons(self):
        events = [
            {
                "id": 1,
                "kind": "reply",
                "payload": {"full_name": "Иван", "context": "homework", "message_preview": "Не понял"},
                "created_at": datetime.now(),
                "handled_at": None,
            },
        ]
        kb = make_admin_inbox_keyboard(events)
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("admin:inbox:item:1", callbacks)
        self.assertIn("admin:inbox:mark_all_read", callbacks)

    def test_make_admin_inbox_item_keyboard_has_reply_close_back(self):
        kb = make_admin_inbox_item_keyboard(42, "reply")
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("✉️ Ответить", texts)
        self.assertIn("✓ Закрыть", texts)
        self.assertIn("◀️ К Inbox", texts)
        self.assertIn("admin:inbox:reply:42", callbacks)
        self.assertIn("admin:inbox:item:42:close", callbacks)
        self.assertIn("admin:inbox", callbacks)

    def test_make_parent_home_keyboard_with_traffic_light_linked(self):
        children = [
            {
                "link_id": 7,
                "child_label": "Анна",
                "link_status": "linked",
                "next_lesson_date": datetime.now(),
                "lesson_balance": 3,
                "overdue_homework_count": 0,
                "active_homework_count": 1,
            }
        ]
        kb = make_parent_home_keyboard(children)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        child_text = next(t for t in texts if "Анна" in t)
        self.assertTrue(child_text.startswith("🟢"), f"Expected green light, got: {child_text}")

    def test_make_parent_home_keyboard_with_traffic_light_waiting(self):
        children = [
            {
                "link_id": 8,
                "child_label": "Маша",
                "link_status": "waiting_link",
                "next_lesson_date": None,
                "lesson_balance": 0,
                "overdue_homework_count": 0,
                "active_homework_count": 0,
            }
        ]
        kb = make_parent_home_keyboard(children)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        child_text = next(t for t in texts if "Маша" in t)
        self.assertTrue(child_text.startswith("⏳"), f"Expected hourglass, got: {child_text}")


if __name__ == "__main__":
    unittest.main()
