from __future__ import annotations

import html as std_html
import re

from aiogram import html


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def homework_attachment_label(attachment_name: str | None, attachment_mime_type: str | None = None) -> str:
    name = str(attachment_name or "").strip()
    mime_type = str(attachment_mime_type or "").strip().lower()
    if not name:
        if mime_type == "application/pdf":
            name = "PDF-файл"
        elif "word" in mime_type or "officedocument.wordprocessingml.document" in mime_type:
            name = "DOCX-файл"
        elif mime_type:
            name = "Документ"
    if not name:
        return ""
    return f"📎 <b>Файл:</b> {html.quote(name)}"


def homework_body_html(
    title: str | None,
    description: str | None,
    attachment_name: str | None = None,
    attachment_mime_type: str | None = None,
) -> str:
    body = ""
    if description and str(description).strip():
        body = str(description).strip()
    elif title and str(title).strip():
        body = html.quote(str(title).strip())

    attachment_html = homework_attachment_label(attachment_name, attachment_mime_type)
    if body and attachment_html:
        return f"{body}\n\n{attachment_html}"
    if body:
        return body
    return attachment_html


def homework_preview_text(
    title: str | None,
    description: str | None,
    limit: int = 120,
    attachment_name: str | None = None,
    attachment_mime_type: str | None = None,
) -> str:
    source = homework_body_html(
        title,
        description,
        attachment_name=attachment_name,
        attachment_mime_type=attachment_mime_type,
    )
    if not source:
        return "—"

    plain = _HTML_TAG_RE.sub(" ", str(source))
    plain = std_html.unescape(plain)
    plain = _WHITESPACE_RE.sub(" ", plain).strip()
    return plain or "—"
