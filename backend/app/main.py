from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import EXPORT_DIR, QUEUE_DIR, UPLOAD_DIR
from .db import init_db
from .routes.admin import router as admin_router
from .routes.applications import router as applications_router
from .routes.auth import router as auth_router
from .routes.expert import router as expert_router
from .routes.llm import router as llm_router
from .routes.me import router as me_router

app = FastAPI(title="QA Evaluate API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    for path in (
        UPLOAD_DIR,
        EXPORT_DIR,
        QUEUE_DIR / "pending",
        QUEUE_DIR / "processing",
        QUEUE_DIR / "done",
        QUEUE_DIR / "failed",
    ):
        path.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    return {"code": 0, "message": "ok", "data": {"status": "healthy"}}


app.include_router(auth_router)
app.include_router(applications_router)
app.include_router(me_router)
app.include_router(expert_router)
app.include_router(llm_router)
app.include_router(admin_router)
