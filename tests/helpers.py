from types import SimpleNamespace


class DummyState:
    def __init__(self):
        self.state = None
        self.data = {}

    async def set_state(self, state):
        self.state = state

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return dict(self.data)

    async def clear(self):
        self.state = None
        self.data = {}


class DummyBot:
    def __init__(self):
        self.sent_messages = []
        self.edited_messages = []
        self.copied_messages = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append(
            SimpleNamespace(chat_id=chat_id, text=text, reply_markup=reply_markup)
        )

    async def copy_message(self, chat_id, from_chat_id, message_id, reply_markup=None):
        self.copied_messages.append(
            SimpleNamespace(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
            )
        )

    async def edit_message_text(self, text, chat_id, message_id, reply_markup=None):
        self.edited_messages.append(
            SimpleNamespace(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
        )


class DummyMessage:
    def __init__(
        self,
        text="",
        user_id=1,
        full_name="Test User",
        username="testuser",
        bot=None,
        chat_id=None,
        message_id=100,
        caption=None,
        animation=None,
        sticker=None,
        photo=None,
        video=None,
        document=None,
        voice=None,
    ):
        self.text = text
        self.caption = caption
        self.entities = None
        self.caption_entities = None
        self.html_text = text or caption or ""
        self.from_user = SimpleNamespace(id=user_id, full_name=full_name, username=username)
        self.bot = bot or DummyBot()
        self.chat = SimpleNamespace(id=chat_id or user_id)
        self.message_id = message_id
        self.animation = animation
        self.sticker = sticker
        self.photo = photo
        self.video = video
        self.document = document
        self.voice = voice
        self.answers = []
        self.edits = []
        self.reply_markups = []
        self.copies = []

    async def answer(self, text, reply_markup=None):
        self.answers.append(text)
        self.reply_markups.append(reply_markup)

    async def edit_text(self, text, reply_markup=None):
        self.edits.append(text)
        self.reply_markups.append(reply_markup)

    async def edit_reply_markup(self, reply_markup=None):
        self.reply_markups.append(reply_markup)

    async def copy_to(self, chat_id):
        self.copies.append(chat_id)


class DummyCallbackQuery:
    def __init__(self, data, message=None, user_id=1, full_name="Test User", username="testuser", bot=None):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, full_name=full_name, username=username)
        self.message = message or DummyMessage(user_id=user_id, full_name=full_name, username=username, bot=bot)
        self.bot = bot or self.message.bot
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(SimpleNamespace(text=text, show_alert=show_alert))


class DummyAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummyConn:
    def __init__(self, fetchrow_result=None):
        self.fetchrow_result = fetchrow_result
        self.executed = []

    async def fetchrow(self, query, *args):
        self.executed.append((query, args))
        return self.fetchrow_result

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "OK"

    async def fetch(self, query, *args):
        self.executed.append((query, args))
        return []


class DummyPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return DummyAcquire(self.conn)
