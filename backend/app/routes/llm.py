from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUser, require_expert
from ..db import db_cursor
from ..jobs import queue_job

router = APIRouter(prefix="/api/expert/tasks", tags=["llm"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class SessionPayload(BaseModel):
    purpose: str


class MessagePayload(BaseModel):
    content: str


class RewritePayload(BaseModel):
    mode: str


def get_task(task_id: int, expert_user_id: int):
    with db_cursor() as cursor:
        task = cursor.execute(
            """
            SELECT id, qa_item_id, answer_id, expert_user_id
            FROM evaluation_tasks
            WHERE id = ? AND expert_user_id = ?
            """,
            (task_id, expert_user_id),
        ).fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/{task_id}/llm/sessions")
def create_session(
    task_id: int,
    payload: SessionPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO llm_sessions (
              task_id, qa_item_id, answer_id, expert_user_id, purpose, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                task["id"],
                task["qa_item_id"],
                task["answer_id"],
                task["expert_user_id"],
                payload.purpose,
                created_at,
            ),
        )
        session_id = cursor.lastrowid
    return {"code": 0, "message": "ok", "data": {"session_id": session_id}}


@router.get("/{task_id}/llm/sessions")
def list_sessions(task_id: int, current_user: CurrentUser = Depends(require_expert)):
    get_task(task_id, current_user["id"])
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, purpose, status, created_at
            FROM llm_sessions
            WHERE task_id = ?
            ORDER BY id DESC
            """,
            (task_id,),
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}


@router.post("/{task_id}/llm/sessions/{session_id}/messages")
def create_message(
    task_id: int,
    session_id: int,
    payload: MessagePayload,
    current_user: CurrentUser = Depends(require_expert),
):
    get_task(task_id, current_user["id"])
    created_at = now_iso()
    with db_cursor() as cursor:
        session = cursor.execute(
            """
            SELECT id, purpose
            FROM llm_sessions
            WHERE id = ? AND task_id = ?
            """,
            (session_id, task_id),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="session not found")

        cursor.execute(
            """
            INSERT INTO llm_messages (session_id, role, content, created_at)
            VALUES (?, 'user', ?, ?)
            """,
            (session_id, payload.content, created_at),
        )

    job_id = queue_job(
        "llm",
        {
            "task_id": task_id,
            "session_id": session_id,
            "action": session["purpose"],
            "prompt": payload.content,
        },
    )
    return {"code": 0, "message": "ok", "data": {"session_id": session_id, "job_id": job_id}}


@router.get("/{task_id}/llm/sessions/{session_id}/messages")
def list_messages(
    task_id: int,
    session_id: int,
    current_user: CurrentUser = Depends(require_expert),
):
    get_task(task_id, current_user["id"])
    with db_cursor() as cursor:
        session = cursor.execute(
            "SELECT id FROM llm_sessions WHERE id = ? AND task_id = ?",
            (session_id, task_id),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        rows = cursor.execute(
            """
            SELECT id, role, content, created_at
            FROM llm_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}


@router.post("/{task_id}/llm/rewrite")
def quick_rewrite(
    task_id: int,
    payload: RewritePayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO llm_sessions (
              task_id, qa_item_id, answer_id, expert_user_id, purpose, status, created_at
            ) VALUES (?, ?, ?, ?, 'rewrite', 'active', ?)
            """,
            (
                task["id"],
                task["qa_item_id"],
                task["answer_id"],
                task["expert_user_id"],
                created_at,
            ),
        )
        session_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO llm_messages (session_id, role, content, created_at)
            VALUES (?, 'user', ?, ?)
            """,
            (session_id, f"rewrite mode: {payload.mode}", created_at),
        )

    job_id = queue_job(
        "llm",
        {
            "task_id": task_id,
            "session_id": session_id,
            "action": "rewrite",
            "mode": payload.mode,
        },
    )
    return {
        "code": 0,
        "message": "ok",
        "data": {"session_id": session_id, "job_id": job_id},
    }


@router.get("/{task_id}/candidate-answers")
def list_candidate_answers(
    task_id: int,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, answer_text, answer_type, source_model, version_no, created_at
            FROM qa_answers
            WHERE qa_item_id = ?
            ORDER BY id DESC
            """,
            (task["qa_item_id"],),
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}
