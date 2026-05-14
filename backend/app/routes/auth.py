from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user
from ..db import db_cursor

router = APIRouter(prefix="/api/auth", tags=["auth"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class RegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=6)
    full_name: str
    organization: Optional[str] = None
    title: Optional[str] = None
    bio: Optional[str] = None
    application_ids: List[int] = Field(default_factory=list)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(payload: RegisterRequest):
    created_at = now_iso()
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="username already exists")

        cursor.execute(
            """
            INSERT INTO users (
              username, password_hash, role, status, full_name,
              organization, title, bio, created_at
            ) VALUES (?, ?, 'expert', 'pending', ?, ?, ?, ?, ?)
            """,
            (
                payload.username,
                hash_password(payload.password),
                payload.full_name,
                payload.organization,
                payload.title,
                payload.bio,
                created_at,
            ),
        )
        user_id = cursor.lastrowid
        for application_id in payload.application_ids:
            cursor.execute(
                """
                INSERT INTO expert_applications (
                  expert_user_id, application_id, priority, created_at
                ) VALUES (?, ?, 1, ?)
                """,
                (user_id, application_id, created_at),
            )

    return {
        "code": 0,
        "message": "pending approval",
        "data": {"user_id": user_id, "status": "pending"},
    }


@router.post("/login")
def login(payload: LoginRequest):
    created_at = now_iso()
    expires_at = (datetime.utcnow() + timedelta(days=7)).replace(microsecond=0).isoformat()
    with db_cursor() as cursor:
        user = cursor.execute(
            """
            SELECT id, username, role, status, password_hash
            FROM users
            WHERE username = ?
            """,
            (payload.username,),
        ).fetchone()

    if not user or user["password_hash"] != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if user["status"] != "approved":
        raise HTTPException(status_code=403, detail=f"account {user['status']}")
    token = secrets.token_urlsafe(32)
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth_sessions (user_id, token, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (user["id"], token, created_at, expires_at),
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "token": token,
            "expires_at": expires_at,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "status": user["status"],
            },
        },
    }


@router.post("/logout")
def logout(current_user: CurrentUser = Depends(get_current_user)):
    with db_cursor() as cursor:
        cursor.execute(
            "DELETE FROM auth_sessions WHERE token = ?",
            (current_user["token"],),
        )
    return {"code": 0, "message": "ok", "data": None}
