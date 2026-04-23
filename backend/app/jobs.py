import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from .config import QUEUE_DIR


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def queue_job(job_type: str, payload: dict, job_id: Optional[str] = None) -> str:
    QUEUE_DIR.joinpath("pending").mkdir(parents=True, exist_ok=True)
    job_id = job_id or f"{job_type}_{uuid4().hex}"
    job_path = QUEUE_DIR / "pending" / f"{job_id}.json"
    job_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "type": job_type,
                "payload": payload,
                "meta": {
                    "created_at": now_iso(),
                    "retry_count": 0,
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                    "last_error": None,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return job_id


def _load_job_payload(path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_active_import_job(batch_id: int) -> Optional[str]:
    for status in ("pending", "processing"):
        directory = QUEUE_DIR / status
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            payload = _load_job_payload(path)
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "import":
                continue
            job_payload = payload.get("payload")
            if not isinstance(job_payload, dict):
                continue
            if int(job_payload.get("batch_id") or 0) == int(batch_id):
                job_id = payload.get("job_id")
                if isinstance(job_id, str) and job_id:
                    return job_id
    return None


def queue_unique_import_job(batch_id: int) -> tuple[str, bool]:
    existing_job_id = find_active_import_job(batch_id)
    if existing_job_id:
        return existing_job_id, False
    return queue_job("import", {"batch_id": batch_id}), True
