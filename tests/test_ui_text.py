import sys
from datetime import date, datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.ui_text import (
    admin_broadcast_recipients_text,
    build_action_result_text,
    build_admin_dashboard_text,
    build_admin_homework_description_prompt,
    build_admin_parent_card_text,
    build_admin_parents_page_text,
    build_admin_students_page_text,
    build_admin_student_card_text,
    build_broadcast_preview_text,
    build_admin_homework_list_text,
    build_contacts_text,
    build_first_lesson_payment_invite_text,
    build_homework_text,
    build_materials_text,
    build_schedule_text,
    build_requisites_text,
    build_study_plan_text,
    build_teacher_bookmark_reminder_text,
    build_teacher_lesson_followup_text,
    student_freshness_label,
)


class UITextTest(unittest.TestCase):
    def test_contacts_text_hides_raw_urls(self):
        info = {
            "contacts": {
                "phone": "+7 900 000-00-00",
                "telegram": "@teacher",
                "vk_call": "https://vk.com/call/join/example",
                "google_meet": "https://meet.google.com/example",
                "address": "ул. Пушкина, дом Колотушкина",
            }
        }

        text = build_contacts_text(info, show_address=True)

        self.assertIn("Контакты преподавателя", text)
        self.assertIn("Google Meet", text)
        self.assertIn("Очные занятия", text)
        self.assertNotIn("https://", text)

    def test_requisites_text_hides_raw_booking_links(self):
        text = build_requisites_text(
            {
                "rate": "3000 ₽ / 60 минут",
                "card": "1234 5678 9000 1111",
                "sbp": "+7 900 000-00-00",
            }
        )

        self.assertIn("Реквизиты и стоимость", text)
        self.assertIn("Сообщить об оплате", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)

    def test_materials_text_handles_present_and_missing_url(self):
        with_url = build_materials_text(materials_url="https://filen.io/example")
        without_url = build_materials_text()
        with_site = build_materials_text(website_url="https://teacher.example")

        self.assertIn("Учебные материалы", with_url)
        self.assertNotIn("https://filen.io", with_url)  # link is on the button, not in text
        self.assertIn("Учебные материалы", without_url)
        self.assertIn("Напишите преподавателю", without_url)
        self.assertIn("сайте преподавателя", with_site)

    def test_first_lesson_payment_invite_text_includes_thanks_and_requisites(self):
        text = build_first_lesson_payment_invite_text(
            "Анна",
            {"rate": "3000 ₽ / 90 минут", "card": "1234"},
            speech_style="formal",
        )

        self.assertIn("первый урок", text)
        self.assertIn("Анна", text)
        self.assertIn("Реквизиты и стоимость", text)
        self.assertIn("Сообщить об оплате", text)
        # "formal" form addresses the student with «оплатите», not «оплати».
        self.assertIn("оплатите", text)

    def test_first_lesson_payment_invite_text_uses_informal_form_when_requested(self):
        text = build_first_lesson_payment_invite_text(
            "Аня",
            {"card": "1234"},
            speech_style="informal",
        )

        self.assertIn("оплати", text)
        self.assertNotIn("оплатите", text)

    def test_requisites_text_uses_exact_pricing_context(self):
        text = build_requisites_text(
            {"rate": "3000 ₽ / 60 минут", "card": "1234"},
            {
                "group_size": 2,
                "duration_minutes": 90,
                "rate": {"amount": 5000, "currency": "RUB", "group_size": 2, "duration_minutes": 90},
            },
        )

        self.assertIn("5000 ₽ / 90 минут", text)
        self.assertIn("Формат: <b>2 уч.</b>", text)
        self.assertNotIn("3000 ₽ / 60 минут", text)

    def test_requisites_text_avoids_wrong_price_when_no_exact_rate(self):
        text = build_requisites_text(
            {"rate": "3000 ₽ / 60 минут", "card": "1234"},
            {"group_size": 3, "duration_minutes": 75, "rate": None},
        )

        self.assertIn("Для формата <b>3 уч. · 75 мин</b> стоимость уточните у преподавателя.", text)
        self.assertNotIn("3000 ₽ / 60 минут", text)

    def test_study_plan_text_shows_plan_checklist_and_progress(self):
        text = build_study_plan_text(
            {"full_name": "Анна Иванова"},
            {"summary": "• Повторяем времена\n• Готовим устную практику"},
            {"lesson_date": datetime(2026, 4, 8, 16, 0)},
            [{"id": 1}],
            [
                {"title": "Открыть активное ДЗ", "status": "done"},
                {"title": "Подготовить вопрос", "status": "pending"},
            ],
            pair={"title": "Анна + Полина"},
        )

        self.assertIn("Учебный план", text)
        self.assertIn("Анна Иванова", text)
        self.assertIn("Пара: <b>Анна + Полина</b>", text)
        self.assertIn("Ближайший урок: <b>08.04.2026 16:00</b>", text)
        self.assertIn("Подготовка: <b>1/2</b>", text)
        self.assertIn("✅ Открыть активное ДЗ", text)
        self.assertIn("☐ Подготовить вопрос", text)

    def test_action_result_text_keeps_warm_service_structure(self):
        text = build_action_result_text(
            "Сообщение отправлено",
            "Преподаватель увидит его в ближайшее время.",
            next_step="Можно вернуться в меню или продолжить с текущего экрана.",
        )

        self.assertIn("Сообщение отправлено", text)
        self.assertIn("Преподаватель увидит его", text)
        self.assertIn("Можно вернуться", text)

    def test_admin_dashboard_text_accepts_sync_report_dict(self):
        text = build_admin_dashboard_text(
            {
                "active_students": 8,
                "lessons_today": 3,
                "unpaid_students": 2,
                "pending_freezes": 1,
                "active_homework": 5,
                "students_without_upcoming_lessons": 4,
            },
            {"scheduler": "running"},
            {"synced_at_local": "01.04.2026 14:30"},
        )

        self.assertIn("Активных учеников: <b>8</b>", text)
        self.assertIn("Уроков сегодня: <b>3</b>", text)
        self.assertIn("Последний sync: <b>01.04.2026 14:30</b>", text)
        self.assertIn("Нужно внимание", text)
        self.assertIn("Система", text)
        self.assertIn("Выберите раздел ниже.", text)
        self.assertIn("⏱ Scheduler: <b>running</b>", text)

    def test_schedule_text_keeps_next_lesson_and_total_count(self):
        text = build_schedule_text(
            [
                {"lesson_date": datetime(2026, 4, 5, 14, 0)},
                {"lesson_date": datetime(2026, 4, 8, 16, 30)},
            ]
        )

        self.assertIn("📅 <b>Расписание</b>", text)
        self.assertIn("Ближайший урок: <b>05.04.2026 14:00</b>", text)
        self.assertIn("Всего в расписании: <b>2</b>", text)
        self.assertIn("• <b>05.04.2026 14:00</b>", text)
        self.assertIn("• <b>08.04.2026 16:30</b>", text)

    def test_student_freshness_switches_after_calendar_month(self):
        first_lesson = datetime(2026, 3, 31, 15, 0)

        self.assertEqual(
            student_freshness_label(first_lesson, today=date(2026, 4, 29)),
            "новый",
        )
        self.assertEqual(
            student_freshness_label(first_lesson, today=date(2026, 4, 30)),
            "старый",
        )

    def test_admin_students_page_text_includes_sorting_context(self):
        text = build_admin_students_page_text(
            [
                {
                    "full_name": "Анна Иванова",
                    "lesson_format": "online",
                    "language": "English",
                    "level": "B1",
                    "speech_style": "formal",
                    "lesson_balance": 0,
                    "next_lesson_date": None,
                    "first_lesson_date": datetime(2026, 4, 1, 10, 0),
                }
            ],
            page=0,
            page_size=5,
            filter_label="Нужно внимание",
            sort_label="По балансу",
            total_count=3,
        )

        self.assertIn("Фильтр: <b>Нужно внимание</b>", text)
        self.assertIn("Сортировка: <b>По балансу</b>", text)
        self.assertIn("Показано: <b>1</b> из 3", text)

    def test_homework_text_prefers_description_over_empty_title(self):
        text = build_homework_text(
            [
                {
                    "title": "",
                    "description": "3. Le vocabulaire.\n<a href=\"https://example.com\">Apprenez ici</a>",
                    "deadline": datetime(2026, 4, 5),
                }
            ],
            "active",
        )

        self.assertIn("3. Le vocabulaire.", text)
        self.assertIn("<a href=\"https://example.com\">Apprenez ici</a>", text)
        self.assertNotIn("L...", text)

    def test_admin_homework_list_text_shows_full_description_without_preview_cut(self):
        text = build_admin_homework_list_text(
            [
                {
                    "full_name": "Наталья Пименова",
                    "title": "",
                    "description": "3. Le vocabulaire.\n<a href=\"https://example.com\">Apprenez ici</a>",
                    "deadline": datetime(2026, 4, 5),
                }
            ]
        )

        self.assertIn("3. Le vocabulaire.", text)
        self.assertIn("<a href=\"https://example.com\">Apprenez ici</a>", text)
        self.assertNotIn("L...", text)

    def test_admin_student_card_text_includes_lesson_duration(self):
        text = build_admin_student_card_text(
            {
                "full_name": "Иван Петров",
                "first_lesson_date": datetime(2026, 3, 1, 14, 0),
                "lesson_format": "online",
                "speech_style": "formal",
                "language": "Английский",
                "level": "B1",
                "lesson_reminders": "enabled",
                "telegram_id": 555,
                "lesson_duration_minutes": 120,
            },
            balance=4,
            next_lesson=datetime(2026, 4, 5, 14, 0),
        )

        self.assertIn("⏱ Длительность урока: <b>120 мин</b>", text)

    def test_admin_parents_page_text_includes_search_and_counts(self):
        text = build_admin_parents_page_text(
            [
                {
                    "telegram_id": 701,
                    "full_name": "Мария Иванова",
                    "children_count": 2,
                    "linked_children_count": 1,
                }
            ],
            page=0,
            page_size=5,
            query="Мария",
            total_count=2,
        )

        self.assertIn("Список родителей", text)
        self.assertIn("Показано: <b>1</b> из 2", text)
        self.assertIn("Поиск: <b>Мария</b>", text)
        self.assertIn("Мария Иванова", text)
        self.assertIn("Дети: <b>1</b> привязано из <b>2</b>", text)

    def test_admin_parent_card_text_lists_children_and_payment_stats(self):
        text = build_admin_parent_card_text(
            {
                "telegram_id": 701,
                "full_name": "Мария Иванова",
                "username": "maria_parent",
                "is_active": True,
            },
            [
                {"child_label": "Анна Иванова", "link_status": "linked"},
                {"child_label": "Максим Иванов", "link_status": "waiting_link"},
            ],
            payments_as_payer=3,
        )

        self.assertIn("Мария Иванова", text)
        self.assertIn("@maria_parent", text)
        self.assertIn("Оплат как плательщик: <b>3</b>", text)
        self.assertIn("Анна Иванова", text)
        self.assertIn("привязан", text)
        self.assertIn("ждёт привязки", text)

    def test_teacher_followup_and_bookmark_texts_cover_saved_state(self):
        followup_text = build_teacher_lesson_followup_text(
            {
                "full_name": "Георгий Мартынов",
                "lesson_date": datetime(2026, 4, 4, 14, 0),
                "lesson_format": "offline",
            }
        )
        reminder_text = build_teacher_bookmark_reminder_text(
            {
                "full_name": "Георгий Мартынов",
                "lesson_date": datetime(2026, 4, 5, 14, 0),
                "lesson_format": "offline",
                "current_bookmark_state": "saved",
                "current_bookmark_text": "Cosmopolite 1, page 69.",
            }
        )

        self.assertIn("Урок завершился", followup_text)
        self.assertIn("Георгий Мартынов", followup_text)
        self.assertIn("за 1 час", reminder_text)
        self.assertIn("Cosmopolite 1, page 69.", reminder_text)

    def test_broadcast_preview_and_recipient_texts_keep_message_shape(self):
        preview = build_broadcast_preview_text(
            "⚠️ <b>Внимание</b>\n\nСегодняшнего урока не будет."
        )
        recipients = admin_broadcast_recipients_text(
            "<b>⚠️ Внимание</b>\n\nСегодняшнего урока не будет.",
            selected_count=2,
            total_count=5,
        )

        self.assertIn("Предпросмотр рассылки", preview)
        self.assertIn("Сегодняшнего урока не будет.", preview)
        self.assertIn("Выберите получателей рассылки", recipients)
        self.assertIn("Выбрано: <b>2</b> из 5", recipients)
        self.assertIn("⚠️ Внимание", recipients)
        self.assertNotIn("<b>Внимание</b>", recipients)

    def test_admin_homework_description_prompt_shows_stats_and_hint(self):
        text = build_admin_homework_description_prompt(
            student_name="Наталья Пименова",
            recent_mentions=[
                {
                    "material_title": "Le cahier d’activités — Cosmopolite 1",
                    "page_from": 44,
                    "page_to": 45,
                    "exercise_label": "Ex. 1-4",
                    "homework_created_at": datetime(2026, 4, 4, 19, 30),
                },
                {
                    "material_title": "Le livre d’étudiant",
                    "page_from": 69,
                    "page_to": None,
                    "exercise_label": "Ex. 2(c)",
                    "homework_created_at": datetime(2026, 4, 2, 19, 30),
                },
            ],
            top_materials=[
                {"material_title": "Cosmopolite 1", "mentions_count": 3},
                {"material_title": "Le livre d’étudiant", "mentions_count": 1},
            ],
            latest_mention={
                "material_title": "Le cahier d’activités — Cosmopolite 1",
                "material_key": "cosmopolite 1",
                "page_from": 44,
                "page_to": 45,
            },
            has_homework_history=True,
        )

        self.assertIn("По прошлым ДЗ", text)
        self.assertIn("Чаще всего", text)
        self.assertIn("Подсказка", text)
        self.assertIn("Le cahier d’activités", text)
        self.assertIn("Cosmopolite 1", text)
        self.assertIn("стр. 44-45", text)
        self.assertIn("Отправьте <b>текст домашнего задания</b>", text)
        self.assertIn("PDF/DOCX", text)

    def test_admin_homework_description_prompt_falls_back_when_history_has_no_mentions(self):
        text = build_admin_homework_description_prompt(
            student_name="Наталья Пименова",
            recent_mentions=[],
            top_materials=[],
            latest_mention=None,
            has_homework_history=True,
        )

        self.assertIn("статистика по учебникам или книгам", text.lower())
        self.assertIn("Отправьте <b>текст домашнего задания</b>", text)
        self.assertIn("PDF/DOCX", text)


if __name__ == "__main__":
    unittest.main()
