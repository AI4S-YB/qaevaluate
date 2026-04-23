from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import CurrentUser, require_expert
from ..db import db_cursor
from ..llm_client import LlmClientError, call_openai_compatible_chat, iter_openai_compatible_chat
from ..llm_config_store import get_llm_api_key

router = APIRouter(prefix="/api/expert/model-trial", tags=["model-trial"])
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def parse_tag_codes(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    try:
        parsed = json.loads(value)
    except Exception:
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


def get_trial_llm_config(config_id: int) -> dict:
    with db_cursor() as cursor:
        config = cursor.execute(
            """
            SELECT
              id,
              name,
              llm_use_case,
              provider_code,
              provider_type,
              base_url,
              api_key,
              model_name,
              system_prompt,
              temperature,
              is_enabled,
              is_trial_enabled
            FROM llm_configs
            WHERE id = ?
            LIMIT 1
            """,
            (config_id,),
        ).fetchone()
    if not config:
        raise HTTPException(status_code=404, detail="llm config not found")
    if not bool(config["is_enabled"]):
        raise HTTPException(status_code=400, detail="selected llm config is disabled")
    if (config["llm_use_case"] or "evaluation") != "trial":
        raise HTTPException(status_code=400, detail="selected llm config is not available for trial")
    api_key = get_llm_api_key(int(config["id"]), config["api_key"])
    if not api_key:
        raise HTTPException(status_code=400, detail="selected llm config missing local api key")
    if config["provider_type"] != "openai_compatible":
        raise HTTPException(status_code=400, detail="unsupported provider")
    return {
        **dict(config),
        "resolved_api_key": api_key,
    }


def serialize_source(row) -> dict:
    return {
        "qa_item_id": int(row["qa_item_id"]),
        "answer_id": int(row["answer_id"]),
        "question_text": row["question_text"],
        "answer_text": row["answer_text"],
        "context_text": row["context_text"],
        "application_name": row["application_name"],
        "technical_type_code": row["technical_type_code"],
        "technical_type_name": row["technical_type_name"],
        "task_type": row["task_type"],
        "task_status": row["task_status"],
        "updated_at": row["updated_at"],
        "question_summary": row["question_text"][:80],
    }


def list_available_sources(current_user: CurrentUser) -> list[dict]:
    with db_cursor() as cursor:
        allow_cross, business_tags = get_expert_scope(cursor, current_user)
        rows = cursor.execute(
            """
            SELECT
              t.qa_item_id,
              t.answer_id,
              q.question_text,
              q.context_text,
              q.business_tags_json,
              ans.answer_text,
              a.name AS application_name,
              tt.code AS technical_type_code,
              tt.name AS technical_type_name,
              t.task_type,
              t.status AS task_status,
              COALESCE(t.submitted_at, t.started_at, t.assigned_at) AS updated_at
            FROM evaluation_tasks t
            JOIN qa_items q ON q.id = t.qa_item_id
            JOIN qa_answers ans ON ans.id = t.answer_id
            JOIN applications a ON a.id = q.application_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
            WHERE t.expert_user_id = ?
            ORDER BY updated_at DESC, t.id DESC
            """,
            (current_user["id"],),
        ).fetchall()

    seen_qa_item_ids: set[int] = set()
    data: list[dict] = []
    for row in rows:
        if not can_access_by_business_scope(allow_cross, business_tags, row["business_tags_json"]):
            continue
        qa_item_id = int(row["qa_item_id"])
        if qa_item_id in seen_qa_item_ids:
            continue
        seen_qa_item_ids.add(qa_item_id)
        data.append(serialize_source(row))
    return data


def get_source_for_user(
    current_user: CurrentUser,
    qa_item_id: Optional[int],
    answer_id: Optional[int],
) -> Optional[dict]:
    if qa_item_id is None or answer_id is None:
        return None
    sources = list_available_sources(current_user)
    for item in sources:
        if item["qa_item_id"] == qa_item_id and item["answer_id"] == answer_id:
            return item
    raise HTTPException(status_code=404, detail="source qa not found")


def get_trial_session(session_id: int, current_user: CurrentUser):
    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT
              s.id,
              s.expert_user_id,
              s.llm_config_id,
              s.llm_config_name,
              s.llm_model_name,
              s.source_qa_item_id,
              s.source_answer_id,
              s.title,
              s.status,
              s.created_at,
              s.updated_at,
              q.question_text,
              q.context_text,
              ans.answer_text,
              a.name AS application_name,
              tt.code AS technical_type_code,
              tt.name AS technical_type_name
            FROM model_trial_sessions s
            LEFT JOIN qa_items q ON q.id = s.source_qa_item_id
            LEFT JOIN qa_answers ans ON ans.id = s.source_answer_id
            LEFT JOIN applications a ON a.id = q.application_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
            WHERE s.id = ? AND s.expert_user_id = ?
            """,
            (session_id, current_user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="trial session not found")
    return row


def build_trial_messages(config: dict, source: Optional[dict], history: list[dict], user_prompt: str):
    messages = [
        {
            "role": "system",
            "content": (
                (config.get("system_prompt") or "").strip()
                or (
                    "你是 QA 评测平台里的模型试用助手。"
                    "当前场景不是正式评测打分，而是供专家通过对话检查模型表现。"
                    "如果给了参考 QA，请把它视为试用素材；可以直接回答问题，也可以分析答案、改写答案或解释推理。"
                    "默认使用中文回答，除非用户明确要求其它语言。"
                )
            ),
        }
    ]
    if source:
        source_lines = [
            "当前选中的参考 QA 如下，可作为本轮对话上下文：",
            f"问题：{source['question_text']}",
            f"参考答案：{source['answer_text']}",
            f"项目：{source['application_name']}",
            f"QA 类型：{source['technical_type_name'] or source['technical_type_code'] or '未指定'}",
        ]
        if source.get("context_text"):
            source_lines.append(f"背景信息：{source['context_text']}")
        source_lines.append("如果用户直接让你回答问题，请优先围绕这道题给出答案。")
        messages.append({"role": "system", "content": "\n".join(source_lines)})

    for item in history:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_prompt})
    return messages


def update_trial_session_status(session_id: int, status: str) -> None:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "UPDATE model_trial_sessions SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), session_id),
            )
    except Exception:
        logger.exception(
            "failed to update model trial session status session_id=%s status=%s",
            session_id,
            status,
        )


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def log_trial_event(
    event: str,
    *,
    session_id: int,
    user_id: int,
    config_id: Optional[int] = None,
    source_qa_item_id: Optional[int] = None,
    source_answer_id: Optional[int] = None,
    content_length: Optional[int] = None,
    history_count: Optional[int] = None,
    reply_length: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    fields: list[str] = [
        f"event={event}",
        f"session_id={session_id}",
        f"user_id={user_id}",
    ]
    if config_id is not None:
        fields.append(f"config_id={config_id}")
    if source_qa_item_id is not None:
        fields.append(f"source_qa_item_id={source_qa_item_id}")
    if source_answer_id is not None:
        fields.append(f"source_answer_id={source_answer_id}")
    if content_length is not None:
        fields.append(f"content_length={content_length}")
    if history_count is not None:
        fields.append(f"history_count={history_count}")
    if reply_length is not None:
        fields.append(f"reply_length={reply_length}")
    if detail:
        fields.append(f"detail={detail}")
    logger.info("model_trial %s", " ".join(fields))


class CreateTrialSessionPayload(BaseModel):
    llm_config_id: int
    source_qa_item_id: Optional[int] = None
    source_answer_id: Optional[int] = None
    title: Optional[str] = None


class TrialMessagePayload(BaseModel):
    content: str


@router.get("/configs")
def list_trial_llm_configs(current_user: CurrentUser = Depends(require_expert)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              id,
              name,
              provider_code,
              model_name,
              is_enabled,
              llm_use_case,
              is_trial_enabled,
              api_key,
              last_tested_at,
              last_test_status
            FROM llm_configs
            WHERE is_enabled = 1 AND llm_use_case = 'trial'
            ORDER BY id DESC
            """
        ).fetchall()

    data = []
    for row in rows:
        api_key = get_llm_api_key(int(row["id"]), row["api_key"])
        data.append(
            {
                "id": int(row["id"]),
                "name": row["name"],
                "provider_code": row["provider_code"],
                "model_name": row["model_name"],
                "is_enabled": bool(row["is_enabled"]),
                "is_trial_enabled": bool(row["is_trial_enabled"]),
                "has_api_key": bool(api_key),
                "last_tested_at": row["last_tested_at"],
                "last_test_status": row["last_test_status"],
            }
        )
    return {"code": 0, "message": "ok", "data": data}


@router.get("/sources")
def list_trial_sources(current_user: CurrentUser = Depends(require_expert)):
    return {"code": 0, "message": "ok", "data": list_available_sources(current_user)}


@router.get("/sessions")
def list_trial_sessions(current_user: CurrentUser = Depends(require_expert)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              s.id,
              s.llm_config_id,
              s.llm_config_name,
              s.llm_model_name,
              s.title,
              s.status,
              s.created_at,
              s.updated_at,
              q.question_text
            FROM model_trial_sessions s
            LEFT JOIN qa_items q ON q.id = s.source_qa_item_id
            WHERE s.expert_user_id = ?
            ORDER BY s.updated_at DESC, s.id DESC
            """,
            (current_user["id"],),
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [
            {
                "id": int(row["id"]),
                "llm_config_id": int(row["llm_config_id"]),
                "llm_config_name": row["llm_config_name"],
                "llm_model_name": row["llm_model_name"],
                "title": row["title"] or (row["question_text"][:60] if row["question_text"] else f"会话 #{row['id']}"),
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }


@router.post("/sessions")
def create_trial_session(
    payload: CreateTrialSessionPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    config = get_trial_llm_config(payload.llm_config_id)
    source = get_source_for_user(current_user, payload.source_qa_item_id, payload.source_answer_id)
    created_at = now_iso()
    title = (payload.title or "").strip() or (source["question_text"][:60] if source else config["name"])
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO model_trial_sessions (
              expert_user_id, llm_config_id, llm_config_name, llm_model_name,
              source_qa_item_id, source_answer_id, title, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)
            """,
            (
                current_user["id"],
                config["id"],
                config["name"],
                config["model_name"],
                payload.source_qa_item_id,
                payload.source_answer_id,
                title,
                created_at,
                created_at,
            ),
        )
        session_id = int(cursor.lastrowid)
    log_trial_event(
        "session_created",
        session_id=session_id,
        user_id=int(current_user["id"]),
        config_id=int(config["id"]),
        source_qa_item_id=int(payload.source_qa_item_id) if payload.source_qa_item_id is not None else None,
        source_answer_id=int(payload.source_answer_id) if payload.source_answer_id is not None else None,
    )
    return {"code": 0, "message": "ok", "data": {"session_id": session_id}}


@router.get("/sessions/{session_id}")
def get_trial_session_detail(session_id: int, current_user: CurrentUser = Depends(require_expert)):
    session = get_trial_session(session_id, current_user)
    with db_cursor() as cursor:
        messages = cursor.execute(
            """
            SELECT id, role, content, created_at
            FROM model_trial_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "session": {
                "id": int(session["id"]),
                "llm_config_id": int(session["llm_config_id"]),
                "llm_config_name": session["llm_config_name"],
                "llm_model_name": session["llm_model_name"],
                "title": session["title"] or f"会话 #{session['id']}",
                "status": session["status"],
                "created_at": session["created_at"],
                "updated_at": session["updated_at"],
            },
            "source": (
                {
                    "qa_item_id": int(session["source_qa_item_id"]),
                    "answer_id": int(session["source_answer_id"]) if session["source_answer_id"] is not None else None,
                    "question_text": session["question_text"],
                    "answer_text": session["answer_text"],
                    "context_text": session["context_text"],
                    "application_name": session["application_name"],
                    "technical_type_code": session["technical_type_code"],
                    "technical_type_name": session["technical_type_name"],
                    "question_summary": (session["question_text"] or "")[:80],
                }
                if session["source_qa_item_id"] is not None
                else None
            ),
            "messages": [dict(row) for row in messages],
        },
    }


@router.delete("/sessions/{session_id}")
def delete_trial_session(session_id: int, current_user: CurrentUser = Depends(require_expert)):
    get_trial_session(session_id, current_user)
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM model_trial_messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM model_trial_sessions WHERE id = ?", (session_id,))
    return {"code": 0, "message": "ok", "data": {"session_id": session_id, "status": "deleted"}}


@router.post("/sessions/{session_id}/stream")
def stream_trial_message(
    session_id: int,
    payload: TrialMessagePayload,
    current_user: CurrentUser = Depends(require_expert),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="message content is required")

    session = get_trial_session(session_id, current_user)
    config = get_trial_llm_config(int(session["llm_config_id"]))
    source_qa_item_id = (
        int(session["source_qa_item_id"]) if session["source_qa_item_id"] is not None else None
    )
    source_answer_id = (
        int(session["source_answer_id"]) if session["source_answer_id"] is not None else None
    )
    source = (
        {
            "question_text": session["question_text"],
            "answer_text": session["answer_text"],
            "context_text": session["context_text"],
            "application_name": session["application_name"],
            "technical_type_code": session["technical_type_code"],
            "technical_type_name": session["technical_type_name"],
        }
        if session["source_qa_item_id"] is not None
        else None
    )

    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            "UPDATE model_trial_sessions SET status = 'active', updated_at = ? WHERE id = ?",
            (created_at, session_id),
        )
        cursor.execute(
            """
            INSERT INTO model_trial_messages (session_id, role, content, created_at)
            VALUES (?, 'user', ?, ?)
            """,
            (session_id, content, created_at),
        )
        history_rows = cursor.execute(
            """
            SELECT role, content
            FROM model_trial_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    log_trial_event(
        "stream_message_start",
        session_id=session_id,
        user_id=int(current_user["id"]),
        config_id=int(session["llm_config_id"]),
        source_qa_item_id=source_qa_item_id,
        source_answer_id=source_answer_id,
        content_length=len(content),
        history_count=len(history_rows),
    )

    request_messages = build_trial_messages(
        config=config,
        source=source,
        history=[dict(row) for row in history_rows[:-1]],
        user_prompt=content,
    )

    def generate() -> Iterator[str]:
        assistant_text = ""
        try:
            yield sse_event("started", {"session_id": session_id})
            for chunk in iter_openai_compatible_chat(
                base_url=config["base_url"],
                api_key=config["resolved_api_key"],
                model_name=config["model_name"],
                messages=request_messages,
                temperature=float(config["temperature"] or 0.2),
            ):
                assistant_text += chunk
                yield sse_event("delta", {"content": chunk})

            completed_at = now_iso()
            with db_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO model_trial_messages (session_id, role, content, created_at)
                    VALUES (?, 'assistant', ?, ?)
                    """,
                    (session_id, assistant_text, completed_at),
                )
                cursor.execute(
                    "UPDATE model_trial_sessions SET status = 'completed', updated_at = ? WHERE id = ?",
                    (completed_at, session_id),
                )

            log_trial_event(
                "stream_message_completed",
                session_id=session_id,
                user_id=int(current_user["id"]),
                config_id=int(session["llm_config_id"]),
                source_qa_item_id=source_qa_item_id,
                source_answer_id=source_answer_id,
                content_length=len(content),
                history_count=len(history_rows),
                reply_length=len(assistant_text),
            )
            yield sse_event(
                "done",
                {"session_id": session_id, "reply": assistant_text, "status": "completed"},
            )
        except LlmClientError as exc:
            update_trial_session_status(session_id, "failed")
            log_trial_event(
                "stream_message_upstream_failed",
                session_id=session_id,
                user_id=int(current_user["id"]),
                config_id=int(session["llm_config_id"]),
                source_qa_item_id=source_qa_item_id,
                source_answer_id=source_answer_id,
                content_length=len(content),
                history_count=len(history_rows),
                detail=str(exc),
            )
            yield sse_event("error", {"detail": str(exc), "status_code": 502})
        except Exception as exc:
            update_trial_session_status(session_id, "failed")
            log_trial_event(
                "stream_message_unexpected_failed",
                session_id=session_id,
                user_id=int(current_user["id"]),
                config_id=int(session["llm_config_id"]),
                source_qa_item_id=source_qa_item_id,
                source_answer_id=source_answer_id,
                content_length=len(content),
                history_count=len(history_rows),
                detail=exc.__class__.__name__,
            )
            logger.exception(
                "unexpected model trial stream failure session_id=%s user_id=%s",
                session_id,
                current_user["id"],
            )
            yield sse_event(
                "error",
                {
                    "detail": "model trial stream failed unexpectedly; see server logs",
                    "status_code": 500,
                },
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/messages")
def send_trial_message(
    session_id: int,
    payload: TrialMessagePayload,
    current_user: CurrentUser = Depends(require_expert),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="message content is required")

    try:
        session = get_trial_session(session_id, current_user)
        config = get_trial_llm_config(int(session["llm_config_id"]))
        source_qa_item_id = (
            int(session["source_qa_item_id"]) if session["source_qa_item_id"] is not None else None
        )
        source_answer_id = (
            int(session["source_answer_id"]) if session["source_answer_id"] is not None else None
        )
        source = (
            {
                "question_text": session["question_text"],
                "answer_text": session["answer_text"],
                "context_text": session["context_text"],
                "application_name": session["application_name"],
                "technical_type_code": session["technical_type_code"],
                "technical_type_name": session["technical_type_name"],
            }
            if session["source_qa_item_id"] is not None
            else None
        )
        log_trial_event(
            "message_start",
            session_id=session_id,
            user_id=int(current_user["id"]),
            config_id=int(session["llm_config_id"]),
            source_qa_item_id=source_qa_item_id,
            source_answer_id=source_answer_id,
            content_length=len(content),
        )

        created_at = now_iso()
        with db_cursor() as cursor:
            cursor.execute(
                "UPDATE model_trial_sessions SET status = 'active', updated_at = ? WHERE id = ?",
                (created_at, session_id),
            )
            cursor.execute(
                """
                INSERT INTO model_trial_messages (session_id, role, content, created_at)
                VALUES (?, 'user', ?, ?)
                """,
                (session_id, content, created_at),
            )
            history_rows = cursor.execute(
                """
                SELECT role, content
                FROM model_trial_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        log_trial_event(
            "message_persisted",
            session_id=session_id,
            user_id=int(current_user["id"]),
            config_id=int(session["llm_config_id"]),
            source_qa_item_id=source_qa_item_id,
            source_answer_id=source_answer_id,
            content_length=len(content),
            history_count=len(history_rows),
        )

        try:
            reply = call_openai_compatible_chat(
                base_url=config["base_url"],
                api_key=config["resolved_api_key"],
                model_name=config["model_name"],
                messages=build_trial_messages(
                    config=config,
                    source=source,
                    history=[dict(row) for row in history_rows[:-1]],
                    user_prompt=content,
                ),
                temperature=float(config["temperature"] or 0.2),
            )
        except LlmClientError as exc:
            update_trial_session_status(session_id, "failed")
            log_trial_event(
                "message_upstream_failed",
                session_id=session_id,
                user_id=int(current_user["id"]),
                config_id=int(session["llm_config_id"]),
                source_qa_item_id=source_qa_item_id,
                source_answer_id=source_answer_id,
                content_length=len(content),
                history_count=len(history_rows),
                detail=str(exc),
            )
            logger.warning(
                "model trial upstream request failed session_id=%s user_id=%s config_id=%s error=%s",
                session_id,
                current_user["id"],
                session["llm_config_id"],
                str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        completed_at = now_iso()
        with db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO model_trial_messages (session_id, role, content, created_at)
                VALUES (?, 'assistant', ?, ?)
                """,
                (session_id, reply, completed_at),
            )
            cursor.execute(
                "UPDATE model_trial_sessions SET status = 'completed', updated_at = ? WHERE id = ?",
                (completed_at, session_id),
            )
        log_trial_event(
            "message_completed",
            session_id=session_id,
            user_id=int(current_user["id"]),
            config_id=int(session["llm_config_id"]),
            source_qa_item_id=source_qa_item_id,
            source_answer_id=source_answer_id,
            content_length=len(content),
            history_count=len(history_rows),
            reply_length=len(reply),
        )
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "reply": reply,
                "status": "completed",
                "session_id": session_id,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        update_trial_session_status(session_id, "failed")
        log_trial_event(
            "message_unexpected_failed",
            session_id=session_id,
            user_id=int(current_user["id"]),
            content_length=len(content),
            detail=exc.__class__.__name__,
        )
        logger.exception(
            "unexpected model trial message failure session_id=%s user_id=%s",
            session_id,
            current_user["id"],
        )
        raise HTTPException(
            status_code=500,
            detail="model trial message failed unexpectedly; see server logs",
        ) from exc
