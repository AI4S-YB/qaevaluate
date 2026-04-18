from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Depends, Header, HTTPException

from .db import db_cursor


CurrentUser = Dict[str, Any]


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _extract_token(authorization: Optional[str], x_auth_token: Optional[str]) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip()
    if x_auth_token:
        return x_auth_token.strip()
    raise HTTPException(status_code=401, detail="missing auth token")


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_auth_token: Optional[str] = Header(default=None),
) -> CurrentUser:
    token = _extract_token(authorization, x_auth_token)
    with db_cursor() as cursor:
        user = cursor.execute(
            """
            SELECT u.id, u.username, u.role, u.status, s.token, s.expires_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="invalid auth token")
    expires_at = parse_iso_datetime(user["expires_at"])
    if expires_at and expires_at <= datetime.utcnow():
        with db_cursor() as cursor:
            cursor.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
        raise HTTPException(status_code=401, detail="auth token expired")
    if user["status"] != "approved":
        raise HTTPException(status_code=403, detail=f"account {user['status']}")
    return dict(user)


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return current_user


def require_expert(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user["role"] not in {"expert", "admin"}:
        raise HTTPException(status_code=403, detail="expert only")
    return current_user
