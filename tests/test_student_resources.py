"""Tests for student_resources: provider detection, UI rendering, keyboards."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keyboards.inline import (
    make_admin_global_resources_keyboard,
    make_admin_student_resources_keyboard,
    make_materials_keyboard,
)
from utils.resource_provider import (
    PROVIDER_FILEN,
    PROVIDER_GDOCS,
    PROVIDER_GDRIVE,
    PROVIDER_OTHER,
    detect_provider,
    provider_emoji,
    provider_label,
)
from utils.ui_text import (
    build_admin_global_resources_text,
    build_admin_student_resources_text,
    build_materials_text,
)


class DetectProviderTest(unittest.TestCase):
    def test_google_docs(self):
        self.assertEqual(detect_provider("https://docs.google.com/document/d/abc"), PROVIDER_GDOCS)

    def test_google_drive(self):
        self.assertEqual(detect_provider("https://drive.google.com/folder/xyz"), PROVIDER_GDRIVE)

    def test_filen_io(self):
        self.assertEqual(detect_provider("https://filen.io/d/123"), PROVIDER_FILEN)
        self.assertEqual(detect_provider("https://app.filen.io/d/123"), PROVIDER_FILEN)

    def test_other(self):
        self.assertEqual(detect_provider("https://example.com/x"), PROVIDER_OTHER)

    def test_empty_or_invalid(self):
        self.assertEqual(detect_provider(""), PROVIDER_OTHER)
        self.assertEqual(detect_provider("not-a-url"), PROVIDER_OTHER)

    def test_emoji_and_label_have_fallbacks(self):
        for p in (PROVIDER_GDOCS, PROVIDER_GDRIVE, PROVIDER_FILEN, PROVIDER_OTHER, "totally-unknown"):
            self.assertTrue(provider_emoji(p))
            self.assertTrue(provider_label(p))


class MaterialsTextTest(unittest.TestCase):
    def test_single_resource_renders_flat(self):
        text = build_materials_text([
            {"id": 1, "student_id": None, "label": "Курс", "url": "https://docs.google.com/x", "provider": "gdocs", "is_primary": True},
        ])
        self.assertIn("Учебные материалы", text)
        self.assertIn("Курс", text)
        # No group headers when single.
        self.assertNotIn("Основное", text)
        self.assertNotIn("Общие", text)

    def test_grouped_layout(self):
        text = build_materials_text([
            {"id": 1, "student_id": None, "label": "Глоб основа", "url": "https://filen.io/g", "provider": "filen", "is_primary": True},
            {"id": 2, "student_id": None, "label": "Аудио", "url": "https://filen.io/a", "provider": "filen", "is_primary": False},
            {"id": 3, "student_id": 1001, "label": "Лично", "url": "https://docs.google.com/p", "provider": "gdocs", "is_primary": False},
        ])
        self.assertIn("Основное", text)
        self.assertIn("Глоб основа", text)
        self.assertIn("Общие", text)
        self.assertIn("Аудио", text)
        self.assertIn("Дополнительно для вас", text)
        self.assertIn("Лично", text)

    def test_html_label_escaped(self):
        text = build_materials_text([
            {"id": 1, "student_id": None, "label": "<script>", "url": "https://filen.io/x", "provider": "filen", "is_primary": True},
        ])
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)


class MaterialsKeyboardTest(unittest.TestCase):
    def test_primary_first(self):
        kb = make_materials_keyboard([
            {"id": 1, "student_id": None, "label": "Аудио", "url": "https://filen.io/a", "provider": "filen", "is_primary": False},
            {"id": 2, "student_id": None, "label": "Курс", "url": "https://docs.google.com/c", "provider": "gdocs", "is_primary": True},
        ])
        url_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.url]
        self.assertEqual(url_buttons[0].url, "https://docs.google.com/c")
        self.assertIn("⭐", url_buttons[0].text)

    def test_empty_falls_back_to_website(self):
        kb = make_materials_keyboard([], website_url="https://teacher.example")
        urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
        self.assertEqual(urls, ["https://teacher.example"])

    def test_empty_no_website(self):
        kb = make_materials_keyboard([])
        urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
        self.assertEqual(urls, [])


class AdminResourcesUIText(unittest.TestCase):
    def test_student_resources_text_with_primary(self):
        text = build_admin_student_resources_text("Иван", [
            {"id": 1, "student_id": 1, "label": "Курс", "provider": "gdocs", "is_primary": True},
            {"id": 2, "student_id": 1, "label": "Аудио", "provider": "filen", "is_primary": False},
        ])
        self.assertIn("Учебные ссылки", text)
        self.assertIn("Иван", text)
        self.assertIn("Курс", text)
        self.assertIn("Дополнительные", text)

    def test_student_resources_text_empty(self):
        text = build_admin_student_resources_text("Иван", [])
        self.assertIn("Иван", text)
        self.assertIn("ссылок", text)

    def test_global_resources_text(self):
        empty = build_admin_global_resources_text([])
        self.assertIn("Глобальных ссылок ещё нет", empty)
        full = build_admin_global_resources_text([
            {"id": 1, "student_id": None, "label": "X", "provider": "filen", "is_primary": True},
        ])
        self.assertIn("Всего: 1", full)


class AdminKeyboardsTest(unittest.TestCase):
    def test_student_resources_keyboard_includes_actions(self):
        kb = make_admin_student_resources_keyboard(
            42,
            0,
            [
                {"id": 1, "student_id": 42, "label": "Курс", "url": "https://docs.google.com/x", "provider": "gdocs", "is_primary": True},
                {"id": 2, "student_id": 42, "label": "Аудио", "url": "https://filen.io/a", "provider": "filen", "is_primary": False},
            ],
        )
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        # Primary row only has delete (no "make primary"); secondary row has both.
        self.assertTrue(any("admin:resources:set_primary:2:42:0" == c for c in callbacks))
        self.assertTrue(any("admin:resources:delete:1:42:0" == c for c in callbacks))
        self.assertTrue(any("admin:resources:add:42:0" == c for c in callbacks))
        self.assertIn("admin:resources:global", callbacks)

    def test_global_keyboard_uses_global_targets(self):
        kb = make_admin_global_resources_keyboard([
            {"id": 5, "student_id": None, "label": "Г", "url": "https://filen.io/g", "provider": "filen", "is_primary": True},
        ])
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertTrue(any("admin:resources:delete:5:global:0" == c for c in callbacks))
        self.assertTrue(any("admin:resources:add:global:0" == c for c in callbacks))


if __name__ == "__main__":
    unittest.main()
