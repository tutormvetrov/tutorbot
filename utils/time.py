from __future__ import annotations

from datetime import date, datetime, timezone

from data import config


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def business_now() -> datetime:
    return datetime.now(config.BUSINESS_TIMEZONE)


def business_today() -> date:
    return business_now().date()


def business_naive_now() -> datetime:
    return business_now().replace(tzinfo=None)


def business_timestamp_label(value: datetime | None = None, fmt: str = "%d.%m.%Y %H:%M:%S") -> str:
    stamp = value or business_now()
    return f"{stamp.strftime(fmt)} {config.BUSINESS_TIMEZONE_LABEL}"
