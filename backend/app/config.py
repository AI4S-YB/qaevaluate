from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
BACKEND_DATA_DIR = ROOT_DIR / "backend" / "data"
SCHEMA_PATH = ROOT_DIR / "backend" / "app" / "schema.sql"


def normalize_app_env(value: str | None) -> str:
    normalized = (value or "development").strip().lower()
    if normalized in {"prod", "production"}:
        return "production"
    if normalized in {"dev", "development", "local"}:
        return "development"
    return normalized or "development"


APP_ENV = normalize_app_env(os.getenv("QAEVALUATE_ENV"))
IS_DEVELOPMENT = APP_ENV == "development"
IS_PRODUCTION = APP_ENV == "production"

RUNTIME_DATA_DIR = Path(os.getenv("QAEVALUATE_RUNTIME_DIR", str(DATA_DIR / APP_ENV)))
RUNTIME_BACKEND_DATA_DIR = Path(
    os.getenv("QAEVALUATE_BACKEND_DATA_DIR", str(BACKEND_DATA_DIR / APP_ENV))
)

UPLOAD_DIR = RUNTIME_DATA_DIR / "uploads"
EXPORT_DIR = RUNTIME_DATA_DIR / "exports"
QUEUE_DIR = RUNTIME_DATA_DIR / "queue"
DB_PATH = Path(os.getenv("QAEVALUATE_DB_PATH", str(RUNTIME_BACKEND_DATA_DIR / "app.db")))
LLM_CONFIG_SECRETS_PATH = Path(
    os.getenv(
        "QAEVALUATE_LLM_SECRETS_PATH",
        str(RUNTIME_BACKEND_DATA_DIR / "llm_config_secrets.json"),
    )
)
