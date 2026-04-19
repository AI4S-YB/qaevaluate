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


def parse_tag_codes(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item) for item in parsed if isinstance(item, str) and item}


def get_expert_scope(cursor, current_user: CurrentUser) -> tuple[bool, set[str]]:
    if current_user["role"] == "admin":
        return True, set()

    user = cursor.execute(
        """
        SELECT allow_cross_business_review
        FROM users
        WHERE id = ?
        """,
        (current_user["id"],),
    ).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    business_tags = cursor.execute(
        """
        SELECT b.code
        FROM expert_business_tags ebt
        JOIN business_tags b ON b.id = ebt.business_tag_id
        WHERE ebt.expert_user_id = ?
        """,
        (current_user["id"],),
    ).fetchall()
    return bool(user["allow_cross_business_review"]), {row["code"] for row in business_tags}


def can_access_by_business_scope(
    allow_cross_business_review: bool,
    expert_business_tags: set[str],
    qa_business_tags_json: Optional[str],
) -> bool:
    if allow_cross_business_review:
        return True

    qa_tags = parse_tag_codes(qa_business_tags_json)
    if not qa_tags:
        return True
    return bool(qa_tags & expert_business_tags)


class DraftPayload(BaseModel):
    correctness_rating: Optional[str] = None
    completeness_rating: Optional[str] = None
    relevance_rating: Optional[str] = None
    clarity_rating: Optional[str] = None
    risk_flag: Optional[str] = None
    reasoning_completeness: Optional[str] = None
    reasoning_consistency: Optional[str] = None
    reasoning_support: Optional[str] = None
    overall_decision: Optional[str] = None
    quick_comment_codes: List[str] = Field(default_factory=list)
    adopted_rewrite_answer_id: Optional[int] = None
    adopted_rewrite_answer_text: Optional[str] = None


class SubmitPayload(BaseModel):
    correctness_rating: str
    completeness_rating: str
    relevance_rating: str
    clarity_rating: str
    risk_flag: str
    reasoning_completeness: Optional[str] = None
    reasoning_consistency: Optional[str] = None
    reasoning_support: Optional[str] = None
    overall_decision: str
    quick_comment_codes: List[str] = Field(default_factory=list)
    adopted_rewrite_answer_id: Optional[int] = None
    adopted_rewrite_answer_text: Optional[str] = None


def get_task(task_id: int, expert_user_id: int):
    with db_cursor() as cursor:
        task = cursor.execute(
            """
            SELECT t.*, q.business_tags_json
            FROM evaluation_tasks t
            JOIN qa_items q ON q.id = t.qa_item_id
            WHERE t.id = ? AND t.expert_user_id = ?
            """,
            (task_id, expert_user_id),
        ).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        current_user = cursor.execute(
            "SELECT id, role FROM users WHERE id = ?",
            (expert_user_id,),
        ).fetchone()
        if not current_user:
            raise HTTPException(status_code=404, detail="user not found")

        allow_cross, business_tags = get_expert_scope(cursor, dict(current_user))
        if not can_access_by_business_scope(allow_cross, business_tags, task["business_tags_json"]):
            raise HTTPException(status_code=404, detail="task not found")
    return task


def ensure_candidate_answer(cursor, qa_item_id: int, answer_id: Optional[int]) -> Optional[int]:
    if answer_id is None:
        return None
    row = cursor.execute(
        """
        SELECT id
        FROM qa_answers
        WHERE id = ? AND qa_item_id = ?
        """,
        (answer_id, qa_item_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="selected candidate answer not found")
    return int(row["id"])


def ensure_candidate_answer_with_text(
    cursor,
    qa_item_id: int,
    answer_id: Optional[int],
    answer_text: Optional[str],
    source_user_id: int,
) -> Optional[int]:
    adopted_rewrite_answer_id = ensure_candidate_answer(cursor, qa_item_id, answer_id)
    normalized_text = blank_to_none(answer_text)
    if normalized_text is None:
        return adopted_rewrite_answer_id
    if adopted_rewrite_answer_id is None:
        raise HTTPException(status_code=400, detail="edited rewrite answer requires selected candidate")

    selected_answer = cursor.execute(
        """
        SELECT id, answer_text
        FROM qa_answers
        WHERE id = ? AND qa_item_id = ?
        """,
        (adopted_rewrite_answer_id, qa_item_id),
    ).fetchone()
    if not selected_answer:
        raise HTTPException(status_code=400, detail="selected candidate answer not found")
    if normalized_text == str(selected_answer["answer_text"]).strip():
        return adopted_rewrite_answer_id

    version_row = cursor.execute(
        "SELECT COALESCE(MAX(version_no), 0) AS max_version_no FROM qa_answers WHERE qa_item_id = ?",
        (qa_item_id,),
    ).fetchone()
    cursor.execute(
        """
        INSERT INTO qa_answers (
          qa_item_id, answer_text, answer_type, source_model,
          source_user_id, parent_answer_id, version_no, is_current, created_at
        ) VALUES (?, ?, 'llm_generated_candidate', ?, ?, ?, ?, 0, ?)
        """,
        (
            qa_item_id,
            normalized_text,
            "expert-edited rewrite",
            source_user_id,
            adopted_rewrite_answer_id,
            int(version_row["max_version_no"] or 0) + 1,
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def ensure_admin_preview_tasks(current_user: CurrentUser) -> None:
    if current_user["role"] != "admin":
        return

    assigned_at = now_iso()
    with db_cursor() as cursor:
        existing_count = cursor.execute(
            "SELECT COUNT(*) AS count FROM evaluation_tasks WHERE expert_user_id = ?",
            (current_user["id"],),
        ).fetchone()["count"]
        if existing_count:
            return

        rows = cursor.execute(
            """
            SELECT
              q.id AS qa_item_id,
              (
                SELECT ans.id
                FROM qa_answers ans
                WHERE ans.qa_item_id = q.id
                ORDER BY ans.is_current DESC, ans.id DESC
                LIMIT 1
              ) AS answer_id
            FROM qa_items q
            WHERE q.status IN ('active', 'in_review', 'reviewed')
            ORDER BY q.id DESC
            LIMIT 12
            """
        ).fetchall()

        for row in rows:
            if not row["answer_id"]:
                continue
            cursor.execute(
                """
                INSERT OR IGNORE INTO evaluation_tasks (
                  qa_item_id, answer_id, expert_user_id, round_no,
                  task_type, status, assigned_at
                ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
                """,
                (row["qa_item_id"], row["answer_id"], current_user["id"], assigned_at),
            )


@router.get("/taxonomy")
def get_taxonomy(current_user: CurrentUser = Depends(require_expert)):
    with db_cursor() as cursor:
        technical_types = cursor.execute(
            """
            SELECT id, code, name, description, is_active, sort_order, created_at
            FROM technical_types
            WHERE is_active = 1
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
        business_tags = cursor.execute(
            """
            SELECT id, code, name, description, is_active, sort_order, created_at
            FROM business_tags
            WHERE is_active = 1
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "technical_types": [dict(row) for row in technical_types],
            "business_tags": [dict(row) for row in business_tags],
        },
    }


@router.get("/history")
def list_history(current_user: CurrentUser = Depends(require_expert)):
    with db_cursor() as cursor:
        allow_cross, business_tags = get_expert_scope(cursor, current_user)
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
              q.business_tags_json,
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
        if not can_access_by_business_scope(allow_cross, business_tags, row["business_tags_json"]):
            continue
        item = dict(row)
        item["question_summary"] = item["question_text"][:80]
        item["quick_comment_codes"] = json.loads(item["quick_comment_codes"] or "[]")
        item.pop("business_tags_json", None)
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
    ensure_admin_preview_tasks(current_user)
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
          q.business_tags_json,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          q.question_text
        FROM evaluation_tasks t
        JOIN qa_items q ON q.id = t.qa_item_id
        JOIN applications a ON a.id = q.application_id
        LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
    """
    params: Tuple[object, ...] = (current_user["id"],)
    query += " WHERE t.expert_user_id = ?"
    if status:
        query += " AND t.status = ?"
        params = (current_user["id"], status)
    query += " ORDER BY t.id DESC"

    with db_cursor() as cursor:
        allow_cross, business_tags = get_expert_scope(cursor, current_user)
        rows = cursor.execute(query, params).fetchall()

    data = []
    for row in rows:
        if not can_access_by_business_scope(allow_cross, business_tags, row["business_tags_json"]):
            continue
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
            SELECT q.*, a.name AS application_name, tt.code AS technical_type_code, tt.name AS technical_type_name
            FROM qa_items q
            JOIN applications a ON a.id = q.application_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
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
            SELECT
              id,
              answer_text,
              answer_type,
              source_model,
              parent_answer_id,
              version_no,
              created_at
            FROM qa_answers
            WHERE qa_item_id = ?
            ORDER BY version_no DESC, id DESC
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
        submitted_record = cursor.execute(
            """
            SELECT
              correctness_rating,
              completeness_rating,
              relevance_rating,
              clarity_rating,
              risk_flag,
              reasoning_completeness,
              reasoning_consistency,
              reasoning_support,
              overall_decision,
              quick_comment_codes,
              adopted_rewrite_answer_id,
              adopted.answer_text AS adopted_rewrite_answer_text,
              r.created_at
            FROM evaluation_records r
            LEFT JOIN qa_answers adopted ON adopted.id = r.adopted_rewrite_answer_id
            WHERE r.task_id = ?
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
            "submitted_record": (
                {
                    "payload": {
                        "correctness_rating": submitted_record["correctness_rating"],
                        "completeness_rating": submitted_record["completeness_rating"],
                        "relevance_rating": submitted_record["relevance_rating"],
                        "clarity_rating": submitted_record["clarity_rating"],
                        "risk_flag": submitted_record["risk_flag"],
                        "reasoning_completeness": submitted_record["reasoning_completeness"],
                        "reasoning_consistency": submitted_record["reasoning_consistency"],
                        "reasoning_support": submitted_record["reasoning_support"],
                        "overall_decision": submitted_record["overall_decision"],
                        "quick_comment_codes": json.loads(
                            submitted_record["quick_comment_codes"] or "[]"
                        ),
                        "adopted_rewrite_answer_id": submitted_record["adopted_rewrite_answer_id"],
                        "adopted_rewrite_answer_text": submitted_record[
                            "adopted_rewrite_answer_text"
                        ],
                    },
                    "updated_at": submitted_record["created_at"],
                }
                if submitted_record
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
        adopted_rewrite_answer_id = ensure_candidate_answer(
            cursor,
            int(task["qa_item_id"]),
            payload.adopted_rewrite_answer_id,
        )
        adopted_rewrite_answer_text = blank_to_none(payload.adopted_rewrite_answer_text)
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
                json.dumps(
                    {
                        **payload.model_dump(),
                        "adopted_rewrite_answer_id": adopted_rewrite_answer_id,
                        "adopted_rewrite_answer_text": adopted_rewrite_answer_text,
                    },
                    ensure_ascii=False,
                ),
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


@router.post("/tasks/{task_id}/abandon")
def abandon_task(task_id: int, current_user: CurrentUser = Depends(require_expert)):
    task = get_task(task_id, current_user["id"])
    if task["status"] in {"submitted", "expired", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"task is {task['status']}")

    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO expert_task_abandons (
              qa_item_id, answer_id, expert_user_id, task_type, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(answer_id, expert_user_id, task_type) DO UPDATE SET
              created_at = excluded.created_at
            """,
            (
                task["qa_item_id"],
                task["answer_id"],
                task["expert_user_id"],
                task["task_type"],
                now_iso(),
            ),
        )
        cursor.execute(
            "DELETE FROM evaluation_drafts WHERE task_id = ?",
            (task_id,),
        )
        session_rows = cursor.execute(
            "SELECT id FROM llm_sessions WHERE task_id = ?",
            (task_id,),
        ).fetchall()
        session_ids = [int(row["id"]) for row in session_rows]
        for session_id in session_ids:
            cursor.execute(
                "DELETE FROM llm_messages WHERE session_id = ?",
                (session_id,),
            )
        cursor.execute(
            "DELETE FROM llm_sessions WHERE task_id = ?",
            (task_id,),
        )
        cursor.execute(
            "DELETE FROM evaluation_tasks WHERE id = ?",
            (task_id,),
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {"task_id": task_id, "status": "abandoned"},
    }


@router.post("/tasks/{task_id}/submit")
def submit_task(
    task_id: int,
    payload: SubmitPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    if task["status"] in {"expired", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"task is {task['status']}")
    created_at = now_iso()
    reasoning_completeness = blank_to_none(payload.reasoning_completeness)
    reasoning_consistency = blank_to_none(payload.reasoning_consistency)
    reasoning_support = blank_to_none(payload.reasoning_support)
    with db_cursor() as cursor:
        adopted_rewrite_answer_id = ensure_candidate_answer_with_text(
            cursor,
            int(task["qa_item_id"]),
            payload.adopted_rewrite_answer_id,
            payload.adopted_rewrite_answer_text,
            int(task["expert_user_id"]),
        )
        cursor.execute(
            """
            INSERT INTO evaluation_records (
              task_id, qa_item_id, answer_id, expert_user_id,
              correctness_rating, completeness_rating, relevance_rating,
              clarity_rating, risk_flag, reasoning_completeness,
              reasoning_consistency, reasoning_support, overall_decision,
              quick_comment_codes, adopted_rewrite_answer_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
              qa_item_id = excluded.qa_item_id,
              answer_id = excluded.answer_id,
              expert_user_id = excluded.expert_user_id,
              correctness_rating = excluded.correctness_rating,
              completeness_rating = excluded.completeness_rating,
              relevance_rating = excluded.relevance_rating,
              clarity_rating = excluded.clarity_rating,
              risk_flag = excluded.risk_flag,
              reasoning_completeness = excluded.reasoning_completeness,
              reasoning_consistency = excluded.reasoning_consistency,
              reasoning_support = excluded.reasoning_support,
              overall_decision = excluded.overall_decision,
              quick_comment_codes = excluded.quick_comment_codes,
              adopted_rewrite_answer_id = excluded.adopted_rewrite_answer_id,
              created_at = excluded.created_at
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
                reasoning_completeness,
                reasoning_consistency,
                reasoning_support,
                payload.overall_decision,
                json.dumps(payload.quick_comment_codes, ensure_ascii=False),
                adopted_rewrite_answer_id,
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
