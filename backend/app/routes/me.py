from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user
from ..db import db_cursor

router = APIRouter(tags=["me"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class MeUpdatePayload(BaseModel):
    organization: Optional[str] = None
    title: Optional[str] = None
    bio: Optional[str] = None
    application_ids: List[int] = Field(default_factory=list)


@router.get("/api/me")
def get_me(current_user: CurrentUser = Depends(get_current_user)):
    user_id = current_user["id"]
    with db_cursor() as cursor:
        user = cursor.execute(
            """
            SELECT id, username, role, status, full_name, organization, title, bio, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user not found")

        applications = cursor.execute(
            """
            SELECT a.id, a.name
            FROM expert_applications ea
            JOIN applications a ON a.id = ea.application_id
            WHERE ea.expert_user_id = ?
            ORDER BY ea.priority, a.name
            """,
            (user_id,),
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            **dict(user),
            "applications": [dict(row) for row in applications],
        },
    }


@router.patch("/api/me")
def update_me(
    payload: MeUpdatePayload,
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = current_user["id"]
    updated_at = now_iso()
    with db_cursor() as cursor:
        user = cursor.execute(
            "SELECT id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user not found")

        cursor.execute(
            """
            UPDATE users
            SET organization = ?, title = ?, bio = ?
            WHERE id = ?
            """,
            (payload.organization, payload.title, payload.bio, user_id),
        )
        cursor.execute(
            "DELETE FROM expert_applications WHERE expert_user_id = ?",
            (user_id,),
        )
        for priority, application_id in enumerate(payload.application_ids, start=1):
            cursor.execute(
                """
                INSERT INTO expert_applications (
                  expert_user_id, application_id, priority, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (user_id, application_id, priority, updated_at),
            )

    return {"code": 0, "message": "ok", "data": {"user_id": user_id}}
