import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from keyboards.inline import (
    admin_education_keyboard,
    admin_keyboard,
    admin_service_keyboard,
    admin_students_keyboard,
    make_admin_parent_card_keyboard,
    make_admin_parent_danger_keyboard,
    make_admin_parents_list_keyboard,
    make_admin_students_list_keyboard,
    make_admin_student_actions_keyboard,
    make_teacher_reply_keyboard,
    make_brand_tone_keyboard,
    make_admin_speech_styles_keyboard,
    make_admin_student_card_keyboard,
    make_contacts_keyboard,
    make_homework_delete_keyboard,
    make_homework_edit_content_keyboard,
    make_homework_edit_deadline_keyboard,
    make_homework_item_keyboard,
    make_homework_list_keyboard,
    make_homework_manage_actions_keyboard,
    make_lesson_delete_confirm_keyboard,
    make_lesson_followup_keyboard,
    make_lesson_presence_keyboard,
    make_profile_danger_keyboard,
    make_self_delete_review_keyboard,
    payment_keyboard,
    parent_profile_keyboard,
    profile_keyboard,
    make_reschedule_offer_keyboard,
)


class KeyboardHelpersTest(unittest.TestCase):
    def test_lesson_presence_keyboard_contains_expected_buttons(self):
        kb = make_lesson_presence_keyboard(42)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]

        self.assertIn("✅ Буду вовремя", texts)
        self.assertIn("⏱ Немного задержусь", texts)
        self.assertIn("✉️ Написать преподавателю", texts)
        self.assertIn("lesson_presence:on_time:42", callbacks)
        self.assertIn("lesson_presence:late:42", callbacks)
        self.assertIn("reply:lesson:42", callbacks)

    def test_contacts_keyboard_includes_vk_link_when_present(self):
        kb = make_contacts_keyboard(vk_call_url="https://vk.com/call/join/example")
        self.assertEqual(kb.inline_keyboard[0][0].text, "📞 VK Звонок")
        self.assertEqual(
            kb.inline_keyboard[0][0].url,
            "https://vk.com/call/join/example",
        )

    def test_contacts_keyboard_labels_google_meet_as_vpn_option(self):
        kb = make_contacts_keyboard(google_meet_url="https://meet.google.com/yic-ijmj-xbn")
        self.assertEqual(kb.inline_keyboard[0][0].text, "📹 Google Meet (VPN)")
        self.assertEqual(
            kb.inline_keyboard[0][0].url,
            "https://meet.google.com/yic-ijmj-xbn",
        )

    def test_payment_keyboard_groups_student_payment_actions(self):
        kb = payment_keyboard
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✉️ Сообщить об оплате", texts)
        self.assertIn("💳 Реквизиты", texts)
        self.assertIn("◀️ Главное меню", texts)
        self.assertIn("reply:payment", callbacks)
        self.assertIn("payment:requisites", callbacks)
        self.assertIn("back_to_menu", callbacks)

    def test_parent_profile_keyboard_stays_minimal_and_parent_specific(self):
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
        self.assertIn("back_to_menu", callbacks)

    def test_profile_danger_keyboard_exposes_delete_as_second_step(self):
        texts = [button.text for row in profile_keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in profile_keyboard.inline_keyboard for button in row if button.callback_data]
        danger_texts = [button.text for row in make_profile_danger_keyboard().inline_keyboard for button in row]
        danger_callbacks = [button.callback_data for row in make_profile_danger_keyboard().inline_keyboard for button in row if button.callback_data]
        review_texts = [button.text for row in make_self_delete_review_keyboard().inline_keyboard for button in row]

        self.assertIn("🛡 Опасные действия", texts)
        self.assertIn("profile:danger", callbacks)
        self.assertEqual(danger_texts, ["🗑 Удалить профиль", "◀️ Назад в профиль"])
        self.assertIn("profile:delete_me", danger_callbacks)
        self.assertEqual(review_texts, ["⚠️ Я понимаю последствия", "◀️ Назад"])

    def test_admin_students_list_keyboard_exposes_search_and_filters(self):
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

        self.assertIn("🔎 Поиск по имени", texts)
        self.assertIn("🧹 Сбросить", texts)
        self.assertIn("• Нужно внимание", texts)
        self.assertIn("• Баланс", texts)
        self.assertIn("✖️ Очистить поиск", texts)
        self.assertIn("admin:students:search", callbacks)
        self.assertIn("admin:students:filter:attention", callbacks)
        self.assertIn("admin:students:sort:balance", callbacks)
        self.assertIn("admin:students:search_clear", callbacks)

    def test_admin_parents_list_keyboard_exposes_search_and_card_navigation(self):
        parents = [
            {"telegram_id": 701, "full_name": "Мария Иванова"},
            {"telegram_id": 702, "full_name": "Елена Петрова"},
        ]
        kb = make_admin_parents_list_keyboard(
            parents,
            page=0,
            page_size=5,
            has_query=True,
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("🔎 Поиск по имени", texts)
        self.assertIn("✖️ Очистить поиск", texts)
        self.assertIn("admin:parents:search", callbacks)
        self.assertIn("admin:parents:search_clear", callbacks)
        self.assertIn("admin:parent_card:701:0", callbacks)
        self.assertIn("admin:parent_card:702:0", callbacks)

    def test_admin_student_card_keyboard_exposes_section_navigation(self):
        kb = make_admin_student_card_keyboard(
            telegram_id=555,
            page=2,
            lesson_format="offline",
            speech_style="formal",
            lesson_duration_minutes=120,
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("⚡ Действия", texts)
        self.assertIn("⚙️ Настройки", texts)
        self.assertIn("🛡 Опасные действия", texts)
        self.assertIn("admin:student_actions:555:2", callbacks)
        self.assertIn("admin:student_settings:555:2", callbacks)
        self.assertIn("admin:student_danger:555:2", callbacks)

    def test_admin_parent_card_and_danger_keyboards_expose_expected_actions(self):
        card_kb = make_admin_parent_card_keyboard(telegram_id=701, page=2)
        danger_kb = make_admin_parent_danger_keyboard(telegram_id=701, page=2)

        card_callbacks = [button.callback_data for row in card_kb.inline_keyboard for button in row if button.callback_data]
        danger_callbacks = [button.callback_data for row in danger_kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("admin:parent_preview_select:701:2", card_callbacks)
        self.assertIn("admin:parent_danger:701:2", card_callbacks)
        self.assertIn("admin:parents:page:2", card_callbacks)
        self.assertIn("admin:parent_deactivate_prompt:701:2", danger_callbacks)
        self.assertIn("admin:parent_delete_prompt:701:2", danger_callbacks)
        self.assertIn("admin:parent_card:701:2", danger_callbacks)

    def test_admin_student_actions_keyboard_exposes_quick_actions(self):
        kb = make_admin_student_actions_keyboard(telegram_id=555, page=2)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✉️ Написать", texts)
        self.assertIn("💰 Оплаты", texts)
        self.assertIn("➕ Урок", texts)
        self.assertIn("💳 Добавить оплату", texts)
        self.assertIn("📚 Задать ДЗ", texts)
        self.assertIn("admin:quick:add_lesson:555:2:actions", callbacks)
        self.assertIn("admin:quick:add_payment:555:2:actions", callbacks)
        self.assertIn("admin:quick:add_homework:555:2:actions", callbacks)
        self.assertIn("admin:write_to_student:555:2:actions", callbacks)

    def test_homework_item_keyboard_behaves_like_detail_actions(self):
        active_kb = make_homework_item_keyboard(42, "active")
        done_kb = make_homework_item_keyboard(42, "done")
        attachment_kb = make_homework_item_keyboard(42, "active", has_attachment=True)

        active_texts = [button.text for row in active_kb.inline_keyboard for button in row]
        active_callbacks = [button.callback_data for row in active_kb.inline_keyboard for button in row if button.callback_data]
        done_texts = [button.text for row in done_kb.inline_keyboard for button in row]
        done_callbacks = [button.callback_data for row in done_kb.inline_keyboard for button in row if button.callback_data]
        attachment_texts = [button.text for row in attachment_kb.inline_keyboard for button in row]
        attachment_callbacks = [button.callback_data for row in attachment_kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("✅ Отметить как выполненное", active_texts)
        self.assertIn("✉️ Написать по ДЗ", active_texts)
        self.assertIn("◀️ К списку ДЗ", active_texts)
        self.assertIn("hw_done:42", active_callbacks)
        self.assertIn("reply:homework:42", active_callbacks)
        self.assertIn("hw:active", active_callbacks)

        self.assertNotIn("✅ Отметить как выполненное", done_texts)
        self.assertIn("✉️ Написать по ДЗ", done_texts)
        self.assertIn("◀️ К списку ДЗ", done_texts)
        self.assertIn("reply:homework:42", done_callbacks)
        self.assertIn("hw:done", done_callbacks)

        self.assertIn("📎 Открыть файл", attachment_texts)
        self.assertIn("hw:file:42:active", attachment_callbacks)

    def test_teacher_reply_keyboard_supports_general_context(self):
        kb = make_teacher_reply_keyboard("general")
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertEqual(texts, ["✉️ Ответить преподавателю"])
        self.assertEqual(callbacks, ["reply:general"])

    def test_lesson_followup_keyboard_contains_all_teacher_actions(self):
        kb = make_lesson_followup_keyboard(42, 555)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertEqual(
            texts,
            ["💬 Комментарий по уроку", "📖 Сохранить закладку", "🚫 Без учебника/книги"],
        )
        self.assertIn("lesson_followup:comment:42", callbacks)
        self.assertIn("lesson_followup:bookmark:42:555", callbacks)
        self.assertIn("lesson_followup:no_material:42:555", callbacks)

    def test_lesson_delete_keyboard_offers_calendar_option_when_linked(self):
        kb = make_lesson_delete_confirm_keyboard(42, can_delete_from_calendar=True)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("🗑 Удалить только из бота", texts)
        self.assertIn("🗓 Удалить из бота и Calendar", texts)
        self.assertIn("lesson_delete:42:db", callbacks)
        self.assertIn("lesson_delete:42:calendar", callbacks)

    def test_admin_home_keyboard_contains_only_section_navigation(self):
        texts = [button.text for row in admin_keyboard.inline_keyboard for button in row]

        self.assertEqual(
            texts,
            [
                "👥 Ученики",
                "📚 Учебный процесс",
                "📢 Рассылка",
                "⚙️ Сервис",
                "🧪 Просмотр ролей",
                "◀️ Главное меню",
            ],
        )

    def test_admin_section_keyboards_are_grouped_by_context(self):
        student_texts = [button.text for row in admin_students_keyboard.inline_keyboard for button in row]
        education_texts = [button.text for row in admin_education_keyboard.inline_keyboard for button in row]
        service_texts = [button.text for row in admin_service_keyboard.inline_keyboard for button in row]

        self.assertIn("📋 Список учеников", student_texts)
        self.assertIn("👨‍👩‍👧 Родители", student_texts)
        self.assertIn("👤 Добавить ученика", student_texts)
        self.assertIn("🗣 Обращение", student_texts)
        self.assertIn("🗑 Деактивировать", student_texts)
        self.assertIn("💀 Полный сброс", student_texts)
        self.assertIn("➕ Добавить занятие", education_texts)
        self.assertIn("🗑 Удалить занятие", education_texts)
        self.assertIn("📚 Задать ДЗ", education_texts)
        self.assertIn("📋 Активные ДЗ", education_texts)
        self.assertIn("📊 Мониторинг", service_texts)
        self.assertIn("🧠 Контекст и проект", service_texts)

    def test_admin_speech_styles_keyboard_shows_toggle_targets(self):
        kb = make_admin_speech_styles_keyboard(
            [
                {"telegram_id": 1, "full_name": "Анна", "speech_style": "formal"},
                {"telegram_id": 2, "full_name": "Илья", "speech_style": "informal"},
            ]
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertTrue(any("переключить на ты" in text for text in texts))
        self.assertTrue(any("переключить на Вы" in text for text in texts))
        self.assertIn("admin:speech_style_toggle:1:informal", callbacks)
        self.assertIn("admin:speech_style_toggle:2:formal", callbacks)

    def test_reschedule_offer_keyboard_contains_slots_and_reply_button(self):
        kb = make_reschedule_offer_keyboard(
            [("202604041400", "04.04 14:00"), ("202604051130", "05.04 11:30")]
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("🗓 04.04 14:00", texts)
        self.assertIn("🗓 05.04 11:30", texts)
        self.assertIn("✉️ Написать преподавателю", texts)
        self.assertIn("reschedule_pick:202604041400", callbacks)

    def test_brand_tone_keyboard_marks_current_value(self):
        kb = make_brand_tone_keyboard("warm")
        texts = [button.text for row in kb.inline_keyboard for button in row]

        self.assertIn("• Тёплый", texts)

    def test_homework_list_keyboard_opens_detail_without_title_cut(self):
        kb = make_homework_list_keyboard(
            [{"id": 1, "title": "", "description": "Очень длинное домашнее задание"}],
            "active",
        )
        texts = [button.text for row in kb.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]

        self.assertIn("📝 1. Открыть задание", texts)
        self.assertIn("hw:view:1:active", callbacks)
        self.assertNotIn("…", "".join(texts))

    def test_admin_homework_manage_keyboards_expose_edit_flow(self):
        list_kb = make_homework_delete_keyboard(
            [{"id": 7, "full_name": "Иван Петров", "deadline": datetime(2026, 4, 10)}]
        )
        actions_kb = make_homework_manage_actions_keyboard(7)
        content_kb = make_homework_edit_content_keyboard()
        deadline_kb = make_homework_edit_deadline_keyboard("10.04.2026")

        list_callbacks = [button.callback_data for row in list_kb.inline_keyboard for button in row if button.callback_data]
        actions_texts = [button.text for row in actions_kb.inline_keyboard for button in row]
        actions_callbacks = [button.callback_data for row in actions_kb.inline_keyboard for button in row if button.callback_data]
        content_texts = [button.text for row in content_kb.inline_keyboard for button in row]
        deadline_texts = [button.text for row in deadline_kb.inline_keyboard for button in row]

        self.assertIn("admin:homework_manage:7", list_callbacks)
        self.assertIn("✏️ Редактировать", actions_texts)
        self.assertIn("🗑 Удалить", actions_texts)
        self.assertIn("hw_edit_start:7", actions_callbacks)
        self.assertIn("hw_delete_confirm:7", actions_callbacks)
        self.assertIn("⏭ Оставить текущий текст и файл", content_texts)
        self.assertIn("⏭ Оставить дедлайн 10.04.2026", deadline_texts)


if __name__ == "__main__":
    unittest.main()
