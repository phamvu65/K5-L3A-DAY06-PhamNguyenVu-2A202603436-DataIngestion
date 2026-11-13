"""Extract and normalize PDF text while retaining physical page numbers."""
import json
import logging
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

logger = logging.getLogger(__name__)


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    *,
    page_numbers: Iterable[int] | None = None,
) -> list[DocumentPage]:
    """Read selected 1-based PDF pages and log any that cannot be read."""
    reader = PdfReader(path)
    page_count = len(reader.pages)
    selected = range(1, page_count + 1) if page_numbers is None else page_numbers
    pages = []
    for number in dict.fromkeys(selected):
        if not 1 <= number <= page_count:
            raise ValueError(f"{path}: PDF page {number} is outside 1–{page_count}")
        try:
            text = normalize_text(reader.pages[number - 1].extract_text() or "")
        except Exception:
            logger.exception("Could not extract %s page %d", path, number)
            continue
        if not text:
            logger.warning("No text extracted from %s page %d", path, number)
            continue
        pages.append(DocumentPage(document_id, source, number, text))
    return pages


def load_corpus(manifest_path: Path) -> list[DocumentPage]:
    """Load the manifest's selected pages and attach chapter and print-page metadata."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages = []
    for document in manifest["documents"]:
        entries = {entry["page"]: entry for entry in document["pages"]}
        pdf_path = manifest_path.parent / document["source_path_or_url"]
        extracted = load_pdf(
            pdf_path, document["source_id"], document["source_url"], page_numbers=entries
        )
        missing = entries.keys() - {page.page for page in extracted}
        if missing:
            raise ValueError(f"{pdf_path}: could not read selected pages {sorted(missing)}")
        for page in extracted:
            entry = entries[page.page]
            page.metadata.update(chapter=entry["chapter"], printed_page=entry["printed_page"])
        pages.extend(extracted)
    return pages


def normalize_text(text: str) -> str:
    """Expand ligatures and join wrapped lines, preserving blank-line breaks."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00ad", "")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"[\x00-\x08\x0e-\x1f\x7f]", "", text)
    paragraphs = re.split(r"\n(?: *\n)+", text)
    return "\n\n".join(" ".join(paragraph.split()) for paragraph in paragraphs if paragraph.strip())
