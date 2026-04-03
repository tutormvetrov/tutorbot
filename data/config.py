import json
import os
from dotenv import load_dotenv

load_dotenv()

INTERNAL_TEST_ACCOUNT_RULES = [
    {
        "telegram_ids": {389264815},
        "usernames": {"eliza_znkv"},
        "surname": "занкевич",
        "names": {"лиза", "елизавета", "eliza"},
    },
]

BOT_TOKEN = str(os.getenv("BOT_TOKEN"))
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

PGUSER = str(os.getenv("PGUSER"))
PGPASSWORD = str(os.getenv("PGPASSWORD"))
DATABASE = str(os.getenv("DATABASE"))
PGHOST = str(os.getenv("PGHOST"))
PGPORT = str(os.getenv("PGPORT"))

POSTGRES_URI = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{DATABASE}"

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "/home/deploy/.secrets/tutorbot/credentials.json",
)

_TEACHER_INFO_PATH = os.path.join(os.path.dirname(__file__), "teacher_info.json")


def load_teacher_info() -> dict:
    """Load teacher contacts and requisites from data/teacher_info.json.
    Read on every call so edits take effect without restarting the bot.
    """
    try:
        with open(_TEACHER_INFO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def normalize_person_name(value: str) -> str:
    return " ".join((value or "").lower().replace("ё", "е").split())


def is_internal_test_account(
    full_name: str = "",
    username: str = "",
    telegram_id: int | None = None,
) -> bool:
    normalized_username = normalize_person_name(username).lstrip("@")
    normalized = normalize_person_name(full_name)
    tokens = set(normalized.split())
    for rule in INTERNAL_TEST_ACCOUNT_RULES:
        if telegram_id is not None and telegram_id in rule.get("telegram_ids", set()):
            return True
        if normalized_username and normalized_username in rule.get("usernames", set()):
            return True
        if rule["surname"] in tokens and tokens.intersection(rule["names"]):
            return True
        if tokens and tokens.issubset(rule["names"]):
            return True
    return False


def is_internal_test_account_name(full_name: str) -> bool:
    return is_internal_test_account(full_name=full_name)
