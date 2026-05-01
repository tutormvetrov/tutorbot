"""Provider detection for student learning resource URLs.

Used by `student_resources` to auto-detect what kind of folder/document
URL the admin pasted, so the bot can render the right icon and label.
"""
from __future__ import annotations

from urllib.parse import urlparse

PROVIDER_GDOCS = "gdocs"
PROVIDER_GDRIVE = "gdrive"
PROVIDER_FILEN = "filen"
PROVIDER_OTHER = "other"

_PROVIDER_EMOJI = {
    PROVIDER_GDOCS: "📄",
    PROVIDER_GDRIVE: "📂",
    PROVIDER_FILEN: "🗂",
    PROVIDER_OTHER: "🔗",
}

_PROVIDER_LABEL = {
    PROVIDER_GDOCS: "Google Docs",
    PROVIDER_GDRIVE: "Google Drive",
    PROVIDER_FILEN: "Filen",
    PROVIDER_OTHER: "Ссылка",
}


def detect_provider(url: str) -> str:
    if not url:
        return PROVIDER_OTHER
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
    except Exception:
        return PROVIDER_OTHER
    if not host:
        return PROVIDER_OTHER
    if host == "docs.google.com" or host.endswith(".docs.google.com"):
        return PROVIDER_GDOCS
    if host == "drive.google.com" or host.endswith(".drive.google.com"):
        return PROVIDER_GDRIVE
    if host == "filen.io" or host.endswith(".filen.io"):
        return PROVIDER_FILEN
    return PROVIDER_OTHER


def provider_emoji(provider: str) -> str:
    return _PROVIDER_EMOJI.get(provider, _PROVIDER_EMOJI[PROVIDER_OTHER])


def provider_label(provider: str) -> str:
    return _PROVIDER_LABEL.get(provider, _PROVIDER_LABEL[PROVIDER_OTHER])
