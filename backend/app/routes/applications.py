from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import CurrentUser, require_admin
from ..db import db_cursor

router = APIRouter(tags=["applications"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class ApplicationPayload(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


@router.get("/api/applications")
def list_applications():
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, name, description, is_active, created_at
            FROM applications
            WHERE is_active = 1
            ORDER BY id DESC
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [dict(row) for row in rows],
    }


@router.get("/api/admin/applications")
def list_admin_applications(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              a.id,
              a.name,
              a.description,
              a.is_active,
              a.created_at,
              COUNT(DISTINCT q.id) AS total_qas,
              SUM(CASE WHEN q.status = 'reviewed' THEN 1 ELSE 0 END) AS reviewed_qas,
              SUM(
                CASE
                  WHEN q.id IS NOT NULL
                   AND (agg.final_decision IS NULL OR agg.final_decision = 'pending')
                  THEN 1 ELSE 0
                END
              ) AS pending_aggregate_qas,
              SUM(
                CASE
                  WHEN agg.final_standard_answer_id IS NOT NULL
                   AND agg.current_answer_id = agg.final_standard_answer_id
                   AND agg.final_decision IN ('pass', 'rewrite', 'fail')
                  THEN 1 ELSE 0
                END
              ) AS closed_qas,
              COUNT(
                DISTINCT CASE
                  WHEN u.role = 'expert' AND u.status = 'approved' THEN u.id
                  ELSE NULL
                END
              ) AS expert_count
            FROM applications a
            LEFT JOIN qa_items q ON q.application_id = a.id
            LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
            LEFT JOIN expert_applications ea ON ea.application_id = a.id
            LEFT JOIN users u ON u.id = ea.expert_user_id
            GROUP BY a.id, a.name, a.description, a.is_active, a.created_at
            ORDER BY a.id DESC
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [dict(row) for row in rows],
    }


@router.post("/api/admin/applications")
def create_application(
    payload: ApplicationPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO applications (name, description, is_active, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (payload.name, payload.description, int(payload.is_active), created_at),
        )
        application_id = cursor.lastrowid
    return {"code": 0, "message": "ok", "data": {"id": application_id}}


@router.patch("/api/admin/applications/{application_id}")
def update_application(
    application_id: int,
    payload: ApplicationPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE applications
            SET name = ?, description = ?, is_active = ?
            WHERE id = ?
            """,
            (payload.name, payload.description, int(payload.is_active), application_id),
        )
    return {"code": 0, "message": "ok", "data": {"id": application_id}}
