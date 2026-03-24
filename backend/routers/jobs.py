import aiosqlite
from fastapi import APIRouter, HTTPException
from database import get_job, update_job, DB_PATH

router = APIRouter()

STATUS_LABELS = {
    "pending":    "等待处理",
    "ocr":        "页面渲染中",
    "translating":"Claude+GPT并行翻译中",
    "validating": "Claude交叉审核合并中",
    "compiling":  "生成网页中",
    "done":       "完成",
    "error":      "出错",
    "cancelled":  "已取消",
}

LANG_NAMES = {"de": "德语", "fr": "法语", "en": "英语", "zh": "中文"}


def _format_job(job: dict) -> dict:
    error_msg = job.get("error_msg") or ""
    # 首行作为摘要（格式为 "最后一行错误\n\n---\n完整traceback"）
    error_summary = error_msg.split("\n\n---\n")[0] if "\n\n---\n" in error_msg else error_msg
    error_detail  = error_msg.split("\n\n---\n")[1] if "\n\n---\n" in error_msg else ""
    return {
        "job_id":            job["id"],
        "status":            job["status"],
        "status_label":      STATUS_LABELS.get(job["status"], job["status"]),
        "progress":          job["progress"],
        "total_chunks":      job["total_chunks"],
        "current_chunk":     job["current_chunk"],
        "source_lang":       job["source_lang"],
        "target_lang":       job["target_lang"],
        "source_lang_label": LANG_NAMES.get(job["source_lang"], job["source_lang"]),
        "filename":          job.get("filename") or "",
        "has_pdf":           bool(job.get("has_pdf", 0)),
        "error_summary":     error_summary,
        "error_detail":      error_detail,
        "created_at":        job["created_at"],
        "updated_at":        job["updated_at"],
    }


@router.get("/jobs")
async def list_jobs():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 50"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_format_job(dict(r)) for r in rows]


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _format_job(job)


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job["status"] in ("done", "error", "cancelled"):
        raise HTTPException(status_code=400, detail="任务已结束，无法取消")
    await update_job(job_id, status="cancelled",
                     error_msg="用户手动取消")
    return {"ok": True}
