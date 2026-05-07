"""Tests for the four-DOCX user-guide subsystem (paths, keyboards, role gates)."""
from pathlib import Path

from keyboards.inline import (
    admin_service_keyboard,
    make_admin_guides_picker_keyboard,
    make_student_guide_picker_keyboard,
    parent_more_keyboard,
    student_more_keyboard,
)
from utils.user_guides import (
    USER_GUIDE_DIR,
    USER_GUIDE_FILES,
    USER_GUIDE_TITLES,
    is_valid_guide_kind,
)


# ── Path registry sanity ─────────────────────────────────────────────────────

def test_user_guide_files_has_four_kinds():
    assert set(USER_GUIDE_FILES.keys()) == {"student_adult", "student_school", "parent", "admin"}


def test_user_guide_files_under_docs_user_guides():
    for path in USER_GUIDE_FILES.values():
        assert isinstance(path, Path)
        assert path.parent == USER_GUIDE_DIR
        assert str(path).endswith(".docx")


def test_user_guide_titles_match_keys():
    assert set(USER_GUIDE_TITLES.keys()) == set(USER_GUIDE_FILES.keys())


def test_user_guide_files_are_built_and_committed():
    for kind, path in USER_GUIDE_FILES.items():
        assert path.exists(), (
            f"{kind} guide is missing at {path}. Run `python scripts/build_user_guides.py` "
            "to regenerate."
        )
        # DOCX files should be > 5 KB once they have actual content
        assert path.stat().st_size > 5_000


def test_is_valid_guide_kind():
    assert is_valid_guide_kind("student_adult")
    assert is_valid_guide_kind("admin")
    assert not is_valid_guide_kind("teacher")
    assert not is_valid_guide_kind("")


# ── Keyboard wiring ──────────────────────────────────────────────────────────

def _flatten_callbacks(keyboard):
    return [btn.callback_data for row in keyboard.inline_keyboard for btn in row]


def test_student_more_has_guide_menu_button():
    callbacks = _flatten_callbacks(student_more_keyboard)
    assert "guide:menu:student" in callbacks


def test_parent_more_has_guide_send_parent_button():
    callbacks = _flatten_callbacks(parent_more_keyboard)
    assert "guide:send:parent" in callbacks


def test_admin_service_has_admin_guides_button():
    callbacks = _flatten_callbacks(admin_service_keyboard)
    assert "admin:guides" in callbacks


def test_student_picker_has_both_versions():
    callbacks = _flatten_callbacks(make_student_guide_picker_keyboard())
    assert "guide:send:student_adult" in callbacks
    assert "guide:send:student_school" in callbacks


def test_admin_picker_has_all_four_kinds():
    callbacks = _flatten_callbacks(make_admin_guides_picker_keyboard())
    assert "guide:send:student_adult" in callbacks
    assert "guide:send:student_school" in callbacks
    assert "guide:send:parent" in callbacks
    assert "guide:send:admin" in callbacks


# ── Role gate (logic-level test, no full handler bootstrap) ─────────────────

def test_role_gate_allowed_kinds():
    from handlers.users.callbacks import GUIDE_ALLOWED_BY_ROLE
    assert GUIDE_ALLOWED_BY_ROLE["student"] == {"student_adult", "student_school"}
    assert GUIDE_ALLOWED_BY_ROLE["parent"] == {"parent"}
    assert "admin" in GUIDE_ALLOWED_BY_ROLE["admin"]
    # student must not get admin or parent guide
    assert "admin" not in GUIDE_ALLOWED_BY_ROLE["student"]
    assert "parent" not in GUIDE_ALLOWED_BY_ROLE["student"]
    # parent must not get student or admin guide
    assert "student_adult" not in GUIDE_ALLOWED_BY_ROLE["parent"]
    assert "student_school" not in GUIDE_ALLOWED_BY_ROLE["parent"]
    assert "admin" not in GUIDE_ALLOWED_BY_ROLE["parent"]
