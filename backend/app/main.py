from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import APP_ENV, DB_PATH, EXPORT_DIR, QUEUE_DIR, UPLOAD_DIR
from .db import init_db
from .routes.admin import news_router, router as admin_router
from .routes.generate import router as generate_router
from .routes.applications import router as applications_router
from .routes.auth import router as auth_router
from .routes.expert import router as expert_router
from .routes.llm import router as llm_router
from .routes.me import router as me_router
from .routes.model_trial import router as model_trial_router

app = FastAPI(title="QA Evaluate API", version="0.1.0")

# allow_credentials=True 不能与 allow_origins=["*"] 同时使用；浏览器会拒绝响应。
# 本应用用 Bearer Token（Authorization 头），不依赖跨域 Cookie，故关闭 credentials。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    print(f"[qaevaluate] startup env={APP_ENV} db={DB_PATH}")
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
app.include_router(model_trial_router)
app.include_router(admin_router)
app.include_router(news_router)
app.include_router(generate_router)
