import re
import shutil
from pathlib import Path


def mmd_to_latex_body(mmd_text: str) -> str:
    """Convert Nougat .mmd (Markdown+LaTeX) to LaTeX body content.

    Nougat outputs mostly LaTeX-ready content; this handles the Markdown layer.
    """
    lines = mmd_text.splitlines()
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Convert Markdown headings to LaTeX sections
        if line.startswith("#### "):
            result.append(f"\\subsubsection{{{line[5:].strip()}}}")
        elif line.startswith("### "):
            result.append(f"\\subsection{{{line[4:].strip()}}}")
        elif line.startswith("## "):
            result.append(f"\\section{{{line[3:].strip()}}}")
        elif line.startswith("# "):
            result.append(f"\\section{{{line[2:].strip()}}}")
        # Bold text
        elif "**" in line:
            line = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', line)
            result.append(line)
        # Italic text
        elif "*" in line and "\\*" not in line:
            line = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\\textit{\1}', line)
            result.append(line)
        else:
            result.append(line)

        i += 1

    return "\n".join(result)


def merge_chunks(
    translated_paths: list[Path],
    template_path: Path,
    output_dir: Path,
    job_id: str,
    pdf_images: list[dict] | None = None,
    pages_per_batch: int = 2,
) -> Path:
    """Merge translated .mmd chunks into a complete LaTeX file.

    Returns path to the merged main.tex.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # Copy extracted PDF images into latex/images/
    pdf_images = pdf_images or []
    for img in pdf_images:
        shutil.copy2(img["path"], images_dir / img["filename"])

    body_parts = []
    for batch_idx, path in enumerate(translated_paths):
        text = path.read_text(encoding="utf-8")
        latex_body = mmd_to_latex_body(text)

        # Append \includegraphics for images in this batch's pages
        start_page = batch_idx * pages_per_batch
        end_page = start_page + pages_per_batch
        batch_imgs = [
            img for img in pdf_images
            if start_page <= img["page"] < end_page
        ]
        for img in batch_imgs:
            latex_body += (
                f"\n\n\\begin{{figure}}[H]\n"
                f"\\centering\n"
                f"\\includegraphics[max width=\\textwidth]{{images/{img['filename']}}}\n"
                f"\\caption{{第 {img['page'] + 1} 页插图}}\n"
                f"\\end{{figure}}\n"
            )

        body_parts.append(latex_body)

    body = "\n\n\\clearpage\n\n".join(body_parts)

    template = template_path.read_text(encoding="utf-8")
    latex_content = template.replace("%%CONTENT%%", body)

    main_tex = output_dir / "main.tex"
    main_tex.write_text(latex_content, encoding="utf-8")
    return main_tex
