from __future__ import annotations

from datetime import datetime
import json
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_expert
from ..db import db_cursor
from ..jobs import queue_job

router = APIRouter(prefix="/api/expert", tags=["expert"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class DraftPayload(BaseModel):
    correctness_rating: Optional[str] = None
    completeness_rating: Optional[str] = None
    relevance_rating: Optional[str] = None
    clarity_rating: Optional[str] = None
    risk_flag: Optional[str] = None
    overall_decision: Optional[str] = None
    quick_comment_codes: List[str] = Field(default_factory=list)
    adopted_rewrite_answer_id: Optional[int] = None


class SubmitPayload(BaseModel):
    correctness_rating: str
    completeness_rating: str
    relevance_rating: str
    clarity_rating: str
    risk_flag: str
    overall_decision: str
    quick_comment_codes: List[str] = Field(default_factory=list)
    adopted_rewrite_answer_id: Optional[int] = None


def get_task(task_id: int, expert_user_id: int):
    with db_cursor() as cursor:
        task = cursor.execute(
            """
            SELECT *
            FROM evaluation_tasks
            WHERE id = ? AND expert_user_id = ?
            """,
            (task_id, expert_user_id),
        ).fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.get("/history")
def list_history(current_user: CurrentUser = Depends(require_expert)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              r.id,
              r.task_id,
              r.qa_item_id,
              r.answer_id,
              r.correctness_rating,
              r.completeness_rating,
              r.relevance_rating,
              r.clarity_rating,
              r.risk_flag,
              r.overall_decision,
              r.quick_comment_codes,
              r.adopted_rewrite_answer_id,
              r.created_at AS submitted_at,
              t.task_type,
              q.question_text,
              a.name AS application_name,
              agg.final_decision AS aggregate_final_decision,
              agg.agreement_score,
              agg.review_count,
              adopted.answer_text AS adopted_rewrite_answer_text,
              final_answer.id AS final_standard_answer_id,
              final_answer.answer_text AS final_standard_answer_text,
              (
                SELECT COUNT(*)
                FROM llm_sessions s
                WHERE s.task_id = r.task_id
              ) AS llm_session_count
            FROM evaluation_records r
            JOIN evaluation_tasks t ON t.id = r.task_id
            JOIN qa_items q ON q.id = r.qa_item_id
            JOIN applications a ON a.id = q.application_id
            LEFT JOIN qa_aggregates agg ON agg.qa_item_id = r.qa_item_id
            LEFT JOIN qa_answers adopted ON adopted.id = r.adopted_rewrite_answer_id
            LEFT JOIN qa_answers final_answer ON final_answer.id = agg.final_standard_answer_id
            WHERE r.expert_user_id = ?
            ORDER BY r.created_at DESC, r.id DESC
            """,
            (current_user["id"],),
        ).fetchall()

    data = []
    for row in rows:
        item = dict(row)
        item["question_summary"] = item["question_text"][:80]
        item["quick_comment_codes"] = json.loads(item["quick_comment_codes"] or "[]")
        item["adopted_became_final"] = bool(
            item["adopted_rewrite_answer_id"]
            and item["final_standard_answer_id"]
            and item["adopted_rewrite_answer_id"] == item["final_standard_answer_id"]
        )
        data.append(item)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/tasks")
def list_tasks(
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_expert),
):
    query = """
        SELECT
          t.id,
          t.qa_item_id,
          t.answer_id,
          t.task_type,
          t.status,
          t.assigned_at,
          t.expires_at,
          a.name AS application_name,
          q.question_text
        FROM evaluation_tasks t
        JOIN qa_items q ON q.id = t.qa_item_id
        JOIN applications a ON a.id = q.application_id
    """
    params: Tuple[object, ...] = (current_user["id"],)
    query += " WHERE t.expert_user_id = ?"
    if status:
        query += " AND t.status = ?"
        params = (current_user["id"], status)
    query += " ORDER BY t.id DESC"

    with db_cursor() as cursor:
        rows = cursor.execute(query, params).fetchall()

    data = []
    for row in rows:
        item = dict(row)
        item["question_summary"] = item["question_text"][:80]
        item.pop("question_text", None)
        data.append(item)
    return {"code": 0, "message": "ok", "data": data}


@router.get("/tasks/{task_id}")
def get_task_detail(
    task_id: int,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    with db_cursor() as cursor:
        qa_item = cursor.execute(
            """
            SELECT q.*, a.name AS application_name
            FROM qa_items q
            JOIN applications a ON a.id = q.application_id
            WHERE q.id = ?
            """,
            (task["qa_item_id"],),
        ).fetchone()
        answer = cursor.execute(
            """
            SELECT id, answer_text, answer_type, source_model, version_no
            FROM qa_answers
            WHERE id = ?
            """,
            (task["answer_id"],),
        ).fetchone()
        candidates = cursor.execute(
            """
            SELECT id, answer_text, answer_type, source_model, version_no, created_at
            FROM qa_answers
            WHERE qa_item_id = ?
            ORDER BY id DESC
            """,
            (task["qa_item_id"],),
        ).fetchall()
        sessions = cursor.execute(
            """
            SELECT id, purpose, status, created_at
            FROM llm_sessions
            WHERE task_id = ?
            ORDER BY id DESC
            """,
            (task_id,),
        ).fetchall()
        draft = cursor.execute(
            """
            SELECT payload_json, updated_at
            FROM evaluation_drafts
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task": dict(task),
            "qa_item": dict(qa_item),
            "current_answer": dict(answer),
            "candidate_answers": [dict(row) for row in candidates],
            "llm_sessions": [dict(row) for row in sessions],
            "draft": (
                {
                    "payload": json.loads(draft["payload_json"]),
                    "updated_at": draft["updated_at"],
                }
                if draft
                else None
            ),
        },
    }


@router.post("/tasks/{task_id}/start")
def start_task(task_id: int, current_user: CurrentUser = Depends(require_expert)):
    get_task(task_id, current_user["id"])
    started_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE evaluation_tasks
            SET status = 'in_progress', started_at = COALESCE(started_at, ?)
            WHERE id = ? AND status = 'pending'
            """,
            (started_at, task_id),
        )
    return {"code": 0, "message": "ok", "data": {"task_id": task_id, "status": "in_progress"}}


@router.post("/tasks/{task_id}/draft")
def save_draft(
    task_id: int,
    payload: DraftPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    updated_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO evaluation_drafts (
              task_id, qa_item_id, answer_id, expert_user_id, payload_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
              payload_json = excluded.payload_json,
              updated_at = excluded.updated_at
            """,
            (
                task["id"],
                task["qa_item_id"],
                task["answer_id"],
                task["expert_user_id"],
                json.dumps(payload.model_dump(), ensure_ascii=False),
                updated_at,
            ),
        )
    return {
        "code": 0,
        "message": "draft saved",
        "data": {
            "task_id": task_id,
            "draft": payload.model_dump(),
            "updated_at": updated_at,
        },
    }


@router.post("/tasks/{task_id}/submit")
def submit_task(
    task_id: int,
    payload: SubmitPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO evaluation_records (
              task_id, qa_item_id, answer_id, expert_user_id,
              correctness_rating, completeness_rating, relevance_rating,
              clarity_rating, risk_flag, overall_decision,
              quick_comment_codes, adopted_rewrite_answer_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task["id"],
                task["qa_item_id"],
                task["answer_id"],
                task["expert_user_id"],
                payload.correctness_rating,
                payload.completeness_rating,
                payload.relevance_rating,
                payload.clarity_rating,
                payload.risk_flag,
                payload.overall_decision,
                json.dumps(payload.quick_comment_codes, ensure_ascii=False),
                payload.adopted_rewrite_answer_id,
                created_at,
            ),
        )
        cursor.execute(
            """
            UPDATE evaluation_tasks
            SET status = 'submitted', submitted_at = ?
            WHERE id = ?
            """,
            (created_at, task_id),
        )
        cursor.execute(
            "DELETE FROM evaluation_drafts WHERE task_id = ?",
            (task_id,),
        )
    job_id = queue_job(
        "aggregate",
        {"qa_item_id": task["qa_item_id"], "answer_id": task["answer_id"]},
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {"task_id": task_id, "status": "submitted", "aggregate_job_id": job_id},
    }
