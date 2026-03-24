import fitz
import hashlib
from pathlib import Path


def extract_images(pdf_path: Path, output_dir: Path) -> list[dict]:
    """Extract embedded images from PDF.

    Returns list of dicts: {path, page, index, width, height}
    sorted by (page, vertical position on page).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    results = []
    seen_hashes: set[str] = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue

            img_bytes = base_image["image"]
            ext = base_image["ext"]  # png / jpeg / etc.

            # Skip tiny images (icons, decorations) — less than 50x50
            w, h = base_image.get("width", 0), base_image.get("height", 0)
            if w < 50 or h < 50:
                continue

            # Deduplicate by content hash
            digest = hashlib.md5(img_bytes).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)

            filename = f"page{page_num:04d}_img{img_index:02d}.{ext}"
            img_path = output_dir / filename
            img_path.write_bytes(img_bytes)

            results.append({
                "path": img_path,
                "filename": filename,
                "page": page_num,
                "index": img_index,
                "width": w,
                "height": h,
            })

    doc.close()
    return results
