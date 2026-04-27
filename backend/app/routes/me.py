from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user
from ..db import db_cursor
from .auth import hash_password

router = APIRouter(tags=["me"])


class MeUpdatePayload(BaseModel):
    organization: Optional[str] = None
    title: Optional[str] = None
    bio: Optional[str] = None


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


@router.get("/api/me")
def get_me(current_user: CurrentUser = Depends(get_current_user)):
    user_id = current_user["id"]
    with db_cursor() as cursor:
        user = cursor.execute(
            """
            SELECT id, username, role, status, full_name, organization, title, bio, created_at
                 , allow_cross_business_review
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
        business_tags = cursor.execute(
            """
            SELECT b.id, b.name
            FROM expert_business_tags ebt
            JOIN business_tags b ON b.id = ebt.business_tag_id
            WHERE ebt.expert_user_id = ?
            ORDER BY ebt.priority, b.name
            """,
            (user_id,),
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            **dict(user),
            "applications": [dict(row) for row in applications],
            "business_tags": [dict(row) for row in business_tags],
            "allow_cross_business_review": bool(user["allow_cross_business_review"]),
        },
    }


@router.patch("/api/me")
def update_me(
    payload: MeUpdatePayload,
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = current_user["id"]
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
    return {"code": 0, "message": "ok", "data": {"user_id": user_id}}


@router.post("/api/me/change-password")
def change_password(
    payload: ChangePasswordPayload,
    current_user: CurrentUser = Depends(get_current_user),
):
    user_id = current_user["id"]
    with db_cursor() as cursor:
        user = cursor.execute(
            "SELECT id, password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user not found")
        if user["password_hash"] != hash_password(payload.current_password):
            raise HTTPException(status_code=400, detail="current password is incorrect")
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(payload.new_password), user_id),
        )
    return {"code": 0, "message": "ok", "data": None}
