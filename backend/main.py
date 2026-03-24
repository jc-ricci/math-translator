from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from database import init_db
from routers import upload, jobs, download


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="数学文献PDF翻译系统", lifespan=lifespan)

app.include_router(upload.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(download.router, prefix="/api")

frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(frontend_dir / "index.html"))
