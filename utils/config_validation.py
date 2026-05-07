from __future__ import annotations

import logging
import os
from pathlib import Path

from data import config

logger = logging.getLogger(__name__)


_BOT_TOKEN_PLACEHOLDERS = {
    "",
    "your_telegram_bot_token",
}
_CALENDAR_ID_PLACEHOLDERS = {
    "your_calendar_id@group.calendar.google.com",
}
_SYSTEMD_SCOPES = {"system", "user"}
_VALIDATION_MODES = {"local", "runtime"}


def _is_missing(value: str) -> bool:
    return not str(value or "").strip()


def _normalize_validation_mode(mode: str | None) -> str:
    normalized = str(mode or "runtime").strip().lower()
    if normalized not in _VALIDATION_MODES:
        raise ValueError(f"Unsupported validation mode: {mode}")
    return normalized


def _validate_google_config(issues: list[str], mode: str) -> None:
    raw_calendar_id = str(os.getenv("GOOGLE_CALENDAR_ID", "")).strip()
    raw_credentials_path = str(os.getenv("GOOGLE_CREDENTIALS_FILE", "")).strip()
    google_requested = bool(config.GOOGLE_CALENDAR_ID or raw_credentials_path)

    if not google_requested:
        return

    if _is_missing(config.GOOGLE_CALENDAR_ID):
        issues.append("GOOGLE_CALENDAR_ID must be set when Google Calendar sync is enabled.")
    elif config.GOOGLE_CALENDAR_ID in _CALENDAR_ID_PLACEHOLDERS:
        issues.append("GOOGLE_CALENDAR_ID still contains the example placeholder value.")

    if _is_missing(config.GOOGLE_CREDENTIALS_FILE):
        issues.append("GOOGLE_CREDENTIALS_FILE must be set when Google Calendar sync is enabled.")
    elif mode == "runtime" and not Path(config.GOOGLE_CREDENTIALS_FILE).exists():
        issues.append(
            f"GOOGLE_CREDENTIALS_FILE does not exist: {config.GOOGLE_CREDENTIALS_FILE}"
        )


def collect_runtime_config_issues(mode: str = "runtime") -> list[str]:
    mode = _normalize_validation_mode(mode)
    issues: list[str] = []

    if config.BOT_TOKEN in _BOT_TOKEN_PLACEHOLDERS:
        issues.append("BOT_TOKEN is missing or still contains the example placeholder value.")
    elif ":" not in config.BOT_TOKEN:
        issues.append("BOT_TOKEN must look like a Telegram token (`<id>:<secret>`).")

    if config.ADMIN_ID_RAW and config.ADMIN_ID <= 0:
        issues.append("ADMIN_ID must be an integer.")
    if config.ADMIN_ID <= 0:
        issues.append("ADMIN_ID must be a positive integer.")

    for env_name, value in (
        ("PGUSER", config.PGUSER),
        ("PGPASSWORD", config.PGPASSWORD),
        ("DATABASE", config.DATABASE),
        ("PGHOST", config.PGHOST),
    ):
        if _is_missing(value):
            issues.append(f"{env_name} must be set.")

    try:
        port = int(config.PGPORT)
    except (TypeError, ValueError):
        issues.append("PGPORT must be an integer.")
    else:
        if not (1 <= port <= 65535):
            issues.append("PGPORT must be between 1 and 65535.")

    if not config.TUTORBOT_SERVICE_NAME.strip():
        issues.append("TUTORBOT_SERVICE_NAME must not be empty.")

    if config.TUTORBOT_SYSTEMD_SCOPE not in _SYSTEMD_SCOPES:
        issues.append("TUTORBOT_SYSTEMD_SCOPE must be either `system` or `user`.")

    if config.BUSINESS_TIMEZONE_ERROR:
        issues.append(f"TUTORBOT_TIMEZONE is invalid: {config.BUSINESS_TIMEZONE_ERROR}")

    if mode == "runtime" and not config.TUTORBOT_ROOT.exists():
        issues.append(f"TUTORBOT_ROOT does not exist: {config.TUTORBOT_ROOT}")

    backup_parent = config.TUTORBOT_BACKUP_DIR.parent
    if mode == "runtime" and not backup_parent.exists():
        issues.append(f"TUTORBOT_BACKUP_DIR parent directory does not exist: {backup_parent}")

    _validate_google_config(issues, mode)
    return issues


def format_runtime_config_issues(issues: list[str]) -> str:
    if not issues:
        return "Runtime configuration is valid."
    lines = ["Invalid runtime configuration:"]
    lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines)


def validate_teacher_info() -> None:
    """Load teacher_info.json and warn about missing key fields.

    This is a non-fatal check: the bot can operate without teacher_info.json,
    but missing fields may cause incomplete responses to students.
    """
    info = config.load_teacher_info()
    if not info:
        logger.warning(
            "teacher_info.json is missing or empty — teacher contact details will not be available."
        )
        return

    contacts = info.get("contacts") or {}
    if not str(contacts.get("phone") or "").strip():
        logger.warning(
            "teacher_info.json: contacts.phone is missing — phone number will not be shown."
        )

    if not info.get("requisites"):
        logger.warning(
            "teacher_info.json: requisites is missing — payment details will not be shown."
        )


def assert_runtime_config(mode: str = "runtime") -> None:
    issues = collect_runtime_config_issues(mode=mode)
    if issues:
        raise RuntimeError(format_runtime_config_issues(issues))
    validate_teacher_info()
