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
