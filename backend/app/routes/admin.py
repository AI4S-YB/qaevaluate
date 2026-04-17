from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_admin
from ..config import QUEUE_DIR, UPLOAD_DIR
from ..db import db_cursor
from ..jobs import queue_job
from ..worker import get_next_job, process_job

router = APIRouter(prefix="/api/admin", tags=["admin"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class ExpertDecisionPayload(BaseModel):
    note: Optional[str] = None


class DispatchPayload(BaseModel):
    application_id: int
    limit: int = 100


class FinalAnswerPayload(BaseModel):
    answer_id: int


class ExportCreatePayload(BaseModel):
    export_type: str = Field(alias="type")
    application_id: Optional[int] = None
    date_from: Optional[str] = Field(default=None, alias="from")
    date_to: Optional[str] = Field(default=None, alias="to")
    file_format: str = Field(default="json", alias="format")


def queue_file(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    error_path = path.with_suffix(".error.txt")
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    error_message = (
        meta.get("last_error")
        or (error_path.read_text(encoding="utf-8").strip() if error_path.exists() else None)
    )
    return {
        "job_id": payload.get("job_id", path.stem),
        "type": payload.get("type", "unknown"),
        "status": path.parent.name,
        "filename": path.name,
        "updated_at": datetime.utcfromtimestamp(path.stat().st_mtime)
        .replace(microsecond=0)
        .isoformat(),
        "payload": payload.get("payload", {}),
        "created_at": meta.get("created_at"),
        "started_at": meta.get("started_at"),
        "completed_at": meta.get("completed_at"),
        "duration_ms": meta.get("duration_ms"),
        "retry_count": meta.get("retry_count", 0),
        "error": error_message,
    }


def iter_queue_jobs(statuses: tuple[str, ...] = ("pending", "processing", "done", "failed")) -> list[dict]:
    jobs: list[dict] = []
    for status in statuses:
        directory = QUEUE_DIR / status
        directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            jobs.append(queue_file(path))
    return jobs


def serialize_export_job(row) -> dict:
    item = dict(row)
    file_path = item.get("file_path")
    item["file_name"] = Path(file_path).name if file_path else None
    return item


@router.get("/dashboard")
def get_dashboard(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        pending_experts = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM users
            WHERE role = 'expert' AND status = 'pending'
            """
        ).fetchone()["count"]
        pending_qas = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM qa_items
            WHERE status = 'active'
            """
        ).fetchone()["count"]
        ongoing_tasks = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM evaluation_tasks
            WHERE status IN ('pending', 'in_progress')
            """
        ).fetchone()["count"]
        disputed_qas = cursor.execute(
            """
            SELECT COUNT(DISTINCT qa_item_id) AS count
            FROM evaluation_tasks
            WHERE task_type = 'dispute_review'
            """
        ).fetchone()["count"]
        total_qas = cursor.execute("SELECT COUNT(*) AS count FROM qa_items").fetchone()["count"]
        reviewed_qas = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM qa_items
            WHERE status = 'reviewed'
            """
        ).fetchone()["count"]
        imported_batches = cursor.execute(
            "SELECT COUNT(*) AS count FROM dataset_batches"
        ).fetchone()["count"]
        application_progress = cursor.execute(
            """
            SELECT
              a.id,
              a.name,
              COUNT(q.id) AS total_qas,
              SUM(CASE WHEN q.status = 'reviewed' THEN 1 ELSE 0 END) AS reviewed_qas
            FROM applications a
            LEFT JOIN qa_items q ON q.application_id = a.id
            GROUP BY a.id, a.name
            ORDER BY a.name ASC
            """
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "metrics": {
                "pending_experts": pending_experts,
                "pending_qas": pending_qas,
                "ongoing_tasks": ongoing_tasks,
                "disputed_qas": disputed_qas,
                "reviewed_qas": reviewed_qas,
                "total_qas": total_qas,
                "imported_batches": imported_batches,
            },
            "application_progress": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "total_qas": row["total_qas"] or 0,
                    "reviewed_qas": row["reviewed_qas"] or 0,
                }
                for row in application_progress
            ],
        },
    }


@router.get("/analytics/summary")
def get_analytics_summary(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        decision_counts = cursor.execute(
            """
            SELECT final_decision, COUNT(*) AS count
            FROM qa_aggregates
            WHERE final_decision IS NOT NULL
            GROUP BY final_decision
            """
        ).fetchall()
        decision_map = {row["final_decision"]: row["count"] for row in decision_counts}
        resolved_total = sum(
            decision_map.get(decision, 0) for decision in ("pass", "rewrite", "fail")
        )

        total_qas = cursor.execute("SELECT COUNT(*) AS count FROM qa_items").fetchone()["count"]
        disputed_qas = cursor.execute(
            """
            SELECT COUNT(DISTINCT qa_item_id) AS count
            FROM evaluation_tasks
            WHERE task_type = 'dispute_review'
            """
        ).fetchone()["count"]
        llm_adoptions = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM evaluation_records
            WHERE adopted_rewrite_answer_id IS NOT NULL
            """
        ).fetchone()["count"]
        total_records = cursor.execute(
            "SELECT COUNT(*) AS count FROM evaluation_records"
        ).fetchone()["count"]
        application_breakdown = cursor.execute(
            """
            SELECT
              a.id,
              a.name,
              COUNT(q.id) AS total_qas,
              SUM(CASE WHEN agg.final_decision = 'pass' THEN 1 ELSE 0 END) AS pass_count,
              SUM(CASE WHEN agg.final_decision = 'rewrite' THEN 1 ELSE 0 END) AS rewrite_count,
              SUM(CASE WHEN agg.final_decision = 'fail' THEN 1 ELSE 0 END) AS fail_count,
              AVG(agg.agreement_score) AS avg_agreement
            FROM applications a
            LEFT JOIN qa_items q ON q.application_id = a.id
            LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
            GROUP BY a.id, a.name
            ORDER BY a.name ASC
            """
        ).fetchall()
        expert_activity = cursor.execute(
            """
            SELECT
              u.id,
              u.full_name,
              COUNT(r.id) AS completed_reviews
            FROM users u
            LEFT JOIN evaluation_records r ON r.expert_user_id = u.id
            WHERE u.role = 'expert'
            GROUP BY u.id, u.full_name
            ORDER BY completed_reviews DESC, u.id ASC
            LIMIT 5
            """
        ).fetchall()

    pass_rate = (decision_map.get("pass", 0) / resolved_total * 100) if resolved_total else 0.0
    rewrite_rate = (
        decision_map.get("rewrite", 0) / resolved_total * 100
    ) if resolved_total else 0.0
    dispute_rate = (disputed_qas / total_qas * 100) if total_qas else 0.0
    llm_adoption_rate = (llm_adoptions / total_records * 100) if total_records else 0.0

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "metrics": {
                "pass_rate": round(pass_rate, 1),
                "rewrite_rate": round(rewrite_rate, 1),
                "dispute_rate": round(dispute_rate, 1),
                "llm_adoption_rate": round(llm_adoption_rate, 1),
            },
            "application_breakdown": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "total_qas": row["total_qas"] or 0,
                    "pass_count": row["pass_count"] or 0,
                    "rewrite_count": row["rewrite_count"] or 0,
                    "fail_count": row["fail_count"] or 0,
                    "avg_agreement": round(row["avg_agreement"], 2)
                    if row["avg_agreement"] is not None
                    else None,
                }
                for row in application_breakdown
            ],
            "top_experts": [
                {
                    "id": row["id"],
                    "full_name": row["full_name"],
                    "completed_reviews": row["completed_reviews"] or 0,
                }
                for row in expert_activity
            ],
        },
    }


@router.get("/jobs")
def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin),
):
    jobs = iter_queue_jobs()
    if status:
        jobs = [job for job in jobs if job["status"] == status]
    if job_type:
        jobs = [job for job in jobs if job["type"] == job_type]
    summary = {
        "pending": sum(1 for job in jobs if job["status"] == "pending"),
        "processing": sum(1 for job in jobs if job["status"] == "processing"),
        "done": sum(1 for job in jobs if job["status"] == "done"),
        "failed": sum(1 for job in jobs if job["status"] == "failed"),
    }
    return {"code": 0, "message": "ok", "data": {"summary": summary, "jobs": jobs}}


@router.post("/exports")
def create_export(
    payload: ExportCreatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    allowed_types = {"final_dataset", "review_records", "disputed_cases"}
    allowed_formats = {"json", "jsonl"}
    if payload.export_type not in allowed_types:
        raise HTTPException(status_code=400, detail="unsupported export type")
    if payload.file_format not in allowed_formats:
        raise HTTPException(status_code=400, detail="unsupported export format")

    with db_cursor() as cursor:
        if payload.application_id is not None:
            application = cursor.execute(
                "SELECT id FROM applications WHERE id = ?",
                (payload.application_id,),
            ).fetchone()
            if not application:
                raise HTTPException(status_code=404, detail="application not found")

        job_id = f"export_{uuid4().hex}"
        cursor.execute(
            """
            INSERT INTO export_jobs (
              job_id, export_type, application_id, date_from, date_to,
              file_format, status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                job_id,
                payload.export_type,
                payload.application_id,
                payload.date_from,
                payload.date_to,
                payload.file_format,
                current_user["id"],
                now_iso(),
            ),
        )
        export_job_id = int(cursor.lastrowid)

    try:
        queue_job("export", {"export_job_id": export_job_id}, job_id=job_id)
    except Exception as exc:
        with db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE export_jobs
                SET status = 'failed',
                    completed_at = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (now_iso(), str(exc), export_job_id),
            )
        raise HTTPException(status_code=500, detail="failed to queue export job")

    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT ej.*, a.name AS application_name
            FROM export_jobs ej
            LEFT JOIN applications a ON a.id = ej.application_id
            WHERE ej.id = ?
            """,
            (export_job_id,),
        ).fetchone()

    return {"code": 0, "message": "ok", "data": serialize_export_job(row)}


@router.get("/exports")
def list_exports(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              ej.*,
              a.name AS application_name,
              u.full_name AS created_by_name
            FROM export_jobs ej
            LEFT JOIN applications a ON a.id = ej.application_id
            LEFT JOIN users u ON u.id = ej.created_by
            ORDER BY ej.id DESC
            """
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": [serialize_export_job(row) for row in rows],
    }


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: int,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT id, file_path, export_type, file_format, status
            FROM export_jobs
            WHERE id = ?
            """,
            (export_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="export not found")
    if row["status"] != "done" or not row["file_path"]:
        raise HTTPException(status_code=409, detail="export file not ready")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="export file missing")

    return FileResponse(
        path=file_path,
        media_type="application/json",
        filename=file_path.name,
    )


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, current_user: CurrentUser = Depends(require_admin)):
    failed_path = QUEUE_DIR / "failed" / f"{job_id}.json"
    if not failed_path.exists():
        raise HTTPException(status_code=404, detail="failed job not found")
    pending_path = QUEUE_DIR / "pending" / failed_path.name
    error_path = failed_path.with_suffix(".error.txt")
    if pending_path.exists():
        raise HTTPException(status_code=409, detail="job already pending")
    payload = json.loads(failed_path.read_text(encoding="utf-8"))
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    payload["meta"] = {
        **meta,
        "retry_count": int(meta.get("retry_count", 0)) + 1,
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
        "last_error": None,
    }
    failed_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failed_path.replace(pending_path)
    if error_path.exists():
        error_path.unlink()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "job_id": job_id,
            "status": "pending",
            "retry_count": payload["meta"]["retry_count"],
        },
    }


@router.post("/jobs/run-once")
def run_one_job(current_user: CurrentUser = Depends(require_admin)):
    next_job = get_next_job()
    if next_job is None:
        return {"code": 0, "message": "ok", "data": {"processed": False, "job_id": None}}
    job_id = next_job.stem
    process_job(next_job)
    return {"code": 0, "message": "ok", "data": {"processed": True, "job_id": job_id}}


@router.get("/experts")
def list_experts(
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin),
):
    query = """
        SELECT
          u.id,
          u.username,
          u.full_name,
          u.organization,
          u.title,
          u.status,
          u.created_at,
          COALESCE(GROUP_CONCAT(a.name, ' / '), '') AS applications
        FROM users u
        LEFT JOIN expert_applications ea ON ea.expert_user_id = u.id
        LEFT JOIN applications a ON a.id = ea.application_id
        WHERE u.role = 'expert'
    """
    params: Tuple[str, ...] = ()
    if status:
        query += " AND u.status = ?"
        params = (status,)
    query += """
        GROUP BY u.id, u.username, u.full_name, u.organization, u.title, u.status, u.created_at
        ORDER BY u.id DESC
    """
    with db_cursor() as cursor:
        rows = cursor.execute(query, params).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}


@router.post("/experts/{expert_id}/approve")
def approve_expert(
    expert_id: int,
    payload: ExpertDecisionPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    approved_at = now_iso()
    with db_cursor() as cursor:
        updated = cursor.execute(
            """
            UPDATE users
            SET status = 'approved', approved_at = ?
            WHERE id = ? AND role = 'expert'
            """,
            (approved_at, expert_id),
        ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="expert not found")
    return {"code": 0, "message": "ok", "data": {"id": expert_id, "status": "approved"}}


@router.post("/experts/{expert_id}/reject")
def reject_expert(
    expert_id: int,
    payload: ExpertDecisionPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        updated = cursor.execute(
            """
            UPDATE users
            SET status = 'rejected'
            WHERE id = ? AND role = 'expert'
            """,
            (expert_id,),
        ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="expert not found")
    return {"code": 0, "message": "ok", "data": {"id": expert_id, "status": "rejected"}}


@router.post("/experts/{expert_id}/disable")
def disable_expert(
    expert_id: int,
    payload: ExpertDecisionPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        updated = cursor.execute(
            """
            UPDATE users
            SET status = 'disabled'
            WHERE id = ? AND role = 'expert'
            """,
            (expert_id,),
        ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="expert not found")
    return {"code": 0, "message": "ok", "data": {"id": expert_id, "status": "disabled"}}


@router.post("/imports/upload")
async def upload_import(
    file: UploadFile = File(...),
    name: str = "default-batch",
    source: str = "manual-upload",
    current_user: CurrentUser = Depends(require_admin),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}_{Path(file.filename or 'dataset.json').name}"
    file_path = UPLOAD_DIR / filename
    file_path.write_bytes(await file.read())

    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dataset_batches (
              name, source, file_path, import_status, created_by, created_at
            ) VALUES (?, ?, ?, 'uploaded', ?, ?)
            """,
            (name, source, str(file_path), current_user["id"], created_at),
        )
        batch_id = cursor.lastrowid

    return {
        "code": 0,
        "message": "ok",
        "data": {"batch_id": batch_id, "file_path": str(file_path), "import_status": "uploaded"},
    }


@router.post("/imports/{batch_id}/parse")
def parse_import(batch_id: int, current_user: CurrentUser = Depends(require_admin)):
    job_id = queue_job("import", {"batch_id": batch_id})
    return {"code": 0, "message": "ok", "data": {"job_id": job_id}}


@router.get("/imports")
def list_imports(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, name, source, file_path, import_status,
                   total_count, success_count, fail_count, created_at
            FROM dataset_batches
            ORDER BY id DESC
            """
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}


@router.get("/imports/{batch_id}/failures")
def list_import_failures(batch_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        batch = cursor.execute(
            """
            SELECT id, name, import_status, total_count, success_count, fail_count
            FROM dataset_batches
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="batch not found")

        rows = cursor.execute(
            """
            SELECT id, row_no, external_id, question_preview, error_message, raw_payload_json, created_at
            FROM dataset_batch_failures
            WHERE dataset_batch_id = ?
            ORDER BY row_no ASC, id ASC
            """,
            (batch_id,),
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "batch": dict(batch),
            "failures": [dict(row) for row in rows],
        },
    }


@router.get("/qas")
def list_qas(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              q.id,
              q.external_id,
              q.question_text,
              q.status,
              a.name AS application_name,
              agg.review_count,
              agg.final_decision,
              agg.agreement_score,
              agg.current_answer_id,
              agg.final_standard_answer_id
            FROM qa_items q
            JOIN applications a ON a.id = q.application_id
            LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
            ORDER BY q.id DESC
            """
        ).fetchall()
    data = []
    for row in rows:
        item = dict(row)
        item["question_summary"] = item["question_text"][:80]
        item.pop("question_text", None)
        data.append(item)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/qas/{qa_id}")
def get_qa_detail(qa_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        qa_item = cursor.execute(
            """
            SELECT q.*, a.name AS application_name
            FROM qa_items q
            JOIN applications a ON a.id = q.application_id
            WHERE q.id = ?
            """,
            (qa_id,),
        ).fetchone()
        if not qa_item:
            raise HTTPException(status_code=404, detail="qa not found")

        answers = cursor.execute(
            "SELECT * FROM qa_answers WHERE qa_item_id = ? ORDER BY id DESC",
            (qa_id,),
        ).fetchall()
        tasks = cursor.execute(
            "SELECT * FROM evaluation_tasks WHERE qa_item_id = ? ORDER BY id DESC",
            (qa_id,),
        ).fetchall()
        records = cursor.execute(
            "SELECT * FROM evaluation_records WHERE qa_item_id = ? ORDER BY id DESC",
            (qa_id,),
        ).fetchall()
        aggregate = cursor.execute(
            "SELECT * FROM qa_aggregates WHERE qa_item_id = ?",
            (qa_id,),
        ).fetchone()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "qa_item": dict(qa_item),
            "answers": [dict(row) for row in answers],
            "tasks": [dict(row) for row in tasks],
            "records": [dict(row) for row in records],
            "aggregate": dict(aggregate) if aggregate else None,
        },
    }


@router.post("/qas/{qa_id}/aggregate/run")
def rerun_aggregate(qa_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        qa_item = cursor.execute(
            "SELECT id FROM qa_items WHERE id = ?",
            (qa_id,),
        ).fetchone()
        if not qa_item:
            raise HTTPException(status_code=404, detail="qa not found")

        latest_record = cursor.execute(
            """
            SELECT answer_id
            FROM evaluation_records
            WHERE qa_item_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (qa_id,),
        ).fetchone()
        if latest_record:
            answer_id = latest_record["answer_id"]
        else:
            latest_task = cursor.execute(
                """
                SELECT answer_id
                FROM evaluation_tasks
                WHERE qa_item_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (qa_id,),
            ).fetchone()
            if not latest_task:
                raise HTTPException(status_code=409, detail="qa has no evaluation task to aggregate")
            answer_id = latest_task["answer_id"]

    job_id = queue_job("aggregate", {"qa_item_id": qa_id, "answer_id": answer_id})
    return {
        "code": 0,
        "message": "ok",
        "data": {"qa_id": qa_id, "answer_id": answer_id, "job_id": job_id},
    }


@router.post("/qas/{qa_id}/final-answer")
def confirm_final_answer(
    qa_id: int,
    payload: FinalAnswerPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        qa_item = cursor.execute(
            "SELECT id, status FROM qa_items WHERE id = ?",
            (qa_id,),
        ).fetchone()
        if not qa_item:
            raise HTTPException(status_code=404, detail="qa not found")

        answer = cursor.execute(
            """
            SELECT id, qa_item_id
            FROM qa_answers
            WHERE id = ? AND qa_item_id = ?
            """,
            (payload.answer_id, qa_id),
        ).fetchone()
        if not answer:
            raise HTTPException(status_code=404, detail="answer not found")

        cursor.execute(
            """
            UPDATE qa_answers
            SET answer_type = CASE
              WHEN answer_type = 'final_standard' THEN 'expert_confirmed_standard'
              ELSE answer_type
            END
            WHERE qa_item_id = ?
            """,
            (qa_id,),
        )
        cursor.execute(
            """
            UPDATE qa_answers
            SET answer_type = 'final_standard'
            WHERE id = ?
            """,
            (payload.answer_id,),
        )
        cursor.execute(
            """
            INSERT INTO qa_aggregates (
              qa_item_id, current_answer_id, review_count, final_decision,
              final_standard_answer_id, aggregated_at
            ) VALUES (?, ?, 0, 'pending', ?, ?)
            ON CONFLICT(qa_item_id) DO UPDATE SET
              final_standard_answer_id = excluded.final_standard_answer_id,
              aggregated_at = excluded.aggregated_at
            """,
            (qa_id, payload.answer_id, payload.answer_id, now_iso()),
        )
        cursor.execute(
            """
            UPDATE qa_items
            SET status = 'reviewed'
            WHERE id = ?
            """,
            (qa_id,),
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {"qa_id": qa_id, "final_standard_answer_id": payload.answer_id},
    }


@router.post("/tasks/dispatch")
def dispatch_tasks(
    payload: DispatchPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    job_id = queue_job(
        "dispatch",
        {"application_id": payload.application_id, "limit": payload.limit},
    )
    return {"code": 0, "message": "ok", "data": {"job_id": job_id}}
