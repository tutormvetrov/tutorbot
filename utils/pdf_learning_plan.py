from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:  # PyMuPDF exposes the modern name in current versions and fitz in older code.
    import pymupdf
except ImportError:  # pragma: no cover - depends on installed package shape
    import fitz as pymupdf  # type: ignore


@dataclass
class ParsedLearningPlan:
    text: str
    summary: str
    status: str
    warnings: list[str]
    pages_count: int
    tables_count: int


def _normalize_text(value: str) -> str:
    lines = []
    for raw_line in value.replace("\xa0", " ").replace("\u202f", " ").splitlines():
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def _table_to_text(rows: list[list[object]]) -> str:
    rendered = []
    for row in rows:
        values = [" ".join(str(cell or "").split()) for cell in row]
        if any(values):
            rendered.append(" | ".join(values))
    return "\n".join(rendered)


def _build_summary(text: str, limit: int = 900) -> str:
    lines = [line.strip("•-–— \t") for line in text.splitlines() if line.strip()]
    selected: list[str] = []
    for line in lines:
        if len(line) < 4:
            continue
        selected.append(line)
        if len(selected) >= 7:
            break
    summary = "\n".join(f"• {line}" for line in selected)
    if len(summary) <= limit:
        return summary
    return summary[: limit - 1].rstrip() + "…"


def parse_learning_plan_pdf(path: str | Path) -> ParsedLearningPlan:
    warnings: list[str] = []
    chunks: list[str] = []
    tables_count = 0

    with pymupdf.open(str(path)) as doc:
        pages_count = len(doc)
        for index, page in enumerate(doc, start=1):
            page_chunks: list[str] = []
            try:
                text = page.get_text("text", sort=True)
            except TypeError:
                text = page.get_text()
            clean_text = _normalize_text(text or "")
            if clean_text:
                page_chunks.append(clean_text)

            find_tables = getattr(page, "find_tables", None)
            if callable(find_tables):
                try:
                    table_finder = find_tables()
                    for table in getattr(table_finder, "tables", []) or []:
                        rows = table.extract()
                        table_text = _table_to_text(rows or [])
                        if table_text:
                            tables_count += 1
                            page_chunks.append(table_text)
                except Exception:
                    warnings.append(f"Таблицы на стр. {index} не удалось разобрать автоматически.")

            if page_chunks:
                chunks.append(f"Стр. {index}\n" + "\n".join(page_chunks))
            else:
                warnings.append(f"На стр. {index} не найден выделяемый текст.")

    text = "\n\n".join(chunks).strip()
    if not text:
        warnings.append("В PDF не найден выделяемый текст. Для v1 нужен текстовый PDF или ручная выжимка.")
        return ParsedLearningPlan("", "", "needs_manual_summary", warnings, pages_count, tables_count)

    if len(text) < 80:
        warnings.append("Текста извлечено мало. Проверьте preview и при необходимости замените выжимку вручную.")
        status = "needs_manual_summary"
    else:
        status = "ok"

    return ParsedLearningPlan(
        text=text,
        summary=_build_summary(text),
        status=status,
        warnings=warnings,
        pages_count=pages_count,
        tables_count=tables_count,
    )
