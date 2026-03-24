import asyncio
import uuid
import traceback
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
import aiofiles

from database import create_job, update_job, set_error
from services.pdf_to_images import pdf_to_image_batches, PAGES_PER_BATCH
from services.claude_processor import process_batch as vision_ocr_claude
from services.text_extractor import extract_text_pages, is_text_based, make_text_batches, TEXT_BATCH_SIZE
from services.text_translator import translate_text_batch as translate_text_claude
from services.html_renderer import render_html
from services.latex_merger import merge_chunks
from services.compiler import compile_latex
from services.image_extractor import extract_images
from services.openai_translator import (
    translate_text_batch as translate_text_openai,
    translate_vision_batch as translate_vision_openai,
)
from services.cross_validator import merge_translations


router = APIRouter()

STORAGE_ROOT = Path(__file__).parent.parent.parent / "storage"
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def _save_chunks(translated_chunks: list[str], translated_dir: Path) -> list[Path]:
    translated_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for idx, text in enumerate(translated_chunks):
        p = translated_dir / f"chunk_{idx:04d}.mmd"
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    return paths


async def _pipeline(job_id: str, pdf_path: Path, source_lang: str, target_lang: str):
    try:
        import time
        images_dir = STORAGE_ROOT / "images" / job_id
        translated_dir = STORAGE_ROOT / "translated" / job_id
        output_dir = STORAGE_ROOT / "output" / job_id

        # Step 1: 检测 PDF 类型
        print(f"[{job_id[:8]}] 开始：检测PDF类型")
        await update_job(job_id, status="ocr", progress=3)
        text_pages = extract_text_pages(pdf_path)
        use_text_mode = is_text_based(text_pages)
        pages_per_batch = TEXT_BATCH_SIZE if use_text_mode else PAGES_PER_BATCH
        print(f"[{job_id[:8]}] PDF类型：{'文字型' if use_text_mode else '扫描型'}，共{len(text_pages)}页")

        if use_text_mode:
            # ── 文字型 PDF：Claude + GPT 并行翻译，再 Claude 审核合并 ──
            await update_job(job_id, status="ocr", progress=5)
            batches = make_text_batches(text_pages)
            total = len(batches)
            await update_job(job_id, total_chunks=total)
            print(f"[{job_id[:8]}] 文字模式：{total}批，Claude+GPT并行翻译+交叉验证")

            translated_chunks = []
            for idx, batch in enumerate(batches):
                pct_start = 8 + int(idx / total * 68)
                await update_job(job_id, status="translating", progress=pct_start, current_chunk=idx)
                print(f"[{job_id[:8]}] 批次 {idx+1}/{total}：Claude+GPT并行翻译")
                try:
                    claude_result, openai_result = await asyncio.gather(
                        translate_text_claude(batch, source_lang, target_lang),
                        translate_text_openai(batch, source_lang, target_lang),
                    )
                    pct_merge = 8 + int((idx + 0.7) / total * 68)
                    await update_job(job_id, status="validating", progress=pct_merge, current_chunk=idx + 1)
                    print(f"[{job_id[:8]}] 批次 {idx+1}/{total}：Claude审核合并")
                    final = await merge_translations(
                        claude_result, openai_result, source_lang, target_lang,
                        original_text=batch,
                    )
                except Exception as e:
                    print(f"[{job_id[:8]}] 批次 {idx+1}/{total}：GPT不可用({e.__class__.__name__})，降级为Claude单独翻译")
                    await update_job(job_id, status="translating", progress=pct_start + 2, current_chunk=idx)
                    final = await translate_text_claude(batch, source_lang, target_lang)
                    await update_job(job_id, status="translating", progress=pct_start + 5, current_chunk=idx + 1)
                translated_chunks.append(final)

        else:
            # ── 扫描型 PDF：Claude + GPT 视觉并行，再 Claude 审核合并 ──
            print(f"[{job_id[:8]}] 扫描模式：渲染页面图片（200 DPI）...")
            batches = pdf_to_image_batches(pdf_path, images_dir)
            total = len(batches)
            await update_job(job_id, total_chunks=total)
            print(f"[{job_id[:8]}] 扫描模式：{total}批，Claude+GPT视觉并行OCR+翻译+交叉验证")

            translated_chunks = []
            for idx, batch in enumerate(batches):
                pct_start = 8 + int(idx / total * 68)
                await update_job(job_id, status="translating", progress=pct_start, current_chunk=idx)
                print(f"[{job_id[:8]}] 批次 {idx+1}/{total}：Claude+GPT视觉并行")
                try:
                    claude_result, openai_result = await asyncio.gather(
                        vision_ocr_claude(batch, source_lang, target_lang),
                        translate_vision_openai(batch, source_lang, target_lang),
                    )
                    pct_merge = 8 + int((idx + 0.7) / total * 68)
                    await update_job(job_id, status="validating", progress=pct_merge, current_chunk=idx + 1)
                    print(f"[{job_id[:8]}] 批次 {idx+1}/{total}：Claude审核合并")
                    final = await merge_translations(
                        claude_result, openai_result, source_lang, target_lang,
                    )
                except Exception as e:
                    print(f"[{job_id[:8]}] 批次 {idx+1}/{total}：GPT不可用({e.__class__.__name__})，降级为Claude单独OCR+翻译")
                    await update_job(job_id, status="translating", progress=pct_start + 2, current_chunk=idx)
                    final = await vision_ocr_claude(batch, source_lang, target_lang)
                    await update_job(job_id, status="translating", progress=pct_start + 5, current_chunk=idx + 1)
                translated_chunks.append(final)

        # Step 2: 提取 PDF 中的嵌入图片
        await update_job(job_id, status="compiling", progress=88)
        images_out_dir = output_dir / "images"
        pdf_images = extract_images(pdf_path, images_out_dir)

        # Step 3: 保存 Markdown
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{job_id}_translated.md"
        md_path.write_text("\n\n---\n\n".join(translated_chunks), encoding="utf-8")

        # Step 4: 生成 HTML
        html_path = output_dir / f"{job_id}_translated.html"
        render_html(translated_chunks, html_path, images=pdf_images, pages_per_batch=pages_per_batch)

        # Step 4: 生成 LaTeX
        await update_job(job_id, status="compiling", progress=92)
        translated_paths = _save_chunks(translated_chunks, translated_dir)
        template_path = TEMPLATES_DIR / "base.tex"
        latex_output_dir = output_dir / "latex"
        main_tex = merge_chunks(
            translated_paths, template_path, latex_output_dir, job_id,
            pdf_images=pdf_images, pages_per_batch=pages_per_batch,
        )

        # Step 5: 编译 PDF（失败不阻断完成）
        await update_job(job_id, status="compiling", progress=95)
        has_pdf = 0
        try:
            await compile_latex(main_tex, job_id)
            has_pdf = 1
        except Exception as latex_err:
            print(f"[{job_id[:8]}] PDF编译失败（不阻断）：{latex_err}")

        await update_job(job_id, status="done", progress=100, has_pdf=has_pdf)

    except Exception as exc:
        tb = traceback.format_exc()
        # 提取最后一行作为简洁错误摘要
        last_line = [l.strip() for l in tb.strip().splitlines() if l.strip()][-1]
        await set_error(job_id, f"{last_line}\n\n---\n{tb}")


@router.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_lang: str = Form("en"),
    target_lang: str = Form("zh"),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只接受PDF文件")

    job_id = str(uuid.uuid4())
    upload_dir = STORAGE_ROOT / "uploads" / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / "source.pdf"

    size = 0
    async with aiofiles.open(pdf_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="文件超过500MB限制")
            await f.write(chunk)

    await create_job(job_id, source_lang, target_lang, filename=file.filename or "")
    background_tasks.add_task(_pipeline, job_id, pdf_path, source_lang, target_lang)

    return {"job_id": job_id}
