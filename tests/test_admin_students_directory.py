import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from handlers.users.admin_sections.students import _sort_admin_students


class AdminStudentsDirectoryLogicTest(unittest.TestCase):
    def setUp(self):
        self.students = [
            {
                "telegram_id": 1,
                "full_name": "Борис Петров",
                "lesson_balance": 4,
                "next_lesson_date": datetime(2026, 4, 12, 18, 0),
            },
            {
                "telegram_id": 2,
                "full_name": "Анна Иванова",
                "lesson_balance": 0,
                "next_lesson_date": datetime(2026, 4, 10, 11, 0),
            },
            {
                "telegram_id": 3,
                "full_name": "Вера Соколова",
                "lesson_balance": 2,
                "next_lesson_date": None,
            },
        ]

    def test_sort_by_name_orders_alphabetically(self):
        ordered = _sort_admin_students(self.students, "name")

        self.assertEqual([item["telegram_id"] for item in ordered], [2, 1, 3])

    def test_sort_by_balance_surfaces_low_balance_first(self):
        ordered = _sort_admin_students(self.students, "balance")

        self.assertEqual([item["telegram_id"] for item in ordered], [2, 3, 1])

    def test_sort_by_lesson_puts_students_without_upcoming_lesson_last(self):
        ordered = _sort_admin_students(self.students, "lesson")

        self.assertEqual([item["telegram_id"] for item in ordered], [2, 1, 3])


if __name__ == "__main__":
    unittest.main()
