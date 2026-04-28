import json
from datetime import datetime
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, require_expert
from ..db import db_cursor
from ..jobs import queue_job
from ..llm_client import (
    LlmClientError,
    build_auto_review_messages,
    build_task_messages,
    call_openai_compatible_chat,
    format_auto_review_message,
    format_review_message,
    iter_openai_compatible_chat,
    parse_auto_review_response,
    parse_review_response,
)
from ..llm_config_store import get_llm_api_key

router = APIRouter(prefix="/api/expert/tasks", tags=["llm"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class SessionPayload(BaseModel):
    purpose: str
    llm_config_id: Optional[int] = None


class ScoreContextPayload(BaseModel):
    correctness_rating: Optional[str] = None
    completeness_rating: Optional[str] = None
    relevance_rating: Optional[str] = None
    clarity_rating: Optional[str] = None
    risk_flag: Optional[str] = None
    reasoning_completeness: Optional[str] = None
    reasoning_consistency: Optional[str] = None
    reasoning_support: Optional[str] = None
    overall_decision: Optional[str] = None
    quick_comment_codes: list[str] = Field(default_factory=list)


class MessagePayload(BaseModel):
    content: str = ""
    target_answer_id: Optional[int] = None
    score_context: Optional[ScoreContextPayload] = None


class RewritePayload(BaseModel):
    mode: Optional[str] = None
    prompt: Optional[str] = None
    target_answer_id: Optional[int] = None
    llm_config_id: Optional[int] = None
    score_context: Optional[ScoreContextPayload] = None


class AutoReviewPayload(BaseModel):
    target_answer_id: Optional[int] = None
    llm_config_id: Optional[int] = None


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


def get_llm_config(config_id: Optional[int] = None) -> dict:
    with db_cursor() as cursor:
        if config_id is None:
            config = cursor.execute(
                """
                SELECT
                  id, name, llm_use_case, provider_code, provider_type, base_url, api_key,
                  model_name, system_prompt, temperature, max_tokens, top_p, is_enabled, is_active, is_trial_enabled
                FROM llm_configs
                WHERE is_active = 1 AND llm_use_case = 'evaluation'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        else:
            config = cursor.execute(
                """
                SELECT
                  id, name, llm_use_case, provider_code, provider_type, base_url, api_key,
                  model_name, system_prompt, temperature, max_tokens, top_p, is_enabled, is_active, is_trial_enabled
                FROM llm_configs
                WHERE id = ?
                LIMIT 1
                """,
                (config_id,),
            ).fetchone()
    if not config:
        raise HTTPException(status_code=400, detail="no primary llm config")
    if not bool(config["is_enabled"]):
        raise HTTPException(status_code=400, detail="selected llm config is disabled")
    if (config["llm_use_case"] or "evaluation") != "evaluation":
        raise HTTPException(status_code=400, detail="selected llm config is reserved for model trial only")
    api_key = get_llm_api_key(int(config["id"]), config["api_key"])
    if not api_key:
        raise HTTPException(status_code=400, detail="selected llm config missing local api key")
    if config["provider_type"] != "openai_compatible":
        raise HTTPException(status_code=400, detail="unsupported provider")
    return {
        **dict(config),
        "is_enabled": bool(config["is_enabled"]),
        "is_active": bool(config["is_active"]),
        "is_trial_enabled": bool(config["is_trial_enabled"]),
        "resolved_api_key": api_key,
    }


def ensure_active_llm_config() -> None:
    get_llm_config()


def normalize_answer_text(value: str) -> str:
    return " ".join(value.split())


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{task_id}/llm/sessions")
def create_session(
    task_id: int,
    payload: SessionPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    llm_config = get_llm_config(payload.llm_config_id)
    task = get_task(task_id, current_user["id"])
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO llm_sessions (
              task_id, qa_item_id, answer_id, expert_user_id,
              llm_config_id, llm_config_name, llm_model_name,
              purpose, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                task["id"],
                task["qa_item_id"],
                task["answer_id"],
                task["expert_user_id"],
                llm_config["id"],
                llm_config["name"],
                llm_config["model_name"],
                payload.purpose,
                created_at,
            ),
        )
        session_id = cursor.lastrowid
    return {"code": 0, "message": "ok", "data": {"session_id": session_id}}


@router.get("/{task_id}/llm/configs")
def list_available_llm_configs(
    task_id: int,
    current_user: CurrentUser = Depends(require_expert),
):
    get_task(task_id, current_user["id"])
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              id,
              name,
              provider_code,
              model_name,
              is_enabled,
              is_active,
              llm_use_case,
              is_trial_enabled,
              api_key,
              last_tested_at,
              last_test_status
            FROM llm_configs
            WHERE is_enabled = 1 AND llm_use_case = 'evaluation'
            ORDER BY is_active DESC, id DESC
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
                "is_primary": bool(row["is_active"]),
                "has_api_key": bool(api_key),
                "last_tested_at": row["last_tested_at"],
                "last_test_status": row["last_test_status"],
            }
        )
    return {"code": 0, "message": "ok", "data": data}


@router.get("/{task_id}/llm/sessions")
def list_sessions(task_id: int, current_user: CurrentUser = Depends(require_expert)):
    get_task(task_id, current_user["id"])
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, purpose, status, created_at, llm_config_id, llm_config_name, llm_model_name
            FROM llm_sessions
            WHERE task_id = ?
            ORDER BY id DESC
            """,
            (task_id,),
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}


@router.delete("/{task_id}/llm/sessions/{session_id}")
def delete_session(
    task_id: int,
    session_id: int,
    current_user: CurrentUser = Depends(require_expert),
):
    get_task(task_id, current_user["id"])
    with db_cursor() as cursor:
        session = cursor.execute(
            """
            SELECT id, status
            FROM llm_sessions
            WHERE id = ? AND task_id = ?
            """,
            (session_id, task_id),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        if session["status"] == "active":
            raise HTTPException(status_code=409, detail="session is still processing")

        cursor.execute("DELETE FROM llm_messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM llm_sessions WHERE id = ?", (session_id,))

    return {"code": 0, "message": "ok", "data": {"session_id": session_id, "status": "deleted"}}


@router.post("/{task_id}/llm/sessions/{session_id}/messages")
def create_message(
    task_id: int,
    session_id: int,
    payload: MessagePayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    created_at = now_iso()
    with db_cursor() as cursor:
        session = cursor.execute(
            """
            SELECT id, purpose, llm_config_id
            FROM llm_sessions
            WHERE id = ? AND task_id = ?
            """,
            (session_id, task_id),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="session not found")

        target_answer_id = payload.target_answer_id or task["answer_id"]
        target_answer = cursor.execute(
            """
            SELECT id
            FROM qa_answers
            WHERE id = ? AND qa_item_id = ?
            """,
            (target_answer_id, task["qa_item_id"]),
        ).fetchone()
        if not target_answer:
            raise HTTPException(status_code=400, detail="target answer not found")

        cursor.execute(
            """
            UPDATE llm_sessions
            SET status = 'active', answer_id = ?
            WHERE id = ?
            """,
            (target_answer_id, session_id),
        )
        cursor.execute(
            """
            INSERT INTO llm_messages (
              session_id, role, content, target_answer_id, created_at
            )
            VALUES (?, 'user', ?, ?, ?)
            """,
            (
                session_id,
                payload.content.strip() or "请综合当前评分，评价这条答案并给出更合适的修正版。",
                target_answer_id,
                created_at,
            ),
        )

    job_id = queue_job(
        "llm",
        {
            "task_id": task_id,
            "session_id": session_id,
            "action": session["purpose"],
            "prompt": payload.content.strip() or None,
            "target_answer_id": target_answer_id,
            "score_context": payload.score_context.model_dump()
            if payload.score_context
            else None,
        },
    )
    return {"code": 0, "message": "ok", "data": {"session_id": session_id, "job_id": job_id}}


@router.post("/{task_id}/llm/sessions/{session_id}/stream")
def stream_message(
    task_id: int,
    session_id: int,
    payload: MessagePayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    created_at = now_iso()

    with db_cursor() as cursor:
        session = cursor.execute(
            """
            SELECT id, purpose, llm_config_id
            FROM llm_sessions
            WHERE id = ? AND task_id = ?
            """,
            (session_id, task_id),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="session not found")

        target_answer_id = payload.target_answer_id or task["answer_id"]
        target_answer = cursor.execute(
            """
            SELECT id, answer_text, version_no
            FROM qa_answers
            WHERE id = ? AND qa_item_id = ?
            """,
            (target_answer_id, task["qa_item_id"]),
        ).fetchone()
        if not target_answer:
            raise HTTPException(status_code=400, detail="target answer not found")

        task_detail = cursor.execute(
            """
            SELECT
              t.id,
              t.qa_item_id,
              t.answer_id,
              q.question_text,
              q.context_text,
              tt.code AS technical_type_code
            FROM evaluation_tasks t
            JOIN qa_items q ON q.id = t.qa_item_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
            WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
        if not task_detail:
            raise HTTPException(status_code=404, detail="task not found")

        cursor.execute(
            """
            UPDATE llm_sessions
            SET status = 'active', answer_id = ?
            WHERE id = ?
            """,
            (target_answer_id, session_id),
        )
        cursor.execute(
            """
            INSERT INTO llm_messages (
              session_id, role, content, target_answer_id, created_at
            )
            VALUES (?, 'user', ?, ?, ?)
            """,
            (
                session_id,
                payload.content.strip() or "请综合当前评分，评价这条答案并给出更合适的修正版。",
                target_answer_id,
                created_at,
            ),
        )
        conversation_history = cursor.execute(
            """
            SELECT role, content
            FROM llm_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    llm_config = get_llm_config(session["llm_config_id"])

    request_messages = build_task_messages(
        action=session["purpose"],
        question_text=task_detail["question_text"],
        context_text=task_detail["context_text"],
        answer_text=target_answer["answer_text"],
        technical_type_code=task_detail["technical_type_code"],
        score_context=payload.score_context.model_dump() if payload.score_context else None,
        conversation_history=[dict(row) for row in conversation_history],
        system_prompt=llm_config["system_prompt"],
    )

    def generate() -> Iterator[str]:
        assistant_text = ""
        try:
            yield sse_event(
                "started",
                {"session_id": session_id, "target_answer_id": int(target_answer["id"])},
            )
            for chunk in iter_openai_compatible_chat(
                base_url=llm_config["base_url"],
                api_key=llm_config["resolved_api_key"],
                model_name=llm_config["model_name"],
                messages=request_messages,
                temperature=float(llm_config["temperature"]),
                max_tokens=llm_config["max_tokens"] or 800,
                top_p=llm_config["top_p"] or 0.95,
            ):
                assistant_text += chunk
                yield sse_event("delta", {"content": chunk})

            review = parse_review_response(assistant_text)
            candidate_answer_id: Optional[int] = None
            revised_answer = review["revised_answer"]
            with db_cursor() as cursor:
                if normalize_answer_text(revised_answer):
                    cursor.execute(
                        """
                        INSERT INTO qa_answers (
                          qa_item_id, answer_text, answer_type, source_model,
                          source_user_id, parent_answer_id, version_no, is_current, created_at
                        ) VALUES (?, ?, 'llm_generated_candidate', ?, NULL, ?, ?, 0, ?)
                        """,
                        (
                            task["qa_item_id"],
                            revised_answer,
                            f"{llm_config['name']} / {llm_config['model_name']} / session#{session_id}",
                            target_answer["id"],
                            int(target_answer["version_no"] or 1) + 1,
                            now_iso(),
                        ),
                    )
                    candidate_answer_id = int(cursor.lastrowid)

                cursor.execute(
                    """
                    INSERT INTO llm_messages (
                      session_id, role, content, target_answer_id, generated_answer_id, review_json, created_at
                    )
                    VALUES (?, 'assistant', ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        format_review_message(review, candidate_answer_id),
                        target_answer["id"],
                        candidate_answer_id,
                        json.dumps(review, ensure_ascii=False),
                        now_iso(),
                    ),
                )
                cursor.execute(
                    "UPDATE llm_sessions SET status = 'completed' WHERE id = ?",
                    (session_id,),
                )

            yield sse_event(
                "done",
                {
                    "session_id": session_id,
                    "candidate_answer_id": candidate_answer_id,
                },
            )
        except Exception as exc:
            with db_cursor() as cursor:
                cursor.execute(
                    "UPDATE llm_sessions SET status = 'failed' WHERE id = ?",
                    (session_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO llm_messages (
                      session_id, role, content, target_answer_id, created_at
                    ) VALUES (?, 'assistant', ?, ?, ?)
                    """,
                    (
                        session_id,
                        f"LLM 调用失败：{str(exc)}",
                        target_answer_id,
                        now_iso(),
                    ),
                )
            yield sse_event("error", {"detail": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
            SELECT
              id,
              role,
              content,
              target_answer_id,
              generated_answer_id,
              review_json,
              created_at
            FROM llm_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}


@router.post("/{task_id}/llm/auto-review")
def auto_review(
    task_id: int,
    payload: AutoReviewPayload,
    current_user: CurrentUser = Depends(require_expert),
):
    task = get_task(task_id, current_user["id"])
    llm_config = get_llm_config(payload.llm_config_id)
    created_at = now_iso()

    with db_cursor() as cursor:
        task_detail = cursor.execute(
            """
            SELECT
              t.id,
              t.qa_item_id,
              t.answer_id,
              q.question_text,
              q.context_text,
              tt.code AS technical_type_code,
              u.bio AS expert_bio
            FROM evaluation_tasks t
            JOIN qa_items q ON q.id = t.qa_item_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
            JOIN users u ON u.id = t.expert_user_id
            WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
        if not task_detail:
            raise HTTPException(status_code=404, detail="task not found")
        answer = cursor.execute(
            """
            SELECT id, answer_text, version_no
            FROM qa_answers
            WHERE id = ? AND qa_item_id = ?
            """,
            (payload.target_answer_id or task_detail["answer_id"], task_detail["qa_item_id"]),
        ).fetchone()
        if not answer:
            raise HTTPException(status_code=404, detail="answer not found")
        cursor.execute(
            """
            INSERT INTO llm_sessions (
              task_id, qa_item_id, answer_id, expert_user_id,
              llm_config_id, llm_config_name, llm_model_name,
              purpose, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'rewrite', 'active', ?)
            """,
            (
                task["id"],
                task["qa_item_id"],
                task["answer_id"],
                task["expert_user_id"],
                llm_config["id"],
                llm_config["name"],
                llm_config["model_name"],
                created_at,
            ),
        )
        session_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO llm_messages (
              session_id, role, content, target_answer_id, created_at
            ) VALUES (?, 'user', ?, ?, ?)
            """,
            (
                session_id,
                "请根据问题、答案和我的个人说明，直接完成自动化评测并给出建议答案。",
                answer["id"],
                created_at,
            ),
        )

    messages = build_auto_review_messages(
        question_text=task_detail["question_text"],
        context_text=task_detail["context_text"],
        answer_text=answer["answer_text"],
        technical_type_code=task_detail["technical_type_code"],
        expert_profile_prompt=task_detail["expert_bio"],
        system_prompt=llm_config["system_prompt"],
    )

    try:
        assistant_text = call_openai_compatible_chat(
            base_url=llm_config["base_url"],
            api_key=llm_config["resolved_api_key"],
            model_name=llm_config["model_name"],
            messages=messages,
            temperature=float(llm_config["temperature"]),
            max_tokens=llm_config["max_tokens"] or 800,
            top_p=llm_config["top_p"] or 0.95,
        )
        review = parse_auto_review_response(assistant_text)
        if task_detail["technical_type_code"] == "cot_qa":
            review["reasoning_completeness"] = review["reasoning_completeness"] or "medium"
            review["reasoning_consistency"] = review["reasoning_consistency"] or "medium"
            review["reasoning_support"] = review["reasoning_support"] or "medium"
    except LlmClientError as exc:
        with db_cursor() as cursor:
            cursor.execute(
                "UPDATE llm_sessions SET status = 'failed' WHERE id = ?",
                (session_id,),
            )
            cursor.execute(
                """
                INSERT INTO llm_messages (
                  session_id, role, content, target_answer_id, created_at
                ) VALUES (?, 'assistant', ?, ?, ?)
                """,
                (
                    session_id,
                    f"自动化评测失败：{str(exc)}",
                    answer["id"],
                    now_iso(),
                ),
            )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    candidate_answer_id: Optional[int] = None
    revised_answer = review["revised_answer"]
    with db_cursor() as cursor:
        if revised_answer and revised_answer.strip() and revised_answer.strip() != answer["answer_text"].strip():
            cursor.execute(
                """
                INSERT INTO qa_answers (
                  qa_item_id, answer_text, answer_type, source_model,
                  source_user_id, parent_answer_id, version_no, is_current, created_at
                ) VALUES (?, ?, 'llm_generated_candidate', ?, NULL, ?, ?, 0, ?)
                """,
                (
                    task_detail["qa_item_id"],
                    revised_answer,
                    f"{llm_config['name']} / {llm_config['model_name']} / auto-review",
                    answer["id"],
                    int(answer["version_no"] or 1) + 1,
                    now_iso(),
                ),
            )
            candidate_answer_id = int(cursor.lastrowid)

        cursor.execute(
            """
            INSERT INTO llm_messages (
              session_id, role, content, target_answer_id, generated_answer_id, review_json, created_at
            ) VALUES (?, 'assistant', ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                format_auto_review_message(review, candidate_answer_id),
                answer["id"],
                candidate_answer_id,
                json.dumps(review, ensure_ascii=False),
                now_iso(),
            ),
        )
        cursor.execute(
            "UPDATE llm_sessions SET status = 'completed' WHERE id = ?",
            (session_id,),
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "session_id": session_id,
            "candidate_answer_id": candidate_answer_id,
            "score_context": {
                "correctness_rating": review["correctness_rating"],
                "completeness_rating": review["completeness_rating"],
                "relevance_rating": review["relevance_rating"],
                "clarity_rating": review["clarity_rating"],
                "risk_flag": review["risk_flag"],
                "reasoning_completeness": review["reasoning_completeness"] or None,
                "reasoning_consistency": review["reasoning_consistency"] or None,
                "reasoning_support": review["reasoning_support"] or None,
                "overall_decision": review["overall_decision"],
                "quick_comment_codes": review["quick_comment_codes"],
            },
        },
    }


@router.post("/{task_id}/llm/rewrite")
def quick_rewrite(
    task_id: int,
    payload: RewritePayload,
    current_user: CurrentUser = Depends(require_expert),
):
    llm_config = get_llm_config(payload.llm_config_id)
    task = get_task(task_id, current_user["id"])
    created_at = now_iso()
    with db_cursor() as cursor:
        target_answer_id = payload.target_answer_id or task["answer_id"]
        target_answer = cursor.execute(
            """
            SELECT id
            FROM qa_answers
            WHERE id = ? AND qa_item_id = ?
            """,
            (target_answer_id, task["qa_item_id"]),
        ).fetchone()
        if not target_answer:
            raise HTTPException(status_code=400, detail="target answer not found")
        cursor.execute(
            """
            INSERT INTO llm_sessions (
              task_id, qa_item_id, answer_id, expert_user_id,
              llm_config_id, llm_config_name, llm_model_name,
              purpose, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'rewrite', 'active', ?)
            """,
            (
                task["id"],
                task["qa_item_id"],
                target_answer_id,
                task["expert_user_id"],
                llm_config["id"],
                llm_config["name"],
                llm_config["model_name"],
                created_at,
            ),
        )
        session_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO llm_messages (
              session_id, role, content, target_answer_id, created_at
            )
            VALUES (?, 'user', ?, ?, ?)
            """,
            (
                session_id,
                payload.prompt.strip()
                if payload.prompt and payload.prompt.strip()
                else "请综合当前评分，评价这条答案并给出更合适的修正版。",
                target_answer_id,
                created_at,
            ),
        )

    job_id = queue_job(
        "llm",
        {
            "task_id": task_id,
            "session_id": session_id,
            "action": "rewrite",
            "mode": payload.mode,
            "prompt": payload.prompt.strip() if payload.prompt else None,
            "target_answer_id": target_answer_id,
            "score_context": payload.score_context.model_dump()
            if payload.score_context
            else None,
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
