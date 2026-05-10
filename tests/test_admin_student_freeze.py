"""Юнит-тесты ручной заморозки ученика и переноса баланса.

Не трогаем БД — проверяем чистые функции (расчёт даты понедельника, разбор
периода) и поведение клавиатуры карточки и оплат при разных входных данных.
"""
from datetime import date, datetime, timedelta

import pytest

from handlers.users.admin_sections.students_freeze import (
    PERIOD_LABELS,
    _resolve_freeze_until,
)
from keyboards.admin_panels import make_payment_delete_keyboard
from keyboards.admin_students import make_admin_student_actions_keyboard
from utils.db_api.users import FREEZE_FOREVER_SENTINEL, DatabaseUserMixin


# ── _resolve_freeze_until ────────────────────────────────────────────────────

def test_resolve_freeze_until_seven_days():
    until = _resolve_freeze_until("7d")
    assert until is not None
    delta = until - datetime.utcnow()
    # Допуск ±1 минута на исполнение теста.
    assert timedelta(days=7) - timedelta(minutes=1) <= delta <= timedelta(days=7) + timedelta(minutes=1)


def test_resolve_freeze_until_forever():
    assert _resolve_freeze_until("forever") is None


def test_period_labels_complete():
    # Каждому периоду должна быть человекочитаемая метка.
    for key in ("7d", "14d", "30d", "90d", "forever"):
        assert key in PERIOD_LABELS


# ── _next_monday (carry-over) ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "today, expected_monday",
    [
        # Если сегодня среда, ближайший понедельник — через 5 дней.
        (date(2026, 5, 6), date(2026, 5, 11)),  # ср → пн
        # Если сегодня воскресенье — понедельник завтра.
        (date(2026, 5, 10), date(2026, 5, 11)),  # вс → пн
        # Если сегодня понедельник — следующий понедельник через 7 дней (не
        # сегодняшний, потому что carry_over действует одну неделю).
        (date(2026, 5, 11), date(2026, 5, 18)),
        # Суббота → ближайший понедельник через 2 дня.
        (date(2026, 5, 9), date(2026, 5, 11)),
    ],
)
def test_next_monday(today, expected_monday):
    assert DatabaseUserMixin._next_monday(today) == expected_monday


# ── Кнопка заморозки в клавиатуре «Действия» ─────────────────────────────────

def _all_button_texts(markup):
    out = []
    for row in markup.inline_keyboard:
        for btn in row:
            out.append(btn.text)
    return out


def _all_callbacks(markup):
    out = []
    for row in markup.inline_keyboard:
        for btn in row:
            out.append(btn.callback_data)
    return out


def test_actions_keyboard_shows_freeze_when_not_frozen():
    kb = make_admin_student_actions_keyboard(123, page=0, frozen_until=None)
    texts = _all_button_texts(kb)
    callbacks = _all_callbacks(kb)
    assert any("Заморозить" in t for t in texts)
    assert any(c.startswith("admin:student_freeze:123:0") for c in callbacks if c)


def test_actions_keyboard_shows_unfreeze_with_date():
    kb = make_admin_student_actions_keyboard(
        123, page=2, frozen_until=datetime(2026, 6, 12, 0, 0),
    )
    texts = _all_button_texts(kb)
    callbacks = _all_callbacks(kb)
    assert any("Разморозить" in t and "12.06" in t for t in texts)
    assert any(c.startswith("admin:student_unfreeze:123:2") for c in callbacks if c)


def test_actions_keyboard_shows_unfreeze_forever():
    kb = make_admin_student_actions_keyboard(
        123, page=0, frozen_until=FREEZE_FOREVER_SENTINEL,
    )
    texts = _all_button_texts(kb)
    assert any("Разморозить" in t and "бессрочно" in t for t in texts)


# ── Кнопки в карточке оплат ──────────────────────────────────────────────────

def _sample_payments():
    return [{"id": 1, "amount": 1500, "payment_date": datetime(2026, 5, 1)}]


def test_payments_keyboard_shows_reset_for_negative_balance():
    kb = make_payment_delete_keyboard(123, _sample_payments(), balance=-3)
    texts = _all_button_texts(kb)
    assert any("Обнулить баланс" in t and "-3" in t for t in texts)


def test_payments_keyboard_shows_reset_for_positive_balance():
    """Главное требование владельца: кнопка должна быть видна и при balance > 0."""
    kb = make_payment_delete_keyboard(123, _sample_payments(), balance=5)
    texts = _all_button_texts(kb)
    assert any("Обнулить баланс" in t and "+5" in t for t in texts)


def test_payments_keyboard_hides_reset_for_zero_balance():
    kb = make_payment_delete_keyboard(123, _sample_payments(), balance=0)
    texts = _all_button_texts(kb)
    assert not any("Обнулить баланс" in t for t in texts)


def test_payments_keyboard_shows_carry_over_when_inactive():
    kb = make_payment_delete_keyboard(
        123, _sample_payments(), balance=2, carry_over_until=None,
    )
    texts = _all_button_texts(kb)
    assert any("Перенести на следующую неделю" in t for t in texts)


def test_payments_keyboard_shows_clear_carry_over_when_active():
    kb = make_payment_delete_keyboard(
        123, _sample_payments(), balance=2, carry_over_until=date(2026, 5, 18),
    )
    texts = _all_button_texts(kb)
    assert any("Отменить перенос" in t and "18.05" in t for t in texts)


# ── DB-mixin: freeze_student использует sentinel для бессрочной заморозки ────

class _FakeMixin(DatabaseUserMixin):
    """Минимальный stub: ловим аргументы execute()."""

    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args, **kwargs):
        self.calls.append((sql, args, kwargs))
        return None


def test_freeze_student_with_none_uses_sentinel():
    import asyncio
    fake = _FakeMixin()
    asyncio.run(fake.freeze_student(42, until=None))
    assert len(fake.calls) == 1
    sql, args, kwargs = fake.calls[0]
    assert "UPDATE users" in sql
    assert "frozen_until" in sql
    assert args == (42, FREEZE_FOREVER_SENTINEL)


def test_freeze_student_with_concrete_date():
    import asyncio
    fake = _FakeMixin()
    target = datetime(2026, 6, 1)
    asyncio.run(fake.freeze_student(42, until=target))
    sql, args, kwargs = fake.calls[0]
    assert args == (42, target)


def test_unfreeze_student_sets_null():
    import asyncio
    fake = _FakeMixin()
    asyncio.run(fake.unfreeze_student(42))
    sql, args, kwargs = fake.calls[0]
    assert "frozen_until = NULL" in sql
    assert args == (42,)


def test_clear_carry_over_sets_null():
    import asyncio
    fake = _FakeMixin()
    asyncio.run(fake.clear_carry_over(42))
    sql, _args, _ = fake.calls[0]
    assert "carry_over_until = NULL" in sql


def test_mark_carry_over_returns_monday():
    import asyncio
    fake = _FakeMixin()
    target = asyncio.run(fake.mark_carry_over(42))
    # Должен прийти будущий понедельник.
    assert target.weekday() == 0
    assert target > date.today()
