from contextlib import asynccontextmanager


def _resolve_message(target):
    return getattr(target, "message", None) or target


def _resolve_bot(target):
    return getattr(target, "bot", None) or getattr(_resolve_message(target), "bot", None)


@asynccontextmanager
async def with_chat_action(target, action: str = "typing"):
    message = _resolve_message(target)
    bot = _resolve_bot(target)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if bot and chat_id is not None:
        try:
            await bot.send_chat_action(chat_id=chat_id, action=action)
        except Exception:
            pass
    yield
