import fitz
from pathlib import Path

MIN_CHARS_PER_PAGE = 100  # below this → treat page as scanned
TEXT_BATCH_SIZE = 10      # pages per batch for text-based PDFs


def extract_text_pages(pdf_path: Path) -> list[str]:
    """Extract text from each page. Returns list of page texts."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for page in doc:
        text = page.get_text("text").strip()
        pages.append(text)
    doc.close()
    return pages


def is_text_based(pages: list[str], sample: int = 10) -> bool:
    """Return True if the PDF has extractable text (not a pure scan)."""
    sample_pages = pages[:sample]
    avg_chars = sum(len(p) for p in sample_pages) / max(len(sample_pages), 1)
    return avg_chars >= MIN_CHARS_PER_PAGE


def make_text_batches(pages: list[str]) -> list[str]:
    """Group pages into TEXT_BATCH_SIZE-page batches.

    Each batch is a single string with page separators.
    """
    batches = []
    for i in range(0, len(pages), TEXT_BATCH_SIZE):
        chunk_pages = pages[i: i + TEXT_BATCH_SIZE]
        batch_text = "\n\n%%PAGE_BREAK%%\n\n".join(
            f"[第 {i + j + 1} 页]\n{text}" for j, text in enumerate(chunk_pages)
        )
        batches.append(batch_text)
    return batches
