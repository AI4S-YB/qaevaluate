from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
BACKEND_DATA_DIR = ROOT_DIR / "backend" / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
QUEUE_DIR = DATA_DIR / "queue"
DB_PATH = BACKEND_DATA_DIR / "app.db"
LLM_CONFIG_SECRETS_PATH = BACKEND_DATA_DIR / "llm_config_secrets.json"
SCHEMA_PATH = ROOT_DIR / "backend" / "app" / "schema.sql"
