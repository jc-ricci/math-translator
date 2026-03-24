import aiosqlite
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "storage" / "jobs.db"


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER NOT NULL DEFAULT 0,
                total_chunks INTEGER NOT NULL DEFAULT 0,
                current_chunk INTEGER NOT NULL DEFAULT 0,
                source_lang TEXT NOT NULL DEFAULT 'en',
                target_lang TEXT NOT NULL DEFAULT 'zh',
                filename TEXT NOT NULL DEFAULT '',
                has_pdf INTEGER NOT NULL DEFAULT 0,
                error_msg TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)
        # Migrate existing DBs: add columns if absent
        for col, definition in [("filename", "TEXT NOT NULL DEFAULT ''"),
                                 ("has_pdf",  "INTEGER NOT NULL DEFAULT 0")]:
            try:
                await db.execute(f"ALTER TABLE jobs ADD COLUMN {col} {definition}")
            except Exception:
                pass  # column already exists
        await db.commit()


async def create_job(job_id: str, source_lang: str, target_lang: str,
                     filename: str = "") -> dict:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO jobs (id, status, progress, total_chunks, current_chunk,
               source_lang, target_lang, filename, created_at, updated_at)
               VALUES (?, 'pending', 0, 0, 0, ?, ?, ?, ?, ?)""",
            (job_id, source_lang, target_lang, filename, now, now)
        )
        await db.commit()
    return await get_job(job_id)


async def get_job(job_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_job(job_id: str, **kwargs):
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE jobs SET {fields} WHERE id = ?", values)
        await db.commit()


async def set_error(job_id: str, error_msg: str):
    await update_job(job_id, status="error", error_msg=error_msg)
