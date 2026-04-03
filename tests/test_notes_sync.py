import json
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from handlers.users.admin_sections import notes as notes_module


class NotesSyncTest(unittest.TestCase):
    def test_save_notes_updates_agent_context_and_debug_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            original = {
                "NOTES_FILE": notes_module.NOTES_FILE,
                "CLAUDE_MEMORY_DIR": notes_module.CLAUDE_MEMORY_DIR,
                "CLAUDE_DOC_FILE": notes_module.CLAUDE_DOC_FILE,
                "AGENT_CONTEXT_FILE": notes_module.AGENT_CONTEXT_FILE,
                "DEBUG_CONTEXT_LOG_FILE": notes_module.DEBUG_CONTEXT_LOG_FILE,
            }

            try:
                notes_module.NOTES_FILE = data_dir / "admin_notes.json"
                notes_module.CLAUDE_MEMORY_DIR = root / "memory"
                notes_module.CLAUDE_DOC_FILE = root / "CLAUDE.md"
                notes_module.AGENT_CONTEXT_FILE = root / "AGENT_CONTEXT.md"
                notes_module.DEBUG_CONTEXT_LOG_FILE = data_dir / "debug_context.jsonl"

                note = {"timestamp": "03.04.2026 08:00 МСК", "content": "Проверка нового контекста"}
                notes_module._save_notes([note])
                notes_module._append_debug_context_event("note_added", note=note, notes_count=1)

                agent_context = notes_module.AGENT_CONTEXT_FILE.read_text(encoding="utf-8")
                self.assertIn("AGENT_CONTEXT.md", agent_context)
                self.assertIn("Проверка нового контекста", agent_context)
                self.assertIn("data/debug_context.jsonl", agent_context)

                log_lines = notes_module.DEBUG_CONTEXT_LOG_FILE.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(log_lines), 1)
                payload = json.loads(log_lines[0])
                self.assertEqual(payload["event"], "note_added")
                self.assertEqual(payload["notes_count"], 1)
                self.assertEqual(payload["note"]["content"], "Проверка нового контекста")
                self.assertEqual(payload["note"]["kind"], "text")
            finally:
                for key, value in original.items():
                    setattr(notes_module, key, value)

    def test_save_photo_note_writes_media_path_into_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            original = {
                "NOTES_FILE": notes_module.NOTES_FILE,
                "CLAUDE_MEMORY_DIR": notes_module.CLAUDE_MEMORY_DIR,
                "CLAUDE_DOC_FILE": notes_module.CLAUDE_DOC_FILE,
                "AGENT_CONTEXT_FILE": notes_module.AGENT_CONTEXT_FILE,
                "DEBUG_CONTEXT_LOG_FILE": notes_module.DEBUG_CONTEXT_LOG_FILE,
            }

            try:
                notes_module.NOTES_FILE = data_dir / "admin_notes.json"
                notes_module.CLAUDE_MEMORY_DIR = root / "memory"
                notes_module.CLAUDE_DOC_FILE = root / "CLAUDE.md"
                notes_module.AGENT_CONTEXT_FILE = root / "AGENT_CONTEXT.md"
                notes_module.DEBUG_CONTEXT_LOG_FILE = data_dir / "debug_context.jsonl"

                note = {
                    "timestamp": "03.04.2026 08:30 МСК",
                    "content": "Скрин с зависшей кнопкой",
                    "kind": "photo",
                    "local_path": "/srv/tutorbot/data/debug_media/example.jpg",
                }
                notes_module._save_notes([note])

                agent_context = notes_module.AGENT_CONTEXT_FILE.read_text(encoding="utf-8")
                self.assertIn("🖼 Скриншот", agent_context)
                self.assertIn("/srv/tutorbot/data/debug_media/example.jpg", agent_context)
                self.assertIn("Скрин с зависшей кнопкой", agent_context)
            finally:
                for key, value in original.items():
                    setattr(notes_module, key, value)


if __name__ == "__main__":
    unittest.main()
