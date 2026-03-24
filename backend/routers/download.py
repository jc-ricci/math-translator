from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from database import get_job

router = APIRouter()

STORAGE_ROOT = Path(__file__).parent.parent.parent / "storage"


def _require_done(job):
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="任务尚未完成")


@router.get("/download/{job_id}/html")
async def download_html(job_id: str):
    job = await get_job(job_id)
    _require_done(job)
    path = STORAGE_ROOT / "output" / job_id / f"{job_id}_translated.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="HTML文件不存在")
    return FileResponse(str(path), media_type="text/html; charset=utf-8",
                        filename=f"translated_{job_id[:8]}.html")


@router.get("/download/{job_id}/md")
async def download_md(job_id: str):
    job = await get_job(job_id)
    _require_done(job)
    path = STORAGE_ROOT / "output" / job_id / f"{job_id}_translated.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Markdown文件不存在")
    return FileResponse(str(path), media_type="text/markdown; charset=utf-8",
                        filename=f"translated_{job_id[:8]}.md")


@router.get("/download/{job_id}/tex")
async def download_tex(job_id: str):
    job = await get_job(job_id)
    _require_done(job)
    path = STORAGE_ROOT / "output" / job_id / "latex" / "main.tex"
    if not path.exists():
        raise HTTPException(status_code=404, detail="LaTeX文件不存在")
    return FileResponse(str(path), media_type="text/plain; charset=utf-8",
                        filename=f"translated_{job_id[:8]}.tex")


@router.get("/download/{job_id}/pdf")
async def download_pdf(job_id: str):
    job = await get_job(job_id)
    _require_done(job)
    path = STORAGE_ROOT / "output" / job_id / "latex" / f"{job_id}_translated.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF尚未生成或编译失败")
    return FileResponse(str(path), media_type="application/pdf",
                        filename=f"translated_{job_id[:8]}.pdf")


@router.get("/preview/{job_id}", response_class=HTMLResponse)
async def preview_html(job_id: str):
    job = await get_job(job_id)
    _require_done(job)
    path = STORAGE_ROOT / "output" / job_id / f"{job_id}_translated.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="输出文件不存在")
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


# Legacy redirect for old /download/{job_id} URL
@router.get("/download/{job_id}")
async def download_default(job_id: str):
    return await download_html(job_id)
