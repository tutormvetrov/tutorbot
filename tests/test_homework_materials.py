import sys
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.db_api.homework import DatabaseHomeworkMixin
from utils.homework_materials import (
    build_next_homework_hint,
    material_progress_label,
    parse_homework_material_mentions,
)


class HomeworkMaterialsParserTest(unittest.TestCase):
    def test_parser_extracts_numbered_textbooks_pages_and_exercises(self):
        html = (
            "1. Le livre d’étudiant.<br>"
            "Ex. 2(c) — page 69.<br><br>"
            "2. Le cahier d’activités. Cosmopolite 1.<br>"
            "Ex. 1-4 — pages 44-45.<br><br>"
            "3. Le vocabulaire.<br>"
            "<a href=\"https://example.com\">Apprenez ici</a>"
        )

        mentions = parse_homework_material_mentions(html)

        self.assertEqual(len(mentions), 3)
        titles = [item["material_title"] for item in mentions]
        self.assertTrue(any("Le livre d’étudiant" in title for title in titles))
        self.assertTrue(any("Le cahier d’activités" in title for title in titles))
        self.assertTrue(any("Le vocabulaire" in title for title in titles))
        self.assertTrue(any("Cosmopolite 1" in title for title in titles))
        self.assertEqual(mentions[0]["page_from"], 69)
        self.assertEqual(mentions[0]["exercise_label"], "Ex. 2(c)")
        self.assertEqual(mentions[1]["page_from"], 44)
        self.assertEqual(mentions[1]["page_to"], 45)
        self.assertEqual(mentions[1]["exercise_label"], "Ex. 1-4")
        self.assertEqual(mentions[2]["material_kind"], "vocabulary")
        self.assertIn("https://example.com", mentions[2]["raw_fragment"])

    def test_parser_extracts_vocabulary_resources_with_links(self):
        html = (
            "3. Le vocabulaire.<br>"
            "<a href=\"https://knowt.com\">Apprenez de nouvelles expressions ici</a><br><br>"
            "4. Flashcards on Quizlet."
        )

        mentions = parse_homework_material_mentions(html)

        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["material_title"], "Le vocabulaire")
        self.assertEqual(mentions[0]["material_kind"], "vocabulary")
        self.assertIn("https://knowt.com", mentions[0]["raw_fragment"])

    def test_hint_generation_covers_page_unit_and_title_only_cases(self):
        page_hint = build_next_homework_hint(
            {
                "material_title": "Cosmopolite 1",
                "material_key": "cosmopolite 1",
                "page_from": 44,
                "page_to": 45,
            },
            recent_mentions=[
                {"material_key": "cosmopolite 1"},
                {"material_key": "cosmopolite 1"},
                {"material_key": "harry potter"},
            ],
        )
        unit_hint = build_next_homework_hint(
            {
                "material_title": "Speakout B2",
                "material_key": "speakout b2",
                "unit_label": "Unit 5",
            }
        )
        title_only_hint = build_next_homework_hint(
            {
                "material_title": "Harry Potter",
                "material_key": "harry potter",
            }
        )

        self.assertIn("доминирует Cosmopolite 1", page_hint)
        self.assertIn("стр. 44-45", page_hint)
        self.assertIn("после Unit 5", unit_hint)
        self.assertIn("логичнее всего продолжать его", title_only_hint)

    def test_material_progress_label_combines_pages_and_exercise(self):
        label = material_progress_label(
            {
                "page_from": 69,
                "page_to": None,
                "exercise_label": "Ex. 2(c)",
            }
        )

        self.assertEqual(label, "стр. 69 · Ex. 2(c)")


class HomeworkDbMixinTest(unittest.IsolatedAsyncioTestCase):
    async def test_add_homework_saves_mentions_and_marks_homework_as_parsed(self):
        class FakeDB(DatabaseHomeworkMixin):
            def __init__(self):
                self.executed = []

            async def execute(self, command, *args, **kwargs):
                self.executed.append((command, args, kwargs))
                if kwargs.get("fetchval"):
                    return 77
                if kwargs.get("fetch"):
                    return []
                if kwargs.get("fetchrow"):
                    return None
                return "OK"

        db = FakeDB()
        homework_id = await db.add_homework(
            555,
            "",
            "Cosmopolite 1. Ex. 1-4 — pages 44-45.",
            datetime(2026, 4, 5),
        )

        self.assertEqual(homework_id, 77)
        commands = [command for command, _, _ in db.executed]
        self.assertTrue(any("INSERT INTO homework_material_mentions" in command for command in commands))
        self.assertTrue(any("DELETE FROM homework_material_mentions" in command for command in commands))
        self.assertTrue(any("UPDATE homework SET materials_parsed_at = NOW()" in command for command in commands))

    async def test_update_homework_refreshes_mentions_and_attachment_fields(self):
        class FakeDB(DatabaseHomeworkMixin):
            def __init__(self):
                self.executed = []

            async def execute(self, command, *args, **kwargs):
                self.executed.append((command, args, kwargs))
                if kwargs.get("fetch"):
                    return []
                if kwargs.get("fetchval"):
                    return None
                if kwargs.get("fetchrow"):
                    return None
                return "OK"

        db = FakeDB()
        await db.update_homework(
            77,
            555,
            "",
            "Cosmopolite 1. Ex. 2 — page 46.",
            datetime(2026, 4, 6),
            attachment={
                "file_id": "doc-file-id",
                "file_unique_id": "doc-unique-id",
                "file_name": "lesson.docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        )

        commands = [command for command, _, _ in db.executed]
        self.assertTrue(any("UPDATE homework" in command for command in commands))
        self.assertTrue(any("DELETE FROM homework_material_mentions" in command for command in commands))
        self.assertTrue(any("INSERT INTO homework_material_mentions" in command for command in commands))

    async def test_backfill_marks_rows_as_parsed_even_without_mentions(self):
        class FakeDB(DatabaseHomeworkMixin):
            def __init__(self):
                self.executed = []

            async def execute(self, command, *args, **kwargs):
                self.executed.append((command, args, kwargs))
                if kwargs.get("fetch"):
                    if "materials_parsed_at IS NULL" in command:
                        return [
                            {"id": 81, "student_id": 555, "description": "Knowt flashcards only"},
                        ]
                    return []
                if kwargs.get("fetchval"):
                    return None
                if kwargs.get("fetchrow"):
                    return None
                return "OK"

        db = FakeDB()
        count = await db.backfill_homework_materials_for_student(555)

        self.assertEqual(count, 1)
        commands = [command for command, _, _ in db.executed]
        self.assertFalse(any("INSERT INTO homework_material_mentions" in command for command in commands))
        self.assertTrue(any("UPDATE homework SET materials_parsed_at = NOW()" in command for command in commands))

    async def test_template_materials_query_selects_top_materials_with_latest_mentions(self):
        class FakeDB(DatabaseHomeworkMixin):
            def __init__(self):
                self.executed = []

            async def execute(self, command, *args, **kwargs):
                self.executed.append((command, args, kwargs))
                return []

        db = FakeDB()

        await db.get_homework_template_materials(555, limit=3)

        command, args, kwargs = db.executed[0]
        self.assertIn("ROW_NUMBER() OVER", command)
        self.assertIn("mentions_count", command)
        self.assertIn("raw_fragment", command)
        self.assertIn("ORDER BY mentions_count DESC", command)
        self.assertEqual(args, (555, 3))
        self.assertTrue(kwargs.get("fetch"))


if __name__ == "__main__":
    unittest.main()
