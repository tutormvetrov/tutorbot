import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from data import config
from handlers.users.admin import admin_preview_parents
from handlers.users.admin_sections.parents import (
    admin_parent_card,
    admin_parent_danger,
    admin_parent_deactivate_confirm,
    admin_parent_deactivate_prompt,
    admin_parent_deactivate_review,
    admin_parent_delete_confirm,
    admin_parent_delete_prompt,
    admin_parent_delete_review,
    admin_parents,
    admin_parents_search_start,
    admin_parents_search_submit,
)
from tests.helpers import DummyCallbackQuery, DummyMessage, DummyState


def _keyboard_texts(reply_markup):
    return [button.text for row in reply_markup.inline_keyboard for button in row]


class FakeParentAdminDB:
    def __init__(self, admin_id: int):
        self.admin_id = admin_id
        self.parents = {
            701: {
                "telegram_id": 701,
                "full_name": "Мария Иванова",
                "username": "maria_parent",
                "role": "parent",
                "is_active": True,
            },
            702: {
                "telegram_id": 702,
                "full_name": "Елена Петрова",
                "username": None,
                "role": "parent",
                "is_active": True,
            },
        }
        self.children = {
            701: [
                {"link_id": 1, "child_label": "Анна Иванова", "student_info": "Анна Иванова", "link_status": "linked"},
                {"link_id": 2, "child_label": "Максим Иванов", "student_info": "Максим Иванов", "link_status": "waiting_link"},
            ],
            702: [
                {"link_id": 3, "child_label": "Лев Петров", "student_info": "Лев Петров", "link_status": "linked"},
            ],
        }
        self.payer_counts = {
            701: 3,
            702: 1,
        }
        self.deactivated = []
        self.deleted = []

    async def get_user(self, telegram_id):
        if telegram_id == self.admin_id:
            return {
                "telegram_id": self.admin_id,
                "full_name": "Admin",
                "role": "teacher_admin",
                "is_active": True,
            }
        return self.parents.get(telegram_id)

    async def get_parents_overview(self):
        items = []
        for parent_id, parent in sorted(self.parents.items(), key=lambda item: item[1]["full_name"]):
            if parent.get("is_active") is False:
                continue
            children = self.children.get(parent_id, [])
            items.append(
                {
                    "telegram_id": parent_id,
                    "full_name": parent["full_name"],
                    "username": parent.get("username"),
                    "children_count": len(children),
                    "linked_children_count": len([child for child in children if child.get("link_status") == "linked"]),
                }
            )
        return items

    async def get_parent_children_overview(self, parent_id):
        return list(self.children.get(parent_id, []))

    async def get_parent_deletion_snapshot(self, parent_id):
        children = self.children.get(parent_id, [])
        return {
            "children_count": len(children),
            "linked_children_count": len([child for child in children if child.get("link_status") == "linked"]),
            "payments_as_payer": self.payer_counts.get(parent_id, 0),
        }

    async def deactivate_parent(self, parent_id):
        self.deactivated.append(parent_id)
        if parent_id in self.parents:
            self.parents[parent_id]["is_active"] = False

    async def delete_parent_preserving_history(self, parent_id):
        self.deleted.append(parent_id)
        self.parents.pop(parent_id, None)
        self.children.pop(parent_id, None)
        self.payer_counts.pop(parent_id, None)

    async def get_students_overview(self):
        return [
            {
                "telegram_id": 201,
                "full_name": "Нина Долгова",
                "lesson_format": "online",
                "lesson_balance": 3,
                "next_lesson_date": None,
            }
        ]


class AdminParentManagementTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.admin_id_backup = config.ADMIN_ID
        self.admin_id = config.ADMIN_ID or 990001
        config.ADMIN_ID = self.admin_id

    def tearDown(self):
        config.ADMIN_ID = self.admin_id_backup

    async def test_admin_parents_opens_directory(self):
        db = FakeParentAdminDB(self.admin_id)
        state = DummyState()
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_parents(
            DummyCallbackQuery("admin:parents", message=message, user_id=self.admin_id, full_name="Admin"),
            state,
            db,
        )

        self.assertEqual(state.state.state, "AdminParentsDirectory:browsing")
        self.assertIn("Список родителей", message.edits[-1])
        self.assertIn("Мария Иванова", message.edits[-1])
        self.assertIn("Елена Петрова", message.edits[-1])

    async def test_admin_parent_card_and_danger_navigation(self):
        db = FakeParentAdminDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_parent_card(
            DummyCallbackQuery("admin:parent_card:701:0", message=message, user_id=self.admin_id, full_name="Admin"),
            db,
        )

        self.assertIn("Мария Иванова", message.edits[-1])
        self.assertIn("Оплат как плательщик", message.edits[-1])
        self.assertIn("Анна Иванова", message.edits[-1])
        card_callbacks = [
            button.callback_data
            for row in message.reply_markups[-1].inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("admin:parent_preview_select:701:0", card_callbacks)
        self.assertIn("admin:parent_danger:701:0", card_callbacks)

        await admin_parent_danger(
            DummyCallbackQuery("admin:parent_danger:701:0", message=message, user_id=self.admin_id, full_name="Admin"),
            db,
        )

        self.assertIn("Опасные действия", message.edits[-1])
        self.assertIn("Удаление снимет связи с детьми", message.edits[-1])

    async def test_admin_parent_search_filters_directory(self):
        db = FakeParentAdminDB(self.admin_id)
        state = DummyState()
        message = DummyMessage(user_id=self.admin_id, full_name="Admin", chat_id=777, message_id=50)
        search_message = DummyMessage("Елена", user_id=self.admin_id, full_name="Admin", bot=message.bot)

        await admin_parents(
            DummyCallbackQuery("admin:parents", message=message, user_id=self.admin_id, full_name="Admin"),
            state,
            db,
        )
        await admin_parents_search_start(
            DummyCallbackQuery("admin:parents:search", message=message, user_id=self.admin_id, full_name="Admin"),
            state,
        )
        await admin_parents_search_submit(search_message, state, db)

        self.assertEqual(state.state.state, "AdminParentsDirectory:browsing")
        self.assertTrue(search_message.bot.edited_messages)
        edited = search_message.bot.edited_messages[-1]
        self.assertIn("Елена Петрова", edited.text)
        self.assertNotIn("Мария Иванова", edited.text)

    async def test_admin_parent_deactivate_review_and_confirm(self):
        db = FakeParentAdminDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_parent_deactivate_prompt(
            DummyCallbackQuery(
                "admin:parent_deactivate_prompt:701:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertEqual(
            message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:parent_deactivate_review:701:0",
        )

        await admin_parent_deactivate_review(
            DummyCallbackQuery(
                "admin:parent_deactivate_review:701:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertEqual(
            message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:parent_deactivate_confirm:701:0",
        )

        await admin_parent_deactivate_confirm(
            DummyCallbackQuery(
                "admin:parent_deactivate_confirm:701:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertEqual(db.deactivated, [701])
        self.assertIn("Родитель деактивирован", message.edits[-1])

        preview_message = DummyMessage(user_id=self.admin_id, full_name="Admin")
        await admin_preview_parents(
            DummyCallbackQuery(
                "admin:preview:parents",
                message=preview_message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        preview_texts = _keyboard_texts(preview_message.reply_markups[-1])
        self.assertFalse(any("Мария Иванова" in text for text in preview_texts))

    async def test_admin_parent_delete_review_and_confirm(self):
        db = FakeParentAdminDB(self.admin_id)
        message = DummyMessage(user_id=self.admin_id, full_name="Admin")

        await admin_parent_delete_prompt(
            DummyCallbackQuery(
                "admin:parent_delete_prompt:702:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertEqual(
            message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:parent_delete_review:702:0",
        )

        await admin_parent_delete_review(
            DummyCallbackQuery(
                "admin:parent_delete_review:702:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertEqual(
            message.reply_markups[-1].inline_keyboard[0][0].callback_data,
            "admin:parent_delete_confirm:702:0",
        )

        await admin_parent_delete_confirm(
            DummyCallbackQuery(
                "admin:parent_delete_confirm:702:0",
                message=message,
                user_id=self.admin_id,
                full_name="Admin",
            ),
            db,
        )
        self.assertEqual(db.deleted, [702])
        self.assertIn("Родитель удалён", message.edits[-1])

        list_message = DummyMessage(user_id=self.admin_id, full_name="Admin")
        await admin_parents(
            DummyCallbackQuery("admin:parents", message=list_message, user_id=self.admin_id, full_name="Admin"),
            DummyState(),
            db,
        )
        self.assertNotIn("Елена Петрова", list_message.edits[-1])


if __name__ == "__main__":
    unittest.main()
