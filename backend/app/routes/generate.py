from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import CurrentUser, get_current_user
from ..db import db_cursor
from ..llm_client import call_openai_compatible_chat, iter_openai_compatible_chat, LlmClientError
from ..llm_config_store import get_llm_api_key, mask_api_key

router = APIRouter(prefix="/api/generate", tags=["generate"])


def resolve_config(model_id: Optional[int] = None, model_name: Optional[str] = None) -> dict:
    with db_cursor() as cursor:
        if model_id:
            row = cursor.execute(
                """
                SELECT id, name, provider_code, base_url, model_name,
                       temperature, api_key
                FROM llm_configs
                WHERE id = ? AND is_enabled = 1
                  AND llm_use_case = 'evaluation'
                """,
                (model_id,),
            ).fetchone()
        elif model_name:
            row = cursor.execute(
                """
                SELECT id, name, provider_code, base_url, model_name,
                       temperature, api_key
                FROM llm_configs
                WHERE model_name = ? AND is_enabled = 1
                  AND llm_use_case = 'evaluation'
                ORDER BY is_active DESC, id DESC
                LIMIT 1
                """,
                (model_name,),
            ).fetchone()
        else:
            row = cursor.execute(
                """
                SELECT id, name, provider_code, base_url, model_name,
                       temperature, api_key
                FROM llm_configs
                WHERE is_enabled = 1
                  AND llm_use_case = 'evaluation'
                ORDER BY is_active DESC, id DESC
                LIMIT 1
                """,
            ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="no enabled evaluation model found")
    api_key = get_llm_api_key(row["id"], row["api_key"])
    if not api_key:
        raise HTTPException(status_code=400, detail="model api key not configured on server")
    return {**dict(row), "resolved_api_key": api_key}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionPayload(BaseModel):
    model: Optional[str] = None
    model_id: Optional[int] = None
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False


@router.get("/models")
def list_generate_models(current_user: CurrentUser = Depends(get_current_user)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, name, provider_code, base_url, model_name, temperature
            FROM llm_configs
            WHERE is_enabled = 1 AND llm_use_case = 'evaluation'
            ORDER BY is_active DESC, id DESC
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [
            {
                "id": row["id"],
                "name": row["name"],
                "provider": row["provider_code"],
                "baseUrl": row["base_url"],
                "model": row["model_name"],
                "temperature": row["temperature"],
                "maxTokens": 800,
                "batchSize": 24,
                "maxInFlight": 64,
            }
            for row in rows
        ],
    }


@router.post("/chat/completions")
def chat_completions(
    payload: ChatCompletionPayload,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    config = resolve_config(
        model_id=payload.model_id,
        model_name=payload.model if payload.model else None,
    )
    messages = [{"role": msg.role, "content": msg.content} for msg in payload.messages]
    temperature = payload.temperature if payload.temperature is not None else config["temperature"]

    if payload.stream:
        def generate():
            try:
                for chunk in iter_openai_compatible_chat(
                    base_url=config["base_url"],
                    api_key=config["resolved_api_key"],
                    model_name=config["model_name"],
                    messages=messages,
                    temperature=temperature,
                ):
                    yield chunk
            except LlmClientError as exc:
                yield f'data: {{"error": "{exc}"}}\n\n'

        return StreamingResponse(generate(), media_type="text/event-stream")

    try:
        content = call_openai_compatible_chat(
            base_url=config["base_url"],
            api_key=config["resolved_api_key"],
            model_name=config["model_name"],
            messages=messages,
            temperature=temperature,
        )
    except LlmClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "id": f"chatcmpl-{config['id']}",
        "object": "chat.completion",
        "model": config["model_name"],
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
