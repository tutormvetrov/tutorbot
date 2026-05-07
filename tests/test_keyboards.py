"""Tests for dynamic keyboard generation logic.

Only tests that verify parameterized behavior are kept here.
Static layout assertions (button labels, exact ordering) were removed
because they break on every UI change and catch no real bugs.
"""
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from datetime import datetime

from keyboards.inline import (
    make_admin_education_keyboard,
    make_admin_inbox_keyboard,
    make_admin_inbox_item_keyboard,
    make_contacts_keyboard,
    make_homework_item_keyboard,
    make_lesson_delete_confirm_keyboard,
    make_lesson_followup_keyboard,
    make_lesson_presence_keyboard,
    make_materials_keyboard,
    make_parent_home_keyboard,
    make_pricing_rates_keyboard,
    make_schedule_keyboard,
    make_study_plan_keyboard,
    make_tariff_picker_keyboard,
)


class DynamicKeyboardTest(unittest.TestCase):
    def test_schedule_keyboard_exposes_calendar_url(self):
        kb = make_schedule_keyboard("https://calendar.google.com/example")
        urls = [button.url for row in kb.inline_keyboard for button in row if getattr(button, "url", None)]
        self.assertIn("https://calendar.google.com/example", urls)

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
        self.assertEqual(urls[0], "https://docs.google.com/c")

    def test_materials_keyboard_falls_back_to_website_when_empty(self):
        kb = make_materials_keyboard([], website_url="https://teacher.example")
        urls = [button.url for row in kb.inline_keyboard for button in row if getattr(button, "url", None)]
        self.assertEqual(urls, ["https://teacher.example"])

    def test_study_plan_keyboard_exposes_pdf_and_checklist_toggles(self):
        kb = make_study_plan_keyboard(
            {"id": 7},
            [
                {"id": 1, "title": "Открыть ДЗ", "status": "pending"},
                {"id": 2, "title": "Повторить материал", "status": "done"},
            ],
        )
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("study_plan:file:7", callbacks)
        self.assertIn("study_plan:toggle:1", callbacks)
        self.assertIn("study_plan:toggle:2", callbacks)

    def test_pricing_rates_keyboard_supports_arbitrary_group_size(self):
        kb = make_pricing_rates_keyboard([
            {"group_size": 3, "duration_minutes": 75, "amount": 6000, "currency": "RUB"}
        ])
        texts = [button.text for row in kb.inline_keyboard for button in row]
        self.assertIn("3 уч. · 75 мин · 6000 RUB", texts)

    def test_pricing_rates_keyboard_shows_label(self):
        kb = make_pricing_rates_keyboard([
            {"id": 1, "label": "Инд старый", "group_size": 1, "duration_minutes": 90, "amount": 2500, "currency": "RUB"}
        ])
        texts = [button.text for row in kb.inline_keyboard for button in row]
        self.assertTrue(any("Инд старый" in t for t in texts))

    def test_tariff_picker_marks_current_rate(self):
        rates = [
            {"id": 1, "label": "Инд", "group_size": 1, "duration_minutes": 90, "amount": 2500, "currency": "RUB"},
            {"id": 2, "label": "Пара", "group_size": 2, "duration_minutes": 90, "amount": 3500, "currency": "RUB"},
        ]
        kb = make_tariff_picker_keyboard(123, 0, rates, current_rate_id=1)
        texts = [button.text for row in kb.inline_keyboard for button in row]
        self.assertTrue(any("Инд" in t and "✓" in t for t in texts))
        self.assertTrue(any("Пара" in t and "✓" not in t for t in texts))

    def test_tariff_picker_shows_remove_button_when_assigned(self):
        rates = [{"id": 1, "label": "Тест", "group_size": 1, "duration_minutes": 90, "amount": 2500, "currency": "RUB"}]
        kb = make_tariff_picker_keyboard(123, 0, rates, current_rate_id=1)
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("admin:assign_tariff:123:0:0", callbacks)

    def test_lesson_presence_keyboard_contains_expected_callbacks(self):
        kb = make_lesson_presence_keyboard(42)
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("lesson_presence:on_time:42", callbacks)
        self.assertIn("lesson_presence:late:42", callbacks)
        self.assertIn("reply:lesson:42", callbacks)

    def test_contacts_keyboard_includes_provided_urls(self):
        kb = make_contacts_keyboard(
            vk_call_url="https://vk.com/call/join/example",
            google_meet_url="https://meet.google.com/example",
        )
        urls = [button.url for row in kb.inline_keyboard for button in row if getattr(button, "url", None)]
        self.assertIn("https://vk.com/call/join/example", urls)
        self.assertIn("https://meet.google.com/example", urls)

    def test_homework_item_keyboard_shows_attachment_when_available(self):
        kb_no_att = make_homework_item_keyboard(42, "active")
        kb_att = make_homework_item_keyboard(42, "active", has_attachment=True)
        callbacks_no_att = [button.callback_data for row in kb_no_att.inline_keyboard for button in row if button.callback_data]
        callbacks_att = [button.callback_data for row in kb_att.inline_keyboard for button in row if button.callback_data]
        self.assertNotIn("hw:file:42:active", callbacks_no_att)
        self.assertIn("hw:file:42:active", callbacks_att)

    def test_lesson_followup_keyboard_has_core_callbacks(self):
        kb = make_lesson_followup_keyboard(42, 555)
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("lesson_followup:comment:42", callbacks)
        self.assertIn("lesson_followup:bookmark:42:555", callbacks)
        self.assertIn("lesson_followup:no_material:42:555", callbacks)

    def test_lesson_delete_keyboard_shows_calendar_option_conditionally(self):
        kb_with = make_lesson_delete_confirm_keyboard(42, can_delete_from_calendar=True)
        kb_without = make_lesson_delete_confirm_keyboard(42, can_delete_from_calendar=False)
        callbacks_with = [button.callback_data for row in kb_with.inline_keyboard for button in row if button.callback_data]
        callbacks_without = [button.callback_data for row in kb_without.inline_keyboard for button in row if button.callback_data]
        self.assertIn("lesson_delete:42:calendar", callbacks_with)
        self.assertNotIn("lesson_delete:42:calendar", callbacks_without)

    def test_education_keyboard_freeze_count(self):
        kb_zero = make_admin_education_keyboard(0)
        kb_three = make_admin_education_keyboard(3)
        texts_zero = [button.text for row in kb_zero.inline_keyboard for button in row]
        texts_three = [button.text for row in kb_three.inline_keyboard for button in row]
        self.assertIn("❄️ Заявки на заморозку", texts_zero)
        self.assertIn("❄️ Заявки на заморозку (3)", texts_three)


class AdminInboxKeyboardTest(unittest.TestCase):
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
        callbacks = [button.callback_data for row in kb.inline_keyboard for button in row if button.callback_data]
        self.assertIn("admin:inbox:reply:42", callbacks)
        self.assertIn("admin:inbox:item:42:close", callbacks)
        self.assertIn("admin:inbox", callbacks)

    def test_parent_home_traffic_light_linked(self):
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
        self.assertTrue(child_text.startswith("🟢"))

    def test_parent_home_traffic_light_waiting(self):
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
        self.assertTrue(child_text.startswith("⏳"))


if __name__ == "__main__":
    unittest.main()
