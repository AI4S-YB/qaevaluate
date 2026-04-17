from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
QUEUE_DIR = DATA_DIR / "queue"
DB_PATH = ROOT_DIR / "backend" / "data" / "app.db"
SCHEMA_PATH = ROOT_DIR / "backend" / "app" / "schema.sql"

