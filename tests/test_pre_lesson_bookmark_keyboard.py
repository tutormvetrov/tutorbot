"""Кнопка с Google Meet (и VK Звонком) в напоминании «📖 Закладка перед уроком»."""
from keyboards.user import make_pre_lesson_bookmark_keyboard


def _texts_and_urls(markup):
    return [(b.text, b.url) for row in markup.inline_keyboard for b in row]


def test_returns_none_when_no_links():
    assert make_pre_lesson_bookmark_keyboard() is None


def test_only_google_meet():
    kb = make_pre_lesson_bookmark_keyboard(google_meet_url="https://meet.google.com/abc")
    assert kb is not None
    pairs = _texts_and_urls(kb)
    assert pairs == [("📹 Открыть Google Meet", "https://meet.google.com/abc")]


def test_only_vk():
    kb = make_pre_lesson_bookmark_keyboard(vk_call_url="https://vk.me/call/x")
    assert kb is not None
    pairs = _texts_and_urls(kb)
    assert pairs == [("📞 VK Звонок", "https://vk.me/call/x")]


def test_both_links_meet_first():
    kb = make_pre_lesson_bookmark_keyboard(
        google_meet_url="https://meet.google.com/abc",
        vk_call_url="https://vk.me/call/x",
    )
    pairs = _texts_and_urls(kb)
    # Google Meet идёт первой строкой как основная ссылка для онлайн-уроков.
    assert pairs[0][0].startswith("📹")
    assert pairs[1][0].startswith("📞")
