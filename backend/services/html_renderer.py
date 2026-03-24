import re
from pathlib import Path

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>翻译结果</title>
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [['$', '$']],
        displayMath: [['$$', '$$']],
        packages: {'[+]': ['ams']},
        tags: 'ams',
      },
      options: { skipHtmlTags: ['script','noscript','style','textarea','pre'] },
    };
  </script>
  <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: "Songti SC", "SimSun", "Source Han Serif CN", Georgia, serif;
      font-size: 16px;
      line-height: 1.85;
      max-width: 860px;
      margin: 0 auto;
      padding: 3rem 2rem;
      color: #1a1a1a;
      background: #fafafa;
    }
    h1 { font-size: 1.7rem; margin: 2rem 0 1rem; border-bottom: 2px solid #333; padding-bottom: 0.4rem; }
    h2 { font-size: 1.4rem; margin: 1.8rem 0 0.8rem; }
    h3 { font-size: 1.15rem; margin: 1.4rem 0 0.6rem; }
    p  { margin: 0.7rem 0; text-indent: 2em; }
    hr { border: none; border-top: 1px solid #ddd; margin: 2rem 0; }

    .theorem-box {
      border-left: 4px solid #4361ee;
      background: #f0f3ff;
      padding: 0.8rem 1.2rem;
      margin: 1.2rem 0;
      border-radius: 0 6px 6px 0;
    }
    .theorem-box .label {
      font-weight: bold;
      color: #4361ee;
      margin-right: 0.5rem;
    }
    .proof-box {
      border-left: 4px solid #888;
      background: #f8f8f8;
      padding: 0.8rem 1.2rem;
      margin: 1rem 0;
      border-radius: 0 6px 6px 0;
    }
    .proof-box .label {
      font-style: italic;
      color: #555;
      margin-right: 0.5rem;
    }
    .definition-box {
      border-left: 4px solid #06d6a0;
      background: #f0fff8;
      padding: 0.8rem 1.2rem;
      margin: 1.2rem 0;
      border-radius: 0 6px 6px 0;
    }
    .definition-box .label {
      font-weight: bold;
      color: #06856a;
      margin-right: 0.5rem;
    }

    @media print {
      body { background: white; max-width: 100%; }
    }
  </style>
</head>
<body>
%%CONTENT%%
</body>
</html>"""

THEOREM_PATTERNS = [
    (r'\*\*定理\*\*\s*(.*?)(?=\n\*\*|\n##|\n---|$)', 'theorem-box', '定理'),
    (r'\*\*引理\*\*\s*(.*?)(?=\n\*\*|\n##|\n---|$)', 'theorem-box', '引理'),
    (r'\*\*命题\*\*\s*(.*?)(?=\n\*\*|\n##|\n---|$)', 'theorem-box', '命题'),
    (r'\*\*推论\*\*\s*(.*?)(?=\n\*\*|\n##|\n---|$)', 'theorem-box', '推论'),
    (r'\*\*定义\*\*\s*(.*?)(?=\n\*\*|\n##|\n---|$)', 'definition-box', '定义'),
    (r'\*\*证明\*\*\s*(.*?)(?=\n\*\*|\n##|\n---|$)', 'proof-box', '证明'),
]


def _escape_html(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def markdown_to_html(text: str) -> str:
    """Convert Markdown+LaTeX to HTML. Math is left for MathJax."""

    # Protect math blocks from further processing
    math_blocks: list[str] = []

    def save_math(m: re.Match) -> str:
        math_blocks.append(m.group(0))
        return f"\x00MATH{len(math_blocks)-1}\x00"

    # Display math first, then inline
    text = re.sub(r'\$\$[\s\S]+?\$\$', save_math, text)
    text = re.sub(r'\$[^$\n]+?\$', save_math, text)
    # Also protect \begin...\end blocks
    text = re.sub(r'\\begin\{[^}]+\}[\s\S]*?\\end\{[^}]+\}', save_math, text)

    lines = text.splitlines()
    html_parts: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Horizontal rule / page separator
        if re.match(r'^---+$', line.strip()):
            html_parts.append('<hr>')
            i += 1
            continue

        # Headings
        m = re.match(r'^(#{1,4})\s+(.*)', line)
        if m:
            level = len(m.group(1))
            content = m.group(2)
            html_parts.append(f'<h{level}>{content}</h{level}>')
            i += 1
            continue

        # Theorem-style bold labels — collect multi-line content
        matched_box = False
        for pattern, css_class, label in THEOREM_PATTERNS:
            m = re.match(r'^\*\*' + re.escape(label) + r'\*\*\s*(.*)', line)
            if m:
                body_lines = [m.group(1)]
                i += 1
                # Collect continuation lines until blank line or new section
                while i < len(lines) and lines[i].strip() and not lines[i].startswith('#') and not lines[i].startswith('**'):
                    body_lines.append(lines[i])
                    i += 1
                body = ' '.join(body_lines)
                html_parts.append(
                    f'<div class="{css_class}"><span class="label">{label}</span>{body}</div>'
                )
                matched_box = True
                break
        if matched_box:
            continue

        # Bold / italic inline
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)

        # Non-empty line → paragraph
        if line.strip():
            html_parts.append(f'<p>{line}</p>')
        else:
            html_parts.append('')  # blank line

        i += 1

    result = '\n'.join(html_parts)

    # Restore math
    for idx, math in enumerate(math_blocks):
        result = result.replace(f'\x00MATH{idx}\x00', math)

    return result


def _images_for_batch(
    batch_idx: int,
    pages_per_batch: int,
    images: list[dict],
) -> list[dict]:
    """Return images belonging to the pages covered by this batch."""
    start_page = batch_idx * pages_per_batch
    end_page = start_page + pages_per_batch
    return [img for img in images if start_page <= img["page"] < end_page]


def _img_tag(img: dict, output_dir: Path) -> str:
    """Render an <img> tag with base64-encoded image data."""
    import base64
    suffix = img["path"].suffix.lstrip(".")
    media = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    b64 = base64.b64encode(img["path"].read_bytes()).decode()
    caption = f"图（第 {img['page'] + 1} 页）"
    return (
        f'<figure class="pdf-figure">'
        f'<img src="data:image/{media};base64,{b64}" alt="{caption}">'
        f'<figcaption>{caption}</figcaption>'
        f'</figure>'
    )


def _replace_figure_placeholders(html: str, batch_imgs: list[dict]) -> str:
    """Replace [图N: caption] placeholders with actual embedded images."""
    import base64
    for i, img in enumerate(batch_imgs):
        suffix = img["path"].suffix.lstrip(".")
        media = "jpeg" if suffix in ("jpg", "jpeg") else suffix
        b64 = base64.b64encode(img["path"].read_bytes()).decode()
        # Match [图N: ...] or [图: ...] patterns
        pattern = re.compile(r'\[图\s*\d*\s*:?\s*([^\]]*)\]')
        def make_tag(m, _b64=b64, _media=media):
            caption = m.group(1).strip() or f"第 {img['page']+1} 页插图"
            return (
                f'<figure class="pdf-figure">'
                f'<img src="data:image/{_media};base64,{_b64}" alt="{caption}">'
                f'<figcaption>{caption}</figcaption>'
                f'</figure>'
            )
        html, n = pattern.subn(make_tag, html, count=1)
        if n == 0:
            # No placeholder found — append image at end of chunk
            caption = f"第 {img['page']+1} 页插图"
            html += (
                f'<figure class="pdf-figure">'
                f'<img src="data:image/{media};base64,{b64}" alt="{caption}">'
                f'<figcaption>{caption}</figcaption>'
                f'</figure>'
            )
    return html


def render_html(
    translated_chunks: list[str],
    output_path: Path,
    images: list[dict] | None = None,
    pages_per_batch: int = 2,
) -> Path:
    """Merge translated chunks and write HTML file.

    images: list of dicts from image_extractor.extract_images()
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    images = images or []

    parts = []
    for batch_idx, chunk in enumerate(translated_chunks):
        chunk_html = markdown_to_html(chunk)
        batch_imgs = _images_for_batch(batch_idx, pages_per_batch, images)
        if batch_imgs:
            chunk_html = _replace_figure_placeholders(chunk_html, batch_imgs)
        parts.append(chunk_html)
        parts.append('<hr>')

    body_html = '\n'.join(parts)
    html = HTML_TEMPLATE.replace('%%CONTENT%%', body_html)
    output_path.write_text(html, encoding='utf-8')
    return output_path
