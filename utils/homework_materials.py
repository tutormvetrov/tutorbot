from __future__ import annotations

import html as std_html
import re
from collections import Counter
from typing import Mapping


_HTML_BREAK_RE = re.compile(r"(?i)<\s*br\s*/?\s*>")
_HTML_BLOCK_CLOSE_RE = re.compile(r"(?i)</\s*(?:p|div|li|ul|ol|blockquote|section|article|h[1-6])\s*>")
_HTML_LINK_RE = re.compile(r'(?is)<a\b[^>]*>(.*?)</a>')
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_NUMBERED_BLOCK_RE = re.compile(r"^\s*(?:\d+[\).]?|[-•])\s+")
_BOOK_KEYWORD_RE = re.compile(
    r"(?i)\b("
    r"student'?s\s+book|workbook|reader|book|livre|cahier|учебник|книга|"
    r"livre\s+d[’']étudiant|cahier\s+d[’']activités"
    r")\b"
)
_IGNORE_RESOURCE_RE = re.compile(
    r"(?i)\b("
    r"knowt|quizlet|youtube|worksheet|flashcards?|flashcard|video|site|website|"
    r"сайт|карточк|словар|vocabulaire|видео|ресурс"
    r")\b"
)
_PAGE_RE = re.compile(r"(?i)\b(?:pages?|pp?\.?|стр\.?)\s*(\d+)(?:\s*[-–—]\s*(\d+))?")
_UNIT_RE = re.compile(r"(?i)\bunit\s+([A-Za-z0-9-]+)")
_CHAPTER_RE = re.compile(r"(?i)\bchapter\s+([A-Za-z0-9-]+)")
_LESSON_RE = re.compile(r"(?i)\blesson\s+([A-Za-z0-9-]+)")
_EXERCISE_HEAD_RE = re.compile(r"(?i)\b(?:ex|exercise|упр)\.?\s*([^\n]+)")
_PROGRESS_RE = re.compile(
    r"(?i)\b(?:pages?|pp?\.?|стр\.?|unit|chapter|lesson|ex|exercise|упр)\b"
)
_NORMALIZE_KEY_RE = re.compile(r"[^\w\d]+", re.UNICODE)

_TITLE_CONNECTORS = {
    "a",
    "an",
    "and",
    "de",
    "des",
    "du",
    "for",
    "la",
    "le",
    "les",
    "of",
    "the",
}


def _mapping_value(item: Mapping[str, object] | None, key: str, default=None):
    if item is None:
        return default
    getter = getattr(item, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return item[key]
    except Exception:
        return default


def homework_html_to_plain_text(source: str | None) -> str:
    if not source:
        return ""

    text = str(source)
    text = _HTML_BREAK_RE.sub("\n", text)
    text = _HTML_BLOCK_CLOSE_RE.sub("\n", text)
    text = _HTML_LINK_RE.sub(lambda match: match.group(1) or "", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = std_html.unescape(text)
    text = text.replace("\xa0", " ")
    text = text.replace("\u202f", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = []
    for raw_line in text.splitlines():
        line = _WHITESPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
        elif lines and lines[-1] != "":
            lines.append("")
    return "\n".join(lines).strip()


def split_homework_into_blocks(source: str | None) -> list[str]:
    plain = homework_html_to_plain_text(source)
    if not plain:
        return []

    blocks: list[str] = []
    current: list[str] = []
    for line in plain.splitlines():
        if not line.strip():
            if current:
                blocks.append(" ".join(current).strip())
                current = []
            continue

        if _NUMBERED_BLOCK_RE.match(line):
            if current:
                blocks.append(" ".join(current).strip())
            current = [_NUMBERED_BLOCK_RE.sub("", line, count=1).strip()]
            continue

        if current:
            current.append(line.strip())
        else:
            current = [line.strip()]

    if current:
        blocks.append(" ".join(current).strip())

    return [block for block in blocks if block]


def normalize_material_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = std_html.unescape(str(value)).lower()
    normalized = normalized.replace("’", " ").replace("'", " ")
    normalized = _NORMALIZE_KEY_RE.sub(" ", normalized)
    return " ".join(part for part in normalized.split() if part)


def parse_homework_material_mentions(source: str | None) -> list[dict]:
    mentions: list[dict] = []
    for block in split_homework_into_blocks(source):
        mention = parse_homework_material_block(block)
        if mention:
            mentions.append(mention)
    return mentions


def parse_homework_material_block(block: str) -> dict | None:
    clean_block = _clean_fragment(block)
    if not clean_block:
        return None

    has_progress = bool(_PROGRESS_RE.search(clean_block))
    if _IGNORE_RESOURCE_RE.search(clean_block) and not _BOOK_KEYWORD_RE.search(clean_block) and not has_progress:
        return None

    material_title, material_key = _extract_material_title(clean_block, has_progress=has_progress)
    if not material_title or not material_key:
        return None

    progress = _extract_progress(clean_block)
    return {
        "material_key": material_key,
        "material_title": material_title,
        "material_kind": "book",
        "page_from": progress["page_from"],
        "page_to": progress["page_to"],
        "unit_label": progress["unit_label"],
        "chapter_label": progress["chapter_label"],
        "lesson_label": progress["lesson_label"],
        "exercise_label": progress["exercise_label"],
        "raw_fragment": clean_block,
    }


def material_progress_label(item: Mapping[str, object] | None) -> str:
    if not item:
        return ""

    parts: list[str] = []
    page_from = _mapping_value(item, "page_from")
    page_to = _mapping_value(item, "page_to")
    if page_from:
        if page_to and page_to != page_from:
            parts.append(f"стр. {page_from}-{page_to}")
        else:
            parts.append(f"стр. {page_from}")

    for key in ("unit_label", "chapter_label", "lesson_label", "exercise_label"):
        value = str(_mapping_value(item, key) or "").strip()
        if value:
            parts.append(value)

    return " · ".join(parts)


def build_next_homework_hint(
    latest_mention: Mapping[str, object] | None,
    recent_mentions: list[Mapping[str, object]] | None = None,
) -> str:
    if not latest_mention:
        return ""

    title = str(_mapping_value(latest_mention, "material_title") or "").strip()
    if not title:
        return ""

    recent_mentions = list(recent_mentions or [])
    recent_keys = [
        str(_mapping_value(item, "material_key") or "").strip()
        for item in recent_mentions
        if str(_mapping_value(item, "material_key") or "").strip()
    ]
    latest_key = str(_mapping_value(latest_mention, "material_key") or "").strip()
    dominant_now = latest_key and Counter(recent_keys).get(latest_key, 0) >= 2

    prefix = f"Сейчас у ученика явно доминирует {title}. " if dominant_now else ""

    page_from = _mapping_value(latest_mention, "page_from")
    page_to = _mapping_value(latest_mention, "page_to")
    if page_from:
        page_label = f"стр. {page_from}-{page_to}" if page_to and page_to != page_from else f"стр. {page_from}"
        return prefix + f"Ориентир: продолжение после {page_label} в {title}."

    for key in ("unit_label", "chapter_label", "lesson_label"):
        value = str(_mapping_value(latest_mention, key) or "").strip()
        if value:
            return prefix + f"Ориентир: продолжение после {value} в {title}."

    exercise_label = str(_mapping_value(latest_mention, "exercise_label") or "").strip()
    if exercise_label:
        return prefix + f"Ориентир: продолжение после {exercise_label} в {title}."

    return prefix + f"Последним у этого ученика шёл {title}; логичнее всего продолжать его."


def _extract_material_title(block: str, *, has_progress: bool) -> tuple[str, str]:
    fragments = [_clean_fragment(item) for item in _split_fragments(block)]
    fragments = [fragment for fragment in fragments if fragment]

    book_fragment = next((fragment for fragment in fragments if _BOOK_KEYWORD_RE.search(fragment)), "")
    title_fragment = next(
        (
            fragment
            for fragment in fragments
            if _is_title_like_fragment(fragment) and not _looks_like_progress(fragment)
        ),
        "",
    )

    if book_fragment:
        if title_fragment and normalize_material_key(title_fragment) not in normalize_material_key(book_fragment):
            display = f"{book_fragment} — {title_fragment}"
            key_source = title_fragment
        else:
            display = book_fragment
            key_source = book_fragment
        return display, normalize_material_key(key_source)

    if title_fragment and has_progress:
        return title_fragment, normalize_material_key(title_fragment)

    return "", ""


def _extract_progress(block: str) -> dict[str, object]:
    page_match = _PAGE_RE.search(block)
    page_from = int(page_match.group(1)) if page_match else None
    page_to = int(page_match.group(2)) if page_match and page_match.group(2) else None

    return {
        "page_from": page_from,
        "page_to": page_to,
        "unit_label": _label_from_match("Unit", _UNIT_RE.search(block)),
        "chapter_label": _label_from_match("Chapter", _CHAPTER_RE.search(block)),
        "lesson_label": _label_from_match("Lesson", _LESSON_RE.search(block)),
        "exercise_label": _extract_exercise_label(block),
    }


def _label_from_match(prefix: str, match: re.Match[str] | None) -> str | None:
    if not match:
        return None
    value = " ".join((match.group(1) or "").split())
    return f"{prefix} {value}".strip() if value else None


def _extract_exercise_label(block: str) -> str | None:
    match = _EXERCISE_HEAD_RE.search(block)
    if not match:
        return None
    value = " ".join((match.group(1) or "").split())
    value = re.split(r"(?i)\s*(?:[-–—]|,)?\s*(?:pages?|pp?\.?|стр\.?|unit|chapter|lesson)\b", value, maxsplit=1)[0]
    value = re.split(r"[.;]", value, maxsplit=1)[0].strip(" -–—,")
    return f"Ex. {value}".strip() if value else None


def _split_fragments(block: str) -> list[str]:
    return re.split(r"\.\s+(?=[A-ZА-ЯЁ0-9])|[;\n]+", block)


def _looks_like_progress(fragment: str) -> bool:
    lowered = fragment.lower()
    return bool(_PROGRESS_RE.search(fragment)) or lowered.startswith("pages") or lowered.startswith("page")


def _is_title_like_fragment(fragment: str) -> bool:
    if not fragment or _IGNORE_RESOURCE_RE.search(fragment) or _looks_like_progress(fragment):
        return False

    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9’'’-]*", fragment)
    if not tokens or len(tokens) > 6:
        return False

    uppercase_like = 0
    numeric_like = 0
    for token in tokens:
        normalized = token.strip(".,;:!?()[]{}")
        if not normalized:
            continue
        if normalized.isdigit() or re.fullmatch(r"[A-Ca-c]\d", normalized) or re.fullmatch(r"[Bb]\d", normalized):
            numeric_like += 1
            continue
        first = normalized[0]
        if first.isupper():
            uppercase_like += 1
            continue
        if normalized.lower() in _TITLE_CONNECTORS:
            continue
        return False

    return uppercase_like >= 2 or (uppercase_like >= 1 and numeric_like >= 1)


def _clean_fragment(value: str | None) -> str:
    if not value:
        return ""
    cleaned = str(value).strip()
    cleaned = re.sub(r"^\s*(?:\d+[\).]?|[-•])\s*", "", cleaned)
    cleaned = cleaned.strip(" \t\r\n-–—.,;:")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()
