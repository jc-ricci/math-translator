import fitz  # PyMuPDF — renders pages without poppler
from pathlib import Path

PAGES_PER_BATCH = 3   # pages sent to Claude per API call
DPI = 200             # resolution for OCR quality — higher = better formula recognition


def pdf_to_image_batches(pdf_path: Path, output_dir: Path) -> list[list[Path]]:
    """Render each PDF page to PNG and group into batches.

    Returns list of batches, each batch is a list of image paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    all_images: list[Path] = []

    mat = fitz.Matrix(DPI / 72, DPI / 72)
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_path = output_dir / f"page_{page_num:04d}.png"
        pix.save(str(img_path))
        all_images.append(img_path)

    doc.close()

    batches = [
        all_images[i: i + PAGES_PER_BATCH]
        for i in range(0, len(all_images), PAGES_PER_BATCH)
    ]
    return batches


def count_pages(pdf_path: Path) -> int:
    doc = fitz.open(str(pdf_path))
    n = len(doc)
    doc.close()
    return n
