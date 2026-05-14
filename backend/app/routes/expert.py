from __future__ import annotations

from datetime import datetime
import json
from typing import List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_expert
from ..config import UPLOAD_DIR
from ..db import db_cursor
from ..jobs import queue_job, queue_unique_import_job
from ..routes.admin import create_dataset_batch, validate_import_target
from ..worker import (
    expert_can_review_business_tags,
    load_application_experts,
    stale_import_lock_before_iso,
)

router = APIRouter(prefix="/api/expert", tags=["expert"])

VIRTUAL_REMOTE_BATCH_ID = -1
VIRTUAL_REMOTE_BATCH_NAME = "远程服务器（未归批次 QA）"
VIRTUAL_REMOTE_BATCH_SOURCE = "remote-server"
VIRTUAL_REMOTE_BATCH_EXTERNAL_ID = "__remote_unbatched__"


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


def can_access_uploaded_batch(row, current_user_id: int) -> bool:
    uploader_user_id = row["batch_uploader_user_id"] if "batch_uploader_user_id" in row.keys() else None
    return uploader_user_id is not None and int(uploader_user_id) == int(current_user_id)


def validate_expert_import_target(
    current_user: CurrentUser,
    application_id: int,
    technical_type_code: str,
    business_tag_codes: list[str],
) -> tuple[int, int]:
    application_db_id, technical_type_id = validate_import_target(
        application_id,
        technical_type_code,
        business_tag_codes,
    )
    if current_user["role"] == "admin":
        return application_db_id, technical_type_id

    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT 1
            FROM expert_applications
            WHERE expert_user_id = ? AND application_id = ?
            """,
            (current_user["id"], application_db_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="application is not in your expert scope")
    with db_cursor() as cursor:
        allow_cross, expert_business_tags = get_expert_scope(cursor, current_user)
    if not allow_cross:
        missing_codes = [code for code in business_tag_codes if code not in expert_business_tags]
        if missing_codes:
            raise HTTPException(
                status_code=403,
                detail=f"business_tag is not in your expert scope: {missing_codes[0]}",
            )
    return application_db_id, technical_type_id


def build_import_batch_payload(rows: list[ExpertImportRowPayload]) -> list[dict]:
    return [row.model_dump(exclude_none=True) for row in rows]


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


class ExpertImportCandidateAnswerPayload(BaseModel):
    answer: str


class ExpertMessagePayload(BaseModel):
    role: str
    content: str


class ExpertImportRowPayload(BaseModel):
    id: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    context: Optional[str] = None
    difficulty: Optional[str] = None
    source: Optional[str] = None
    model: Optional[str] = None
    metadata: Optional[dict] = None
    candidate_answers: list[ExpertImportCandidateAnswerPayload] = Field(default_factory=list)
    messages: list[ExpertMessagePayload] = Field(default_factory=list)


class ExpertImportPushPayload(BaseModel):
    name: str = "default-batch"
    source: str = "qa-xiaozhao"
    source_batch_name: Optional[str] = None
    external_batch_id: Optional[str] = None
    application_id: int
    technical_type_code: str
    business_tag_codes: list[str] = Field(default_factory=list)
    rows: list[ExpertImportRowPayload] = Field(default_factory=list)
    auto_parse: bool = True
    create_self_review: bool = True


class ExpertImportStatusLookupItemPayload(BaseModel):
    source: str = "qa-xiaozhao"
    external_batch_id: str


class ExpertImportStatusLookupPayload(BaseModel):
    items: list[ExpertImportStatusLookupItemPayload] = Field(default_factory=list)


def import_batch_is_processing(row) -> bool:
    if row is None:
        return False
    import_status = row["import_status"] if "import_status" in row.keys() else None
    if import_status in {None, "parsed", "failed"}:
        return False
    parse_lock_token = row["parse_lock_token"] if "parse_lock_token" in row.keys() else None
    parse_lock_acquired_at = (
        row["parse_lock_acquired_at"] if "parse_lock_acquired_at" in row.keys() else None
    )
    if not parse_lock_token or not parse_lock_acquired_at:
        return False
    return parse_lock_acquired_at >= stale_import_lock_before_iso()


def derive_import_batch_status(row) -> str:
    if row is None:
        return "missing"
    if row["import_status"] == "failed":
        return "failed"
    if row["import_status"] == "parsed":
        return "parsed"
    if import_batch_is_processing(row):
        return "processing"
    return "uploaded"


def serialize_import_batch_status(row) -> dict:
    item = dict(row)
    item["batch_id"] = int(item["id"])
    item["exists"] = True
    item["is_processing"] = import_batch_is_processing(row)
    item["batch_status"] = derive_import_batch_status(row)
    item.pop("parse_lock_token", None)
    item.pop("parse_lock_acquired_at", None)
    return item


def serialize_missing_import_batch_status(source: str, external_batch_id: str) -> dict:
    return {
        "source": source,
        "external_batch_id": external_batch_id,
        "exists": False,
        "batch_id": None,
        "import_status": None,
        "is_processing": False,
        "batch_status": "missing",
        "self_review_status": None,
        "peer_review_status": None,
    }


def list_visible_unbatched_qa_rows(cursor, current_user: CurrentUser):
    allow_cross, business_tags = get_expert_scope(cursor, current_user)
    rows = cursor.execute(
        """
        SELECT
          q.id,
          q.external_id,
          q.status,
          q.question_text,
          q.context_text,
          q.source,
          q.source_model,
          q.metadata_json,
          q.business_tags_json,
          q.created_at,
          q.application_id,
          a.name AS application_name,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          ans.id AS current_answer_id,
          ans.answer_text AS current_answer_text,
          (
            SELECT t.status
            FROM evaluation_tasks t
            WHERE t.answer_id = ans.id
              AND t.task_type = 'initial_review'
              AND t.expert_user_id = ?
            ORDER BY t.id DESC
            LIMIT 1
          ) AS self_review_task_status,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            WHERE t.answer_id = ans.id
              AND t.task_type = 'initial_review'
              AND t.expert_user_id = ?
          ) AS self_review_total,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            WHERE t.answer_id = ans.id
              AND t.task_type = 'initial_review'
              AND t.expert_user_id = ?
              AND t.status = 'submitted'
          ) AS self_review_submitted,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            WHERE t.answer_id = ans.id
              AND t.task_type = 'initial_review'
              AND t.expert_user_id = ?
              AND t.status = 'in_progress'
          ) AS self_review_in_progress,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            WHERE t.answer_id = ans.id
              AND t.task_type = 'initial_review'
              AND t.expert_user_id != ?
          ) AS peer_review_total,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            WHERE t.answer_id = ans.id
              AND t.task_type = 'initial_review'
              AND t.expert_user_id != ?
              AND t.status = 'submitted'
          ) AS peer_review_submitted,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            WHERE t.answer_id = ans.id
              AND t.task_type = 'initial_review'
              AND t.expert_user_id != ?
              AND t.status = 'in_progress'
          ) AS peer_review_in_progress
        FROM qa_items q
        JOIN applications a ON a.id = q.application_id
        LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
        LEFT JOIN qa_answers ans ON ans.qa_item_id = q.id AND ans.is_current = 1
        WHERE q.dataset_batch_id IS NULL
        ORDER BY q.id DESC
        """,
        (
            current_user["id"],
            current_user["id"],
            current_user["id"],
            current_user["id"],
            current_user["id"],
            current_user["id"],
            current_user["id"],
        ),
    ).fetchall()

    return [
        row
        for row in rows
        if can_access_by_business_scope(
            allow_cross,
            business_tags,
            row["business_tags_json"],
        )
    ]


def build_virtual_remote_batch_status(cursor, current_user: CurrentUser) -> Optional[dict]:
    rows = list_visible_unbatched_qa_rows(cursor, current_user)
    if not rows:
        return None

    application_ids = {int(row["application_id"]) for row in rows if row["application_id"] is not None}
    application_names = {str(row["application_name"]) for row in rows if row["application_name"]}
    technical_type_codes = {
        str(row["technical_type_code"]) for row in rows if row["technical_type_code"]
    }
    technical_type_names = {
        str(row["technical_type_name"]) for row in rows if row["technical_type_name"]
    }
    business_tag_codes = sorted(
        {
            tag
            for row in rows
            for tag in parse_tag_codes(row["business_tags_json"])
        }
    )

    self_total = sum(int(row["self_review_total"] or 0) for row in rows)
    self_submitted = sum(int(row["self_review_submitted"] or 0) for row in rows)
    self_in_progress = sum(int(row["self_review_in_progress"] or 0) for row in rows)
    peer_total = sum(int(row["peer_review_total"] or 0) for row in rows)
    peer_submitted = sum(int(row["peer_review_submitted"] or 0) for row in rows)
    peer_in_progress = sum(int(row["peer_review_in_progress"] or 0) for row in rows)

    created_at = max(str(row["created_at"]) for row in rows if row["created_at"])

    return {
        "id": VIRTUAL_REMOTE_BATCH_ID,
        "batch_id": VIRTUAL_REMOTE_BATCH_ID,
        "name": VIRTUAL_REMOTE_BATCH_NAME,
        "source": VIRTUAL_REMOTE_BATCH_SOURCE,
        "source_batch_name": "server-unbatched",
        "external_batch_id": VIRTUAL_REMOTE_BATCH_EXTERNAL_ID,
        "file_path": None,
        "import_status": "parsed",
        "total_count": len(rows),
        "success_count": len(rows),
        "fail_count": 0,
        "created_at": created_at,
        "application_id": next(iter(application_ids)) if len(application_ids) == 1 else None,
        "application_name": next(iter(application_names)) if len(application_names) == 1 else "多个项目",
        "uploader_user_id": None,
        "self_review_status": "submitted"
        if compute_progress_status(self_total, self_submitted, self_in_progress) == "completed"
        else compute_progress_status(self_total, self_submitted, self_in_progress),
        "peer_review_status": "completed",
        "parse_lock_token": None,
        "parse_lock_acquired_at": None,
        "business_tags_json": json.dumps(business_tag_codes, ensure_ascii=False),
        "technical_type_code": next(iter(technical_type_codes)) if len(technical_type_codes) == 1 else "mixed",
        "technical_type_name": next(iter(technical_type_names)) if len(technical_type_names) == 1 else "混合类型",
        "self_review_total": self_total,
        "self_review_submitted": self_submitted,
        "peer_review_total": peer_total,
        "peer_review_submitted": peer_submitted,
        "exists": True,
        "is_processing": False,
        "batch_status": "parsed",
    }


def get_import_batch(cursor, batch_id: int, current_user: CurrentUser):
    query = """
        SELECT
          b.id,
          b.name,
          b.source,
          b.source_batch_name,
          b.external_batch_id,
          b.file_path,
          b.import_status,
          b.total_count,
          b.success_count,
          b.fail_count,
          b.created_at,
          b.application_id,
          b.uploader_user_id,
          b.self_review_status,
          b.peer_review_status,
          b.parse_lock_token,
          b.parse_lock_acquired_at,
          b.business_tags_json,
          a.name AS application_name,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name
        FROM dataset_batches b
        LEFT JOIN applications a ON a.id = b.application_id
        LEFT JOIN technical_types tt ON tt.id = b.technical_type_id
        WHERE b.id = ?
          AND b.uploader_user_id = ?
    """
    row = cursor.execute(query, (batch_id, current_user["id"])).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="batch not found")
    return row


def compute_progress_status(total: int, submitted: int, in_progress: int) -> str:
    if total <= 0:
        return "none"
    if submitted >= total:
        return "completed"
    if in_progress > 0 or submitted > 0:
        return "in_progress"
    return "pending"


def refresh_import_batch_review_status(cursor, batch_id: int) -> dict:
    row = cursor.execute(
        """
        SELECT
          b.id,
          b.uploader_user_id,
          b.self_review_status AS current_self_review_status,
          b.peer_review_status AS current_peer_review_status,
          COUNT(DISTINCT CASE
            WHEN t.task_type = 'initial_review'
             AND b.uploader_user_id IS NOT NULL
             AND t.expert_user_id = b.uploader_user_id
            THEN t.id
          END) AS self_total,
          COUNT(DISTINCT CASE
            WHEN t.task_type = 'initial_review'
             AND b.uploader_user_id IS NOT NULL
             AND t.expert_user_id = b.uploader_user_id
             AND t.status = 'submitted'
            THEN t.id
          END) AS self_submitted,
          COUNT(DISTINCT CASE
            WHEN t.task_type = 'initial_review'
             AND b.uploader_user_id IS NOT NULL
             AND t.expert_user_id = b.uploader_user_id
             AND t.status = 'in_progress'
            THEN t.id
          END) AS self_in_progress,
          COUNT(DISTINCT CASE
            WHEN t.task_type = 'initial_review'
             AND (b.uploader_user_id IS NULL OR t.expert_user_id != b.uploader_user_id)
            THEN t.id
          END) AS peer_total,
          COUNT(DISTINCT CASE
            WHEN t.task_type = 'initial_review'
             AND (b.uploader_user_id IS NULL OR t.expert_user_id != b.uploader_user_id)
             AND t.status = 'submitted'
            THEN t.id
          END) AS peer_submitted,
          COUNT(DISTINCT CASE
            WHEN t.task_type = 'initial_review'
             AND (b.uploader_user_id IS NULL OR t.expert_user_id != b.uploader_user_id)
             AND t.status = 'in_progress'
            THEN t.id
          END) AS peer_in_progress
        FROM dataset_batches b
        LEFT JOIN qa_items q ON q.dataset_batch_id = b.id
        LEFT JOIN qa_answers ans ON ans.qa_item_id = q.id AND ans.is_current = 1
        LEFT JOIN evaluation_tasks t ON t.answer_id = ans.id
        WHERE b.id = ?
        GROUP BY b.id
        """,
        (batch_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="batch not found")

    if row["uploader_user_id"] is None:
        self_status = "none"
    else:
        self_state = compute_progress_status(
            int(row["self_total"] or 0),
            int(row["self_submitted"] or 0),
            int(row["self_in_progress"] or 0),
        )
        self_status = "submitted" if self_state == "completed" else self_state

    peer_state = compute_progress_status(
        int(row["peer_total"] or 0),
        int(row["peer_submitted"] or 0),
        int(row["peer_in_progress"] or 0),
    )
    peer_status = "completed" if peer_state == "completed" else peer_state

    cursor.execute(
        """
        UPDATE dataset_batches
        SET self_review_status = ?, peer_review_status = ?
        WHERE id = ?
        """,
        (self_status, peer_status, batch_id),
    )
    return {
        "self_review_status": self_status,
        "peer_review_status": peer_status,
        "self_review_total": int(row["self_total"] or 0),
        "self_review_submitted": int(row["self_submitted"] or 0),
        "peer_review_total": int(row["peer_total"] or 0),
        "peer_review_submitted": int(row["peer_submitted"] or 0),
    }


def assign_peer_review_tasks_for_batch(cursor, batch_id: int, uploader_user_id: Optional[int]) -> dict:
    batch = cursor.execute(
        """
        SELECT id, application_id
        FROM dataset_batches
        WHERE id = ?
        """,
        (batch_id,),
    ).fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")

    experts = load_application_experts(cursor, int(batch["application_id"]))
    rows = cursor.execute(
        """
        SELECT
          q.id AS qa_item_id,
          ans.id AS answer_id,
          q.business_tags_json
        FROM qa_items q
        JOIN qa_answers ans ON ans.qa_item_id = q.id
        WHERE q.dataset_batch_id = ?
          AND ans.is_current = 1
        ORDER BY q.id ASC, ans.id ASC
        """,
        (batch_id,),
    ).fetchall()

    created_count = 0
    covered_count = 0
    blocked_count = 0

    for row in rows:
        qa_business_tags = parse_tag_codes(row["business_tags_json"])
        eligible_expert_ids = [
            expert_id
            for expert_id, expert in experts.items()
            if expert_id != uploader_user_id
            and expert_can_review_business_tags(
                qa_business_tags,
                expert["allow_cross_business_review"],
                expert["business_tags"],
            )
        ]
        if not eligible_expert_ids:
            blocked_count += 1
            continue

        existing_expert_rows = cursor.execute(
            """
            SELECT expert_user_id
            FROM evaluation_tasks
            WHERE answer_id = ?
              AND task_type = 'initial_review'
            ORDER BY expert_user_id ASC
            """,
            (row["answer_id"],),
        ).fetchall()
        abandoned_rows = cursor.execute(
            """
            SELECT expert_user_id
            FROM expert_task_abandons
            WHERE answer_id = ?
              AND task_type = 'initial_review'
            ORDER BY expert_user_id ASC
            """,
            (row["answer_id"],),
        ).fetchall()
        existing_expert_ids = {int(task_row["expert_user_id"]) for task_row in existing_expert_rows}
        existing_expert_ids.update(int(task_row["expert_user_id"]) for task_row in abandoned_rows)
        assigned_count = len(existing_expert_rows)

        if assigned_count >= 2:
            covered_count += 1
            continue

        for expert_id in eligible_expert_ids:
            if expert_id in existing_expert_ids:
                continue
            cursor.execute(
                """
                INSERT OR IGNORE INTO evaluation_tasks (
                  qa_item_id, answer_id, expert_user_id, round_no,
                  task_type, status, assigned_at
                ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
                """,
                (row["qa_item_id"], row["answer_id"], expert_id, now_iso()),
            )
            if cursor.rowcount:
                created_count += 1
                assigned_count += 1
                existing_expert_ids.add(expert_id)
            if assigned_count >= 2:
                break

        if assigned_count >= 2:
            covered_count += 1
            cursor.execute(
                "UPDATE qa_items SET status = 'in_review' WHERE id = ?",
                (row["qa_item_id"],),
            )
        else:
            blocked_count += 1

    return {
        "created_count": created_count,
        "covered_count": covered_count,
        "blocked_count": blocked_count,
        "item_count": len(rows),
    }


def get_task(task_id: int, expert_user_id: int):
    with db_cursor() as cursor:
        task = cursor.execute(
            """
            SELECT
              t.*,
              q.business_tags_json,
              q.dataset_batch_id,
              b.uploader_user_id AS batch_uploader_user_id
            FROM evaluation_tasks t
            JOIN qa_items q ON q.id = t.qa_item_id
            LEFT JOIN dataset_batches b ON b.id = q.dataset_batch_id
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
        if not can_access_by_business_scope(
            allow_cross,
            business_tags,
            task["business_tags_json"],
        ) and not can_access_uploaded_batch(task, expert_user_id):
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


@router.post("/imports/push")
def push_import_batch(
    payload: ExpertImportPushPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    if not payload.rows:
        raise HTTPException(status_code=400, detail="rows must not be empty")

    business_tags = [code for code in payload.business_tag_codes if code]
    application_db_id, technical_type_id = validate_expert_import_target(
        current_user,
        payload.application_id,
        payload.technical_type_code,
        business_tags,
    )

    with db_cursor() as cursor:
        existing_batch = None
        if payload.external_batch_id:
            existing_batch = cursor.execute(
                """
                SELECT
                  id,
                  source,
                  external_batch_id,
                  import_status,
                  self_review_status,
                  peer_review_status,
                  parse_lock_token,
                  parse_lock_acquired_at
                FROM dataset_batches
                WHERE source = ?
                  AND uploader_user_id = ?
                  AND external_batch_id = ?
                """,
                (payload.source, current_user["id"], payload.external_batch_id),
            ).fetchone()

    if existing_batch:
        job_id = None
        parse_queued = False
        if payload.auto_parse and existing_batch["import_status"] == "uploaded":
            job_id, parse_queued = queue_unique_import_job(int(existing_batch["id"]))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "existing_batch": True,
                "job_id": job_id,
                "parse_queued": parse_queued,
                **serialize_import_batch_status(existing_batch),
            },
        }

    rows = build_import_batch_payload(payload.rows)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{current_user['id']}_{uuid4().hex}_expert_import.json"
    file_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    batch_id = create_dataset_batch(
        name=payload.name,
        source=payload.source,
        source_batch_name=payload.source_batch_name,
        external_batch_id=payload.external_batch_id,
        file_path=file_path,
        application_id=application_db_id,
        technical_type_id=technical_type_id,
        business_tags=business_tags,
        created_by=current_user["id"],
        uploader_user_id=current_user["id"],
        self_review_status="queued" if payload.create_self_review else "none",
        peer_review_status="none",
    )

    job_id = None
    parse_queued = False
    if payload.auto_parse:
        job_id, parse_queued = queue_unique_import_job(batch_id)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "existing_batch": False,
            "job_id": job_id,
            "parse_queued": parse_queued,
            "batch_id": batch_id,
            "exists": True,
            "source": payload.source,
            "external_batch_id": payload.external_batch_id,
            "import_status": "uploaded",
            "is_processing": False,
            "batch_status": "uploaded",
            "self_review_status": "queued" if payload.create_self_review else "none",
            "peer_review_status": "none",
        },
    }


@router.post("/imports/status")
def lookup_import_batch_statuses(
    payload: ExpertImportStatusLookupPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    if not payload.items:
        return {"code": 0, "message": "ok", "data": []}

    normalized_items: list[tuple[str, str]] = []
    for item in payload.items:
        source = item.source.strip()
        external_batch_id = item.external_batch_id.strip()
        if not source:
            raise HTTPException(status_code=400, detail="source must not be empty")
        if not external_batch_id:
            raise HTTPException(status_code=400, detail="external_batch_id must not be empty")
        normalized_items.append((source, external_batch_id))

    if len(normalized_items) > 500:
        raise HTTPException(status_code=400, detail="items must not exceed 500")

    unique_items = list(dict.fromkeys(normalized_items))
    conditions = " OR ".join("(b.source = ? AND b.external_batch_id = ?)" for _ in unique_items)
    params: list[object] = [current_user["id"]]
    for source, external_batch_id in unique_items:
        params.extend([source, external_batch_id])

    with db_cursor() as cursor:
        rows = cursor.execute(
            f"""
            SELECT
              b.id,
              b.name,
              b.source,
              b.source_batch_name,
              b.external_batch_id,
              b.file_path,
              b.import_status,
              b.total_count,
              b.success_count,
              b.fail_count,
              b.created_at,
              b.application_id,
              b.uploader_user_id,
              b.self_review_status,
              b.peer_review_status,
              b.parse_lock_token,
              b.parse_lock_acquired_at,
              b.business_tags_json,
              a.name AS application_name,
              tt.code AS technical_type_code,
              tt.name AS technical_type_name
            FROM dataset_batches b
            LEFT JOIN applications a ON a.id = b.application_id
            LEFT JOIN technical_types tt ON tt.id = b.technical_type_id
            WHERE b.uploader_user_id = ?
              AND ({conditions})
            """,
            tuple(params),
        ).fetchall()

    batch_map = {
        (str(row["source"]), str(row["external_batch_id"])): serialize_import_batch_status(row)
        for row in rows
    }
    data = [
        batch_map.get((source, external_batch_id))
        or serialize_missing_import_batch_status(source, external_batch_id)
        for source, external_batch_id in normalized_items
    ]
    return {"code": 0, "message": "ok", "data": data}


@router.get("/imports")
def list_import_batches(current_user: CurrentUser = Depends(require_expert)):
    query = """
        SELECT
          b.id,
          b.name,
          b.source,
          b.source_batch_name,
          b.external_batch_id,
          b.file_path,
          b.import_status,
          b.total_count,
          b.success_count,
          b.fail_count,
          b.created_at,
          b.application_id,
          b.uploader_user_id,
          b.self_review_status,
          b.peer_review_status,
          b.parse_lock_token,
          b.parse_lock_acquired_at,
          b.business_tags_json,
          a.name AS application_name,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            JOIN qa_answers ans ON ans.id = t.answer_id
            JOIN qa_items q ON q.id = ans.qa_item_id
            WHERE q.dataset_batch_id = b.id
              AND t.task_type = 'initial_review'
              AND b.uploader_user_id IS NOT NULL
              AND t.expert_user_id = b.uploader_user_id
          ) AS self_review_total,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            JOIN qa_answers ans ON ans.id = t.answer_id
            JOIN qa_items q ON q.id = ans.qa_item_id
            WHERE q.dataset_batch_id = b.id
              AND t.task_type = 'initial_review'
              AND b.uploader_user_id IS NOT NULL
              AND t.expert_user_id = b.uploader_user_id
              AND t.status = 'submitted'
          ) AS self_review_submitted,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            JOIN qa_answers ans ON ans.id = t.answer_id
            JOIN qa_items q ON q.id = ans.qa_item_id
            WHERE q.dataset_batch_id = b.id
              AND t.task_type = 'initial_review'
              AND (b.uploader_user_id IS NULL OR t.expert_user_id != b.uploader_user_id)
          ) AS peer_review_total,
          (
            SELECT COUNT(*)
            FROM evaluation_tasks t
            JOIN qa_answers ans ON ans.id = t.answer_id
            JOIN qa_items q ON q.id = ans.qa_item_id
            WHERE q.dataset_batch_id = b.id
              AND t.task_type = 'initial_review'
              AND (b.uploader_user_id IS NULL OR t.expert_user_id != b.uploader_user_id)
              AND t.status = 'submitted'
          ) AS peer_review_submitted
        FROM dataset_batches b
        LEFT JOIN applications a ON a.id = b.application_id
        LEFT JOIN technical_types tt ON tt.id = b.technical_type_id
        WHERE b.uploader_user_id = ?
    """
    query += " ORDER BY b.id DESC"

    with db_cursor() as cursor:
        rows = cursor.execute(query, (current_user["id"],)).fetchall()
        virtual_batch = build_virtual_remote_batch_status(cursor, current_user)
    data = [serialize_import_batch_status(row) for row in rows]
    if virtual_batch:
        data.append(virtual_batch)
    data.sort(key=lambda item: str(item["created_at"]), reverse=True)
    return {
        "code": 0,
        "message": "ok",
        "data": data,
    }


@router.get("/imports/{batch_id}")
def get_import_batch_detail(batch_id: int, current_user: CurrentUser = Depends(require_expert)):
    if batch_id == VIRTUAL_REMOTE_BATCH_ID:
        with db_cursor() as cursor:
            batch = build_virtual_remote_batch_status(cursor, current_user)
            if not batch:
                raise HTTPException(status_code=404, detail="batch not found")
            rows = list_visible_unbatched_qa_rows(cursor, current_user)

        items = [
            {
                "id": int(row["id"]),
                "external_id": row["external_id"],
                "status": row["status"],
                "question_text": row["question_text"],
                "question_summary": str(row["question_text"])[:120],
                "source": row["source"],
                "source_model": row["source_model"],
                "metadata_json": row["metadata_json"],
                "current_answer_id": row["current_answer_id"],
                "current_answer_text": row["current_answer_text"],
                "self_review_task_status": row["self_review_task_status"],
                "peer_review_total": int(row["peer_review_total"] or 0),
                "peer_review_submitted": int(row["peer_review_submitted"] or 0),
            }
            for row in rows
        ]
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "batch": batch,
                "failures": [],
                "items": items,
            },
        }

    with db_cursor() as cursor:
        batch = get_import_batch(cursor, batch_id, current_user)
        failures = cursor.execute(
            """
            SELECT id, row_no, external_id, question_preview, error_message, raw_payload_json, created_at
            FROM dataset_batch_failures
            WHERE dataset_batch_id = ?
            ORDER BY row_no ASC, id ASC
            """,
            (batch_id,),
        ).fetchall()
        items = cursor.execute(
            """
            SELECT
              q.id,
              q.external_id,
              q.status,
              q.question_text,
              q.source,
              q.source_model,
              q.metadata_json,
              ans.id AS current_answer_id,
              ans.answer_text AS current_answer_text,
              (
                SELECT t.status
                FROM evaluation_tasks t
                WHERE t.answer_id = ans.id
                  AND t.task_type = 'initial_review'
                  AND b.uploader_user_id IS NOT NULL
                  AND t.expert_user_id = b.uploader_user_id
                ORDER BY t.id DESC
                LIMIT 1
              ) AS self_review_task_status,
              (
                SELECT COUNT(*)
                FROM evaluation_tasks t
                WHERE t.answer_id = ans.id
                  AND t.task_type = 'initial_review'
                  AND (b.uploader_user_id IS NULL OR t.expert_user_id != b.uploader_user_id)
              ) AS peer_review_total,
              (
                SELECT COUNT(*)
                FROM evaluation_tasks t
                WHERE t.answer_id = ans.id
                  AND t.task_type = 'initial_review'
                  AND (b.uploader_user_id IS NULL OR t.expert_user_id != b.uploader_user_id)
                  AND t.status = 'submitted'
              ) AS peer_review_submitted
            FROM dataset_batches b
            JOIN qa_items q ON q.dataset_batch_id = b.id
            LEFT JOIN qa_answers ans ON ans.qa_item_id = q.id AND ans.is_current = 1
            WHERE b.id = ?
            ORDER BY q.id DESC
            """,
            (batch_id,),
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "batch": serialize_import_batch_status(batch),
            "failures": [dict(row) for row in failures],
            "items": [
                {
                    **dict(row),
                    "question_summary": str(row["question_text"])[:120],
                }
                for row in items
            ],
        },
    }


@router.post("/imports/{batch_id}/submit-for-peer-review")
def submit_import_batch_for_peer_review(
    batch_id: int,
    current_user: CurrentUser = Depends(require_expert),
):
    with db_cursor() as cursor:
        batch = get_import_batch(cursor, batch_id, current_user)
        if batch["import_status"] != "parsed":
            raise HTTPException(status_code=409, detail="batch is not parsed yet")
        if int(batch["success_count"] or 0) <= 0:
            raise HTTPException(status_code=409, detail="batch has no parsed qa rows")
        if batch["self_review_status"] not in {"none", "submitted"}:
            raise HTTPException(status_code=409, detail="self review is not finished")

        result = assign_peer_review_tasks_for_batch(
            cursor,
            batch_id,
            int(batch["uploader_user_id"]) if batch["uploader_user_id"] is not None else None,
        )
        statuses = refresh_import_batch_review_status(cursor, batch_id)

    if result["created_count"] <= 0 and result["covered_count"] <= 0:
        raise HTTPException(status_code=409, detail="no eligible peer reviewers available")

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "batch_id": batch_id,
            **result,
            **statuses,
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
              b.uploader_user_id AS batch_uploader_user_id,
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
            LEFT JOIN dataset_batches b ON b.id = q.dataset_batch_id
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
        if not can_access_by_business_scope(
            allow_cross,
            business_tags,
            row["business_tags_json"],
        ) and not can_access_uploaded_batch(row, current_user["id"]):
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
          q.metadata_json,
          b.uploader_user_id AS batch_uploader_user_id,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          q.question_text
        FROM evaluation_tasks t
        JOIN qa_items q ON q.id = t.qa_item_id
        LEFT JOIN dataset_batches b ON b.id = q.dataset_batch_id
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
        if not can_access_by_business_scope(
            allow_cross,
            business_tags,
            row["business_tags_json"],
        ) and not can_access_uploaded_batch(row, current_user["id"]):
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
            SELECT
              id,
              purpose,
              status,
              created_at,
              llm_config_id,
              llm_config_name,
              llm_model_name
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
    task = get_task(task_id, current_user["id"])
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
        if task["dataset_batch_id"] is not None:
            refresh_import_batch_review_status(cursor, int(task["dataset_batch_id"]))
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
        if task["dataset_batch_id"] is not None:
            refresh_import_batch_review_status(cursor, int(task["dataset_batch_id"]))

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
        if task["dataset_batch_id"] is not None:
            refresh_import_batch_review_status(cursor, int(task["dataset_batch_id"]))
    job_id = queue_job(
        "aggregate",
        {"qa_item_id": task["qa_item_id"], "answer_id": task["answer_id"]},
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {"task_id": task_id, "status": "submitted", "aggregate_job_id": job_id},
    }
