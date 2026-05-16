import json
import os
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

INTERNAL_TEST_ACCOUNT_RULES: list[dict[str, object]] = []

PROJECT_ROOT = Path(__file__).resolve().parents[1]

BOT_TOKEN = str(os.getenv("BOT_TOKEN", "")).strip()
ADMIN_ID_RAW = str(os.getenv("ADMIN_ID", "")).strip()
try:
    ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW else 0
except ValueError:
    ADMIN_ID = 0

PGUSER = str(os.getenv("PGUSER", "")).strip()
PGPASSWORD = str(os.getenv("PGPASSWORD", "")).strip()
DATABASE = str(os.getenv("DATABASE", "")).strip()
PGHOST = str(os.getenv("PGHOST", "")).strip()
PGPORT = str(os.getenv("PGPORT", "5432")).strip() or "5432"

POSTGRES_URI = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{DATABASE}"

TOUCHES_ENABLED = str(os.getenv("TOUCHES_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}
try:
    TOUCHES_RUN_HOUR = int(os.getenv("TOUCHES_RUN_HOUR", "11"))
except ValueError:
    TOUCHES_RUN_HOUR = 11
try:
    TOUCHES_RUN_MINUTE = int(os.getenv("TOUCHES_RUN_MINUTE", "0"))
except ValueError:
    TOUCHES_RUN_MINUTE = 0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


RATE_LIMIT_USER_SECONDS = _env_float("RATE_LIMIT_USER_SECONDS", 0.7)
RATE_LIMIT_ADMIN_SECONDS = _env_float("RATE_LIMIT_ADMIN_SECONDS", 0.25)
RATE_LIMIT_CALLBACK_SECONDS = _env_float("RATE_LIMIT_CALLBACK_SECONDS", 0.5)

TUTORBOT_TIMEZONE = str(os.getenv("TUTORBOT_TIMEZONE", "Europe/Moscow")).strip() or "Europe/Moscow"
try:
    BUSINESS_TIMEZONE = ZoneInfo(TUTORBOT_TIMEZONE)
    BUSINESS_TIMEZONE_ERROR = ""
except ZoneInfoNotFoundError:
    BUSINESS_TIMEZONE = ZoneInfo("Europe/Moscow")
    BUSINESS_TIMEZONE_ERROR = f"Unknown time zone: {TUTORBOT_TIMEZONE}"
BUSINESS_TIMEZONE_LABEL = "МСК" if TUTORBOT_TIMEZONE == "Europe/Moscow" else TUTORBOT_TIMEZONE

GOOGLE_CALENDAR_ID = str(os.getenv("GOOGLE_CALENDAR_ID", "")).strip()
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "/home/deploy/.secrets/tutorbot/credentials.json",
).strip()
TUTORBOT_ROOT = Path(os.getenv("TUTORBOT_ROOT", PROJECT_ROOT)).resolve()
TUTORBOT_SERVICE_NAME = str(os.getenv("TUTORBOT_SERVICE_NAME", "tutorbot")).strip() or "tutorbot"
TUTORBOT_SYSTEMD_SCOPE = str(os.getenv("TUTORBOT_SYSTEMD_SCOPE", "system")).strip() or "system"
TUTORBOT_BACKUP_DIR = Path(os.getenv("TUTORBOT_BACKUP_DIR", TUTORBOT_ROOT / "backups")).resolve()

_TEACHER_INFO_PATH = PROJECT_ROOT / "data" / "teacher_info.json"


def load_teacher_info() -> dict:
    """Load teacher contacts and requisites from data/teacher_info.json.
    Read on every call so edits take effect without restarting the bot.
    """
    try:
        with Path(_TEACHER_INFO_PATH).open(encoding="utf-8") as f:
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
        telegram_ids = cast(set[int], rule.get("telegram_ids", set()))
        usernames = cast(set[str], rule.get("usernames", set()))
        surname = cast(str, rule.get("surname", ""))
        names = cast(set[str], rule.get("names", set()))
        if telegram_id is not None and telegram_id in telegram_ids:
            return True
        if normalized_username and normalized_username in usernames:
            return True
        if surname in tokens and tokens.intersection(names):
            return True
        if tokens and tokens.issubset(names):
            return True
    return False


def is_internal_test_account_name(full_name: str) -> bool:
    return is_internal_test_account(full_name=full_name)
