"""Implement fixed-size and structure-aware chunking."""
import re

from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split a page into character windows with exact overlap."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Expected size > 0 and 0 <= overlap < size")

    text = page.text.strip()
    chunks = []
    for start in range(0, len(text), size - overlap):
        end = start + size
        window = text[start:end]
        if window.strip():
            chunks.append(_make_chunk(page, "fixed", len(chunks), window))
        if end >= len(text):
            break
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Pack whole paragraphs when possible and split oversized paragraphs."""
    if max_size <= 0:
        raise ValueError("Expected max_size > 0")

    chunks = []
    current = ""
    for paragraph in re.split(r"\n(?:[^\S\n]*\n)+", page.text):
        remaining = paragraph.strip()
        if not remaining:
            continue

        separator_size = 2 if current else 0
        if current and len(current) + separator_size + len(remaining) > max_size:
            chunks.append(_make_chunk(page, "paragraph", len(chunks), current))
            current = ""

        while len(remaining) > max_size:
            end = _split_point(remaining, max_size)
            chunks.append(_make_chunk(page, "paragraph", len(chunks), remaining[:end].rstrip()))
            remaining = remaining[end:].lstrip()

        current = f"{current}\n\n{remaining}" if current else remaining

    if current:
        chunks.append(_make_chunk(page, "paragraph", len(chunks), current))
    return chunks


def _split_point(text: str, limit: int) -> int:
    """Prefer the last sentence break, then the last word break in the window."""
    window = text[:limit + 1]
    sentence_breaks = list(re.finditer(r"""[.!?](?:["'”’)]*)\s""", window))
    if sentence_breaks:
        return sentence_breaks[-1].end() - 1

    word_breaks = list(re.finditer(r"\s+", window))
    if word_breaks:
        return word_breaks[-1].start()
    return limit


def _make_chunk(page: DocumentPage, method: str, index: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"{page.document_id}:{page.page}:{method}:{index}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=page.metadata.copy(),
    )
