from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import time
from typing import Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user, require_admin
from ..config import APP_ENV, DB_PATH, EXPORT_DIR, QUEUE_DIR, RUNTIME_DATA_DIR, UPLOAD_DIR
from ..db import db_cursor
from ..jobs import queue_job, queue_unique_import_job
from ..llm_client import LlmClientError, call_openai_compatible_chat
from ..llm_config_store import get_llm_api_key, mask_api_key, set_llm_api_key
from ..worker import get_next_job, process_job
from .auth import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])
news_router = APIRouter(tags=["news"])


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def record_changelog(model_name: str, change_type: str, description: str) -> None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO model_changelogs (model_name, change_type, description, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (model_name, change_type, description, now_iso()),
        )


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


class ExpertDecisionPayload(BaseModel):
    note: Optional[str] = None


class ExpertSettingsPayload(BaseModel):
    business_tag_ids: list[int] = Field(default_factory=list)
    allow_cross_business_review: bool = False


class DispatchPayload(BaseModel):
    application_id: int
    limit: int = 100


class FinalAnswerPayload(BaseModel):
    answer_id: int


class ExportCreatePayload(BaseModel):
    export_type: str = Field(alias="type")
    application_id: Optional[int] = None
    technical_type_codes: list[str] = Field(default_factory=list)
    date_from: Optional[str] = Field(default=None, alias="from")
    date_to: Optional[str] = Field(default=None, alias="to")
    file_format: str = Field(default="json", alias="format")


class TaxonomyCreatePayload(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    sort_order: int = 100


class TaxonomyUpdatePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class LlmConfigPayload(BaseModel):
    name: str
    provider_code: str = "custom_openai"
    provider_type: str = "openai_compatible"
    base_url: str
    api_key: str
    model_name: str
    system_prompt: Optional[str] = None
    temperature: float = 0.2
    is_enabled: bool = True
    is_active: bool = False
    is_trial_enabled: bool = False


class LlmConfigEnablePayload(BaseModel):
    is_enabled: bool


class LlmConfigTrialEnablePayload(BaseModel):
    is_trial_enabled: bool


LLM_USE_CASE_EVALUATION = "evaluation"
LLM_USE_CASE_TRIAL = "trial"


class ImportCandidateAnswerPayload(BaseModel):
    answer: str


class ImportRowPayload(BaseModel):
    id: Optional[str] = None
    question: str
    answer: Optional[str] = None
    context: Optional[str] = None
    difficulty: Optional[str] = None
    source: Optional[str] = None
    model: Optional[str] = None
    candidate_answers: list[ImportCandidateAnswerPayload] = Field(default_factory=list)


class ImportPushPayload(BaseModel):
    name: str = "default-batch"
    source: str = "remote-sync"
    application_id: int
    technical_type_code: str
    business_tag_codes: list[str] = Field(default_factory=list)
    rows: list[ImportRowPayload] = Field(default_factory=list)
    auto_parse: bool = True


def queue_file(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    error_path = path.with_suffix(".error.txt")
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    error_message = (
        meta.get("last_error")
        or (error_path.read_text(encoding="utf-8").strip() if error_path.exists() else None)
    )
    return {
        "job_id": payload.get("job_id", path.stem),
        "type": payload.get("type", "unknown"),
        "status": path.parent.name,
        "filename": path.name,
        "updated_at": datetime.utcfromtimestamp(path.stat().st_mtime)
        .replace(microsecond=0)
        .isoformat(),
        "payload": payload.get("payload", {}),
        "created_at": meta.get("created_at"),
        "started_at": meta.get("started_at"),
        "completed_at": meta.get("completed_at"),
        "duration_ms": meta.get("duration_ms"),
        "retry_count": meta.get("retry_count", 0),
        "error": error_message,
    }


def iter_queue_jobs(statuses: tuple[str, ...] = ("pending", "processing", "done", "failed")) -> list[dict]:
    jobs: list[dict] = []
    for status in statuses:
        directory = QUEUE_DIR / status
        directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            jobs.append(queue_file(path))
    return jobs


def serialize_runtime_file(path: Path) -> dict:
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "updated_at": datetime.utcfromtimestamp(path.stat().st_mtime)
        .replace(microsecond=0)
        .isoformat(),
    }


def serialize_export_job(row) -> dict:
    item = dict(row)
    file_path = item.get("file_path")
    item["file_name"] = Path(file_path).name if file_path else None
    try:
        technical_type_codes = json.loads(item.get("technical_type_codes_json") or "[]")
    except json.JSONDecodeError:
        technical_type_codes = []
    item["technical_type_codes"] = (
        technical_type_codes
        if isinstance(technical_type_codes, list)
        and all(isinstance(code, str) for code in technical_type_codes)
        else []
    )
    return item


def serialize_taxonomy(row) -> dict:
    item = dict(row)
    item["is_active"] = bool(item["is_active"])
    return item


def serialize_llm_config(row) -> dict:
    item = dict(row)
    fallback_api_key = item.pop("api_key", None)
    api_key = get_llm_api_key(item["id"], fallback_api_key)
    item["is_enabled"] = bool(item["is_enabled"])
    item["is_active"] = bool(item["is_active"])
    item["llm_use_case"] = item.get("llm_use_case") or (
        LLM_USE_CASE_TRIAL if bool(item.get("is_trial_enabled")) else LLM_USE_CASE_EVALUATION
    )
    item["is_trial_enabled"] = item["llm_use_case"] == LLM_USE_CASE_TRIAL
    item["api_key_masked"] = mask_api_key(api_key)
    item["has_api_key"] = bool(api_key)
    return item


def get_llm_query_params(use_case: str) -> tuple[str, tuple[object, ...]]:
    if use_case == LLM_USE_CASE_TRIAL:
        return "WHERE llm_use_case = ?", (LLM_USE_CASE_TRIAL,)
    return "WHERE llm_use_case = ?", (LLM_USE_CASE_EVALUATION,)


def normalize_llm_payload(payload: LlmConfigPayload, use_case: str) -> dict:
    provider_code = payload.provider_code.strip() or "custom_openai"
    provider_type = payload.provider_type
    is_enabled = bool(payload.is_enabled)
    is_active = bool(payload.is_active)
    if use_case == LLM_USE_CASE_TRIAL:
        provider_code = "custom_openai"
        provider_type = "openai_compatible"
        is_active = False
        is_enabled = True if payload.is_enabled else False
    else:
        is_enabled = payload.is_enabled or is_active
    return {
        "name": payload.name.strip(),
        "provider_code": provider_code,
        "provider_type": provider_type,
        "base_url": payload.base_url.strip(),
        "api_key": payload.api_key.strip(),
        "model_name": payload.model_name.strip(),
        "system_prompt": payload.system_prompt,
        "temperature": payload.temperature,
        "is_enabled": is_enabled,
        "is_active": is_active,
        "llm_use_case": use_case,
    }


def parse_import_business_tags(value: str) -> list[str]:
    try:
        business_tags = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="business_tags_json must be valid json") from exc
    if not isinstance(business_tags, list) or not all(isinstance(item, str) for item in business_tags):
        raise HTTPException(status_code=400, detail="business_tags_json must be an array of strings")
    return business_tags


def validate_import_target(
    application_id: int,
    technical_type_code: str,
    business_tags: list[str],
) -> tuple[int, int]:
    with db_cursor() as cursor:
        application = cursor.execute(
            """
            SELECT id
            FROM applications
            WHERE id = ? AND is_active = 1
            """,
            (application_id,),
        ).fetchone()
        if not application:
            raise HTTPException(status_code=400, detail=f"application not found: {application_id}")
        technical_type = cursor.execute(
            """
            SELECT id
            FROM technical_types
            WHERE code = ? AND is_active = 1
            """,
            (technical_type_code,),
        ).fetchone()
        if not technical_type:
            raise HTTPException(status_code=400, detail=f"technical_type not found: {technical_type_code}")
        if business_tags:
            tag_rows = cursor.execute(
                f"""
                SELECT code
                FROM business_tags
                WHERE code IN ({",".join("?" for _ in business_tags)}) AND is_active = 1
                """,
                tuple(business_tags),
            ).fetchall()
            found_codes = {row["code"] for row in tag_rows}
            missing_codes = [code for code in business_tags if code not in found_codes]
            if missing_codes:
                raise HTTPException(status_code=400, detail=f"business_tag not found: {missing_codes[0]}")
        return int(application["id"]), int(technical_type["id"])


def create_dataset_batch(
    *,
    name: str,
    source: str,
    file_path: Path,
    application_id: int,
    technical_type_id: int,
    business_tags: list[str],
    created_by: int,
    source_batch_name: Optional[str] = None,
    external_batch_id: Optional[str] = None,
    uploader_user_id: Optional[int] = None,
    self_review_status: str = "none",
    peer_review_status: str = "none",
) -> int:
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dataset_batches (
              name, source, source_batch_name, external_batch_id, file_path,
              application_id, technical_type_id, business_tags_json, uploader_user_id,
              self_review_status, peer_review_status, import_status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'uploaded', ?, ?)
            """,
            (
                name,
                source,
                source_batch_name,
                external_batch_id,
                str(file_path),
                application_id,
                technical_type_id,
                json.dumps(business_tags, ensure_ascii=False),
                uploader_user_id,
                self_review_status,
                peer_review_status,
                created_by,
                now_iso(),
            ),
        )
        return int(cursor.lastrowid)


def create_taxonomy_entry(table_name: str, payload: TaxonomyCreatePayload) -> int:
    with db_cursor() as cursor:
        existing = cursor.execute(
            f"SELECT id FROM {table_name} WHERE code = ? OR name = ?",
            (payload.code, payload.name),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail=f"{table_name} already exists")
        cursor.execute(
            f"""
            INSERT INTO {table_name} (
              code, name, description, is_active, sort_order, created_at
            ) VALUES (?, ?, ?, 1, ?, ?)
            """,
            (payload.code, payload.name, payload.description, payload.sort_order, now_iso()),
        )
        return int(cursor.lastrowid)


@router.get("/dashboard")
def get_dashboard(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        pending_experts = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM users
            WHERE role = 'expert' AND status = 'pending'
            """
        ).fetchone()["count"]
        pending_qas = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM qa_items
            WHERE status = 'active'
            """
        ).fetchone()["count"]
        ongoing_tasks = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM evaluation_tasks
            WHERE status IN ('pending', 'in_progress')
            """
        ).fetchone()["count"]
        disputed_qas = cursor.execute(
            """
            SELECT COUNT(DISTINCT qa_item_id) AS count
            FROM evaluation_tasks
            WHERE task_type = 'dispute_review'
            """
        ).fetchone()["count"]
        total_qas = cursor.execute("SELECT COUNT(*) AS count FROM qa_items").fetchone()["count"]
        reviewed_qas = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM qa_items
            WHERE status = 'reviewed'
            """
        ).fetchone()["count"]
        imported_batches = cursor.execute(
            "SELECT COUNT(*) AS count FROM dataset_batches"
        ).fetchone()["count"]
        application_progress = cursor.execute(
            """
            SELECT
              a.id,
              a.name,
              COUNT(q.id) AS total_qas,
              SUM(CASE WHEN q.status = 'reviewed' THEN 1 ELSE 0 END) AS reviewed_qas
            FROM applications a
            LEFT JOIN qa_items q ON q.application_id = a.id
            GROUP BY a.id, a.name
            ORDER BY a.name ASC
            """
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "metrics": {
                "pending_experts": pending_experts,
                "pending_qas": pending_qas,
                "ongoing_tasks": ongoing_tasks,
                "disputed_qas": disputed_qas,
                "reviewed_qas": reviewed_qas,
                "total_qas": total_qas,
                "imported_batches": imported_batches,
            },
            "application_progress": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "total_qas": row["total_qas"] or 0,
                    "reviewed_qas": row["reviewed_qas"] or 0,
                }
                for row in application_progress
            ],
        },
    }


@router.get("/system-status")
def get_system_status(current_user: CurrentUser = Depends(require_admin)):
    queue_jobs = iter_queue_jobs()
    queue_summary = {
        "pending": sum(1 for job in queue_jobs if job["status"] == "pending"),
        "processing": sum(1 for job in queue_jobs if job["status"] == "processing"),
        "done": sum(1 for job in queue_jobs if job["status"] == "done"),
        "failed": sum(1 for job in queue_jobs if job["status"] == "failed"),
    }
    recent_failed_jobs = [job for job in queue_jobs if job["status"] == "failed"][:5]
    recent_pending_jobs = [job for job in queue_jobs if job["status"] == "pending"][:5]

    backup_dir = RUNTIME_DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_files = sorted(
        backup_dir.glob("*.sqlite3"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    uploads = sorted(
        UPLOAD_DIR.glob("*"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    exports = sorted(
        EXPORT_DIR.glob("*"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    with db_cursor() as cursor:
        llm_rows = cursor.execute(
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
              is_active,
              is_trial_enabled,
              last_tested_at,
              last_test_status,
              last_test_message,
              last_test_latency_ms,
              created_at,
              updated_at
            FROM llm_configs
            ORDER BY is_active DESC, id DESC
            """
        ).fetchall()

    llm_configs = [serialize_llm_config(row) for row in llm_rows]
    active_llm_config = next((item for item in llm_configs if item["is_active"]), None)

    db_exists = DB_PATH.exists()
    db_size_bytes = DB_PATH.stat().st_size if db_exists else 0

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "environment": {
                "app_env": APP_ENV,
                "database": {
                    "path": str(DB_PATH),
                    "exists": db_exists,
                    "size_bytes": db_size_bytes,
                },
                "runtime": {
                    "path": str(RUNTIME_DATA_DIR),
                    "uploads_count": len(uploads),
                    "exports_count": len(exports),
                },
            },
            "llm": {
                "total_configs": len(llm_configs),
                "active_config": active_llm_config,
                "passed_count": sum(
                    1 for item in llm_configs if item["last_test_status"] == "passed"
                ),
                "failed_count": sum(
                    1 for item in llm_configs if item["last_test_status"] == "failed"
                ),
                "missing_api_key_count": sum(
                    1 for item in llm_configs if not item["has_api_key"]
                ),
                "configs": llm_configs[:6],
            },
            "queue": {
                "summary": queue_summary,
                "recent_failed_jobs": recent_failed_jobs,
                "recent_pending_jobs": recent_pending_jobs,
            },
            "backups": {
                "directory": str(backup_dir),
                "total_files": len(backup_files),
                "latest_file": serialize_runtime_file(backup_files[0]) if backup_files else None,
                "files": [serialize_runtime_file(path) for path in backup_files[:8]],
            },
        },
    }


@router.get("/technical-types")
def list_technical_types(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, code, name, description, is_active, sort_order, created_at
            FROM technical_types
            ORDER BY is_active DESC, sort_order ASC, id ASC
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [serialize_taxonomy(row) for row in rows],
    }


@router.post("/technical-types")
def create_technical_type(
    payload: TaxonomyCreatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    taxonomy_id = create_taxonomy_entry("technical_types", payload)
    return {"code": 0, "message": "ok", "data": {"id": taxonomy_id}}


@router.patch("/technical-types/{taxonomy_id}")
def update_technical_type(
    taxonomy_id: int,
    payload: TaxonomyUpdatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return {"code": 0, "message": "ok", "data": {"id": taxonomy_id}}
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id FROM technical_types WHERE id = ?",
            (taxonomy_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="technical type not found")
        fields = []
        values: list[object] = []
        for key, value in updates.items():
            if key == "is_active":
                fields.append("is_active = ?")
                values.append(1 if value else 0)
            else:
                fields.append(f"{key} = ?")
                values.append(value)
        values.append(taxonomy_id)
        cursor.execute(
            f"UPDATE technical_types SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )
    return {"code": 0, "message": "ok", "data": {"id": taxonomy_id}}


@router.get("/business-tags")
def list_business_tags(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              b.id,
              b.code,
              b.name,
              b.description,
              b.is_active,
              b.sort_order,
              b.created_at,
              (
                SELECT COUNT(*)
                FROM qa_items q
                JOIN json_each(q.business_tags_json) je
                  ON je.value = b.code
              ) AS qa_count
            FROM business_tags b
            ORDER BY is_active DESC, sort_order ASC, id ASC
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [serialize_taxonomy(row) for row in rows],
    }


@router.post("/business-tags")
def create_business_tag(
    payload: TaxonomyCreatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    taxonomy_id = create_taxonomy_entry("business_tags", payload)
    return {"code": 0, "message": "ok", "data": {"id": taxonomy_id}}


@router.patch("/business-tags/{taxonomy_id}")
def update_business_tag(
    taxonomy_id: int,
    payload: TaxonomyUpdatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return {"code": 0, "message": "ok", "data": {"id": taxonomy_id}}
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id FROM business_tags WHERE id = ?",
            (taxonomy_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="business tag not found")
        fields = []
        values: list[object] = []
        for key, value in updates.items():
            if key == "is_active":
                fields.append("is_active = ?")
                values.append(1 if value else 0)
            else:
                fields.append(f"{key} = ?")
                values.append(value)
        values.append(taxonomy_id)
        cursor.execute(
            f"UPDATE business_tags SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )
    return {"code": 0, "message": "ok", "data": {"id": taxonomy_id}}


@router.get("/llm-configs")
def list_llm_configs(current_user: CurrentUser = Depends(require_admin)):
    where_clause, params = get_llm_query_params(LLM_USE_CASE_EVALUATION)
    with db_cursor() as cursor:
        rows = cursor.execute(
            f"""
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
              is_active,
              is_trial_enabled,
              last_tested_at,
              last_test_status,
              last_test_message,
              last_test_latency_ms,
              created_at,
              updated_at
            FROM llm_configs
            {where_clause}
            ORDER BY is_active DESC, id DESC
            """,
            params,
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [serialize_llm_config(row) for row in rows]}


@router.get("/trial-llm-configs")
def list_trial_llm_configs(current_user: CurrentUser = Depends(require_admin)):
    where_clause, params = get_llm_query_params(LLM_USE_CASE_TRIAL)
    with db_cursor() as cursor:
        rows = cursor.execute(
            f"""
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
              is_active,
              is_trial_enabled,
              last_tested_at,
              last_test_status,
              last_test_message,
              last_test_latency_ms,
              created_at,
              updated_at
            FROM llm_configs
            {where_clause}
            ORDER BY id DESC
            """,
            params,
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [serialize_llm_config(row) for row in rows]}


@router.post("/llm-configs")
def create_llm_config(
    payload: LlmConfigPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    normalized = normalize_llm_payload(payload, LLM_USE_CASE_EVALUATION)
    created_at = now_iso()
    api_key = normalized["api_key"]
    if not api_key:
        raise HTTPException(status_code=400, detail="api key is required")
    if not normalized["name"] or not normalized["base_url"] or not normalized["model_name"]:
        raise HTTPException(status_code=400, detail="name, base_url and model_name are required")
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id FROM llm_configs WHERE name = ?",
            (normalized["name"],),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="llm config already exists")
        if normalized["is_active"]:
            cursor.execute("UPDATE llm_configs SET is_active = 0")
        cursor.execute(
            """
            INSERT INTO llm_configs (
              name, llm_use_case, provider_code, provider_type, base_url, api_key, model_name,
              system_prompt, temperature, is_enabled, is_active, is_trial_enabled,
              last_tested_at, last_test_status, last_test_message, last_test_latency_ms,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
            """,
            (
                normalized["name"],
                normalized["llm_use_case"],
                normalized["provider_code"],
                normalized["provider_type"],
                normalized["base_url"],
                "",
                normalized["model_name"],
                normalized["system_prompt"],
                normalized["temperature"],
                1 if normalized["is_enabled"] else 0,
                1 if normalized["is_active"] else 0,
                0,
                created_at,
                created_at,
            ),
        )
        config_id = int(cursor.lastrowid)
    set_llm_api_key(config_id, api_key)
    return {"code": 0, "message": "ok", "data": {"id": config_id}}


@router.patch("/llm-configs/{config_id}")
def update_llm_config(
    config_id: int,
    payload: LlmConfigPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    normalized = normalize_llm_payload(payload, LLM_USE_CASE_EVALUATION)
    updated_at = now_iso()
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id, api_key, llm_use_case FROM llm_configs WHERE id = ?",
            (config_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="llm config not found")
        if (existing["llm_use_case"] or LLM_USE_CASE_EVALUATION) != LLM_USE_CASE_EVALUATION:
            raise HTTPException(status_code=400, detail="config belongs to model trial scope")
        api_key = normalized["api_key"]
        if api_key == "__KEEP_EXISTING__" or not api_key:
            api_key = get_llm_api_key(config_id, existing["api_key"])
        if not normalized["name"] or not normalized["base_url"] or not normalized["model_name"]:
            raise HTTPException(status_code=400, detail="name, base_url and model_name are required")
        if normalized["is_active"]:
            cursor.execute("UPDATE llm_configs SET is_active = 0 WHERE id != ?", (config_id,))
        cursor.execute(
            """
            UPDATE llm_configs
            SET name = ?,
                llm_use_case = ?,
                provider_code = ?,
                provider_type = ?,
                base_url = ?,
                api_key = ?,
                model_name = ?,
                system_prompt = ?,
                temperature = ?,
                is_enabled = ?,
                is_active = ?,
                is_trial_enabled = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["name"],
                normalized["llm_use_case"],
                normalized["provider_code"],
                normalized["provider_type"],
                normalized["base_url"],
                "",
                normalized["model_name"],
                normalized["system_prompt"],
                normalized["temperature"],
                1 if normalized["is_enabled"] else 0,
                1 if normalized["is_active"] else 0,
                0,
                updated_at,
                config_id,
            ),
        )
    if api_key:
        set_llm_api_key(config_id, api_key)
    return {"code": 0, "message": "ok", "data": {"id": config_id}}


@router.post("/trial-llm-configs")
def create_trial_llm_config(
    payload: LlmConfigPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    normalized = normalize_llm_payload(payload, LLM_USE_CASE_TRIAL)
    created_at = now_iso()
    api_key = normalized["api_key"]
    if not api_key:
        raise HTTPException(status_code=400, detail="api key is required")
    if not normalized["name"] or not normalized["base_url"] or not normalized["model_name"]:
        raise HTTPException(status_code=400, detail="name, base_url and model_name are required")
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id FROM llm_configs WHERE name = ?",
            (normalized["name"],),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="llm config already exists")
        cursor.execute(
            """
            INSERT INTO llm_configs (
              name, llm_use_case, provider_code, provider_type, base_url, api_key, model_name,
              system_prompt, temperature, is_enabled, is_active, is_trial_enabled,
              last_tested_at, last_test_status, last_test_message, last_test_latency_ms,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, NULL, NULL, NULL, NULL, ?, ?)
            """,
            (
                normalized["name"],
                normalized["llm_use_case"],
                normalized["provider_code"],
                normalized["provider_type"],
                normalized["base_url"],
                "",
                normalized["model_name"],
                normalized["system_prompt"],
                normalized["temperature"],
                1 if normalized["is_enabled"] else 0,
                created_at,
                created_at,
            ),
        )
        config_id = int(cursor.lastrowid)
    set_llm_api_key(config_id, api_key)
    record_changelog(normalized["model_name"], "added", f"新增试用模型: {normalized['name']} ({normalized['model_name']})")
    return {"code": 0, "message": "ok", "data": {"id": config_id}}


@router.patch("/trial-llm-configs/{config_id}")
def update_trial_llm_config(
    config_id: int,
    payload: LlmConfigPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    normalized = normalize_llm_payload(payload, LLM_USE_CASE_TRIAL)
    updated_at = now_iso()
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id, api_key, model_name, llm_use_case FROM llm_configs WHERE id = ?",
            (config_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="llm config not found")
        if (existing["llm_use_case"] or LLM_USE_CASE_EVALUATION) != LLM_USE_CASE_TRIAL:
            raise HTTPException(status_code=400, detail="config belongs to qa evaluation scope")
        api_key = normalized["api_key"]
        if api_key == "__KEEP_EXISTING__" or not api_key:
            api_key = get_llm_api_key(config_id, existing["api_key"])
        if not normalized["name"] or not normalized["base_url"] or not normalized["model_name"]:
            raise HTTPException(status_code=400, detail="name, base_url and model_name are required")
        cursor.execute(
            """
            UPDATE llm_configs
            SET name = ?,
                llm_use_case = ?,
                provider_code = ?,
                provider_type = ?,
                base_url = ?,
                api_key = ?,
                model_name = ?,
                system_prompt = ?,
                temperature = ?,
                is_enabled = ?,
                is_active = 0,
                is_trial_enabled = 1,
                updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["name"],
                normalized["llm_use_case"],
                normalized["provider_code"],
                normalized["provider_type"],
                normalized["base_url"],
                "",
                normalized["model_name"],
                normalized["system_prompt"],
                normalized["temperature"],
                1 if normalized["is_enabled"] else 0,
                updated_at,
                config_id,
            ),
        )
    if api_key:
        set_llm_api_key(config_id, api_key)
    if normalized["model_name"] != existing["model_name"]:
        record_changelog(
            normalized["model_name"], "updated",
            f"试用模型更新: {normalized['name']} ({existing['model_name']} → {normalized['model_name']})",
        )
    return {"code": 0, "message": "ok", "data": {"id": config_id}}


@router.post("/llm-configs/{config_id}/activate")
def activate_llm_config(
    config_id: int,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id, llm_use_case FROM llm_configs WHERE id = ?",
            (config_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="llm config not found")
        if (existing["llm_use_case"] or LLM_USE_CASE_EVALUATION) != LLM_USE_CASE_EVALUATION:
            raise HTTPException(status_code=400, detail="trial-only llm config cannot be activated for qa evaluation")
        cursor.execute("UPDATE llm_configs SET is_active = 0")
        cursor.execute(
            "UPDATE llm_configs SET is_enabled = 1, is_active = 1, updated_at = ? WHERE id = ?",
            (now_iso(), config_id),
        )
    return {"code": 0, "message": "ok", "data": {"id": config_id, "is_active": True}}


@router.post("/llm-configs/{config_id}/enable")
def enable_llm_config(
    config_id: int,
    payload: LlmConfigEnablePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    updated_at = now_iso()
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id, is_active, llm_use_case FROM llm_configs WHERE id = ?",
            (config_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="llm config not found")
        if (existing["llm_use_case"] or LLM_USE_CASE_EVALUATION) != LLM_USE_CASE_EVALUATION:
            raise HTTPException(status_code=400, detail="config belongs to model trial scope")
        cursor.execute(
            """
            UPDATE llm_configs
            SET is_enabled = ?, is_active = CASE WHEN ? = 0 THEN 0 ELSE is_active END, updated_at = ?
            WHERE id = ?
            """,
            (1 if payload.is_enabled else 0, 1 if payload.is_enabled else 0, updated_at, config_id),
        )
    return {
        "code": 0,
        "message": "ok",
        "data": {"id": config_id, "is_enabled": payload.is_enabled},
    }


@router.post("/llm-configs/{config_id}/trial-enable")
def redirect_trial_toggle(
    config_id: int,
    payload: LlmConfigTrialEnablePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    raise HTTPException(status_code=410, detail="use /api/admin/trial-llm-configs pages and endpoints instead")


@router.post("/trial-llm-configs/{config_id}/enable")
def enable_trial_llm_config(
    config_id: int,
    payload: LlmConfigEnablePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id, llm_use_case FROM llm_configs WHERE id = ?",
            (config_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="llm config not found")
        if (existing["llm_use_case"] or LLM_USE_CASE_EVALUATION) != LLM_USE_CASE_TRIAL:
            raise HTTPException(status_code=400, detail="config belongs to qa evaluation scope")
        cursor.execute(
            "UPDATE llm_configs SET is_enabled = ?, updated_at = ? WHERE id = ?",
            (1 if payload.is_enabled else 0, now_iso(), config_id),
        )
    return {"code": 0, "message": "ok", "data": {"id": config_id, "is_enabled": payload.is_enabled}}


@router.post("/llm-configs/{config_id}/test")
def test_llm_config(
    config_id: int,
    current_user: CurrentUser = Depends(require_admin),
):
    return _test_llm_config(config_id, LLM_USE_CASE_EVALUATION)


@router.post("/trial-llm-configs/{config_id}/test")
def test_trial_llm_config(
    config_id: int,
    current_user: CurrentUser = Depends(require_admin),
):
    return _test_llm_config(config_id, LLM_USE_CASE_TRIAL)


def _test_llm_config(config_id: int, expected_use_case: str):
    with db_cursor() as cursor:
        row = cursor.execute(
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
              temperature
            FROM llm_configs
            WHERE id = ?
            """,
            (config_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="llm config not found")
        actual_use_case = row["llm_use_case"] or LLM_USE_CASE_EVALUATION
        if actual_use_case != expected_use_case:
            raise HTTPException(
                status_code=400,
                detail=(
                    "config belongs to model trial scope"
                    if actual_use_case == LLM_USE_CASE_TRIAL
                    else "config belongs to qa evaluation scope"
                ),
            )

    api_key = get_llm_api_key(config_id, row["api_key"])
    tested_at = now_iso()
    if not api_key:
        message = "本地未找到 API Key，请先在当前机器保存密钥。"
        with db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE llm_configs
                SET last_tested_at = ?, last_test_status = 'failed',
                    last_test_message = ?, last_test_latency_ms = NULL
                WHERE id = ?
                """,
                (tested_at, message, config_id),
            )
        return {"code": 0, "message": "ok", "data": {"passed": False, "message": message}}

    started = time.perf_counter()
    try:
        if row["provider_type"] != "openai_compatible":
            raise LlmClientError(f"unsupported provider: {row['provider_type']}")
        content = call_openai_compatible_chat(
            base_url=row["base_url"],
            api_key=api_key,
            model_name=row["model_name"],
            messages=[
                {"role": "system", "content": "你是连接检测助手。只返回 TEST_OK。"},
                {"role": "user", "content": "请返回 TEST_OK"},
            ],
            temperature=float(row["temperature"]),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = f"连接成功，模型返回：{content}"
        with db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE llm_configs
                SET last_tested_at = ?, last_test_status = 'passed',
                    last_test_message = ?, last_test_latency_ms = ?
                WHERE id = ?
                """,
                (tested_at, message, latency_ms, config_id),
            )
        return {
            "code": 0,
            "message": "ok",
            "data": {"passed": True, "message": message, "latency_ms": latency_ms},
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = str(exc)
        with db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE llm_configs
                SET last_tested_at = ?, last_test_status = 'failed',
                    last_test_message = ?, last_test_latency_ms = ?
                WHERE id = ?
                """,
                (tested_at, message, latency_ms, config_id),
            )
        return {
            "code": 0,
            "message": "ok",
            "data": {"passed": False, "message": message, "latency_ms": latency_ms},
        }


@router.get("/analytics/summary")
def get_analytics_summary(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        decision_counts = cursor.execute(
            """
            SELECT final_decision, COUNT(*) AS count
            FROM qa_aggregates
            WHERE final_decision IS NOT NULL
            GROUP BY final_decision
            """
        ).fetchall()
        decision_map = {row["final_decision"]: row["count"] for row in decision_counts}
        resolved_total = sum(
            decision_map.get(decision, 0) for decision in ("pass", "rewrite", "fail")
        )

        total_qas = cursor.execute("SELECT COUNT(*) AS count FROM qa_items").fetchone()["count"]
        disputed_qas = cursor.execute(
            """
            SELECT COUNT(DISTINCT qa_item_id) AS count
            FROM evaluation_tasks
            WHERE task_type = 'dispute_review'
            """
        ).fetchone()["count"]
        llm_adoptions = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM evaluation_records
            WHERE adopted_rewrite_answer_id IS NOT NULL
            """
        ).fetchone()["count"]
        total_records = cursor.execute(
            "SELECT COUNT(*) AS count FROM evaluation_records"
        ).fetchone()["count"]
        application_breakdown = cursor.execute(
            """
            SELECT
              a.id,
              a.name,
              COUNT(q.id) AS total_qas,
              SUM(CASE WHEN agg.final_decision = 'pass' THEN 1 ELSE 0 END) AS pass_count,
              SUM(CASE WHEN agg.final_decision = 'rewrite' THEN 1 ELSE 0 END) AS rewrite_count,
              SUM(CASE WHEN agg.final_decision = 'fail' THEN 1 ELSE 0 END) AS fail_count,
              AVG(agg.agreement_score) AS avg_agreement
            FROM applications a
            LEFT JOIN qa_items q ON q.application_id = a.id
            LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
            GROUP BY a.id, a.name
            ORDER BY a.name ASC
            """
        ).fetchall()
        expert_activity = cursor.execute(
            """
            SELECT
              u.id,
              u.full_name,
              COUNT(r.id) AS completed_reviews
            FROM users u
            LEFT JOIN evaluation_records r ON r.expert_user_id = u.id
            WHERE u.role = 'expert'
            GROUP BY u.id, u.full_name
            ORDER BY completed_reviews DESC, u.id ASC
            LIMIT 5
            """
        ).fetchall()

    pass_rate = (decision_map.get("pass", 0) / resolved_total * 100) if resolved_total else 0.0
    rewrite_rate = (
        decision_map.get("rewrite", 0) / resolved_total * 100
    ) if resolved_total else 0.0
    dispute_rate = (disputed_qas / total_qas * 100) if total_qas else 0.0
    llm_adoption_rate = (llm_adoptions / total_records * 100) if total_records else 0.0

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "metrics": {
                "pass_rate": round(pass_rate, 1),
                "rewrite_rate": round(rewrite_rate, 1),
                "dispute_rate": round(dispute_rate, 1),
                "llm_adoption_rate": round(llm_adoption_rate, 1),
            },
            "application_breakdown": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "total_qas": row["total_qas"] or 0,
                    "pass_count": row["pass_count"] or 0,
                    "rewrite_count": row["rewrite_count"] or 0,
                    "fail_count": row["fail_count"] or 0,
                    "avg_agreement": round(row["avg_agreement"], 2)
                    if row["avg_agreement"] is not None
                    else None,
                }
                for row in application_breakdown
            ],
            "top_experts": [
                {
                    "id": row["id"],
                    "full_name": row["full_name"],
                    "completed_reviews": row["completed_reviews"] or 0,
                }
                for row in expert_activity
            ],
        },
    }


@router.get("/jobs")
def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin),
):
    jobs = iter_queue_jobs()
    if status:
        jobs = [job for job in jobs if job["status"] == status]
    if job_type:
        jobs = [job for job in jobs if job["type"] == job_type]
    summary = {
        "pending": sum(1 for job in jobs if job["status"] == "pending"),
        "processing": sum(1 for job in jobs if job["status"] == "processing"),
        "done": sum(1 for job in jobs if job["status"] == "done"),
        "failed": sum(1 for job in jobs if job["status"] == "failed"),
    }
    return {"code": 0, "message": "ok", "data": {"summary": summary, "jobs": jobs}}


@router.post("/exports")
def create_export(
    payload: ExportCreatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    allowed_types = {"final_dataset", "review_records", "disputed_cases", "sft_dataset"}
    allowed_formats = {"json", "jsonl"}
    if payload.export_type not in allowed_types:
        raise HTTPException(status_code=400, detail="unsupported export type")
    if payload.file_format not in allowed_formats:
        raise HTTPException(status_code=400, detail="unsupported export format")

    with db_cursor() as cursor:
        if payload.application_id is not None:
            application = cursor.execute(
                "SELECT id FROM applications WHERE id = ?",
                (payload.application_id,),
            ).fetchone()
            if not application:
                raise HTTPException(status_code=404, detail="application not found")

        technical_type_codes = [code.strip() for code in payload.technical_type_codes if code.strip()]
        if technical_type_codes:
            rows = cursor.execute(
                f"""
                SELECT code
                FROM technical_types
                WHERE code IN ({",".join("?" for _ in technical_type_codes)})
                """,
                tuple(technical_type_codes),
            ).fetchall()
            found_codes = {row["code"] for row in rows}
            missing_codes = [code for code in technical_type_codes if code not in found_codes]
            if missing_codes:
                raise HTTPException(
                    status_code=404,
                    detail=f"technical types not found: {', '.join(missing_codes)}",
                )

        job_id = f"export_{uuid4().hex}"
        cursor.execute(
            """
            INSERT INTO export_jobs (
              job_id, export_type, application_id, technical_type_codes_json, date_from, date_to,
              file_format, status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                job_id,
                payload.export_type,
                payload.application_id,
                json.dumps(technical_type_codes, ensure_ascii=False),
                payload.date_from,
                payload.date_to,
                payload.file_format,
                current_user["id"],
                now_iso(),
            ),
        )
        export_job_id = int(cursor.lastrowid)

    try:
        queue_job("export", {"export_job_id": export_job_id}, job_id=job_id)
    except Exception as exc:
        with db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE export_jobs
                SET status = 'failed',
                    completed_at = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (now_iso(), str(exc), export_job_id),
            )
        raise HTTPException(status_code=500, detail="failed to queue export job")

    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT ej.*, a.name AS application_name
            FROM export_jobs ej
            LEFT JOIN applications a ON a.id = ej.application_id
            WHERE ej.id = ?
            """,
            (export_job_id,),
        ).fetchone()

    return {"code": 0, "message": "ok", "data": serialize_export_job(row)}


@router.get("/exports")
def list_exports(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              ej.*,
              a.name AS application_name,
              u.full_name AS created_by_name
            FROM export_jobs ej
            LEFT JOIN applications a ON a.id = ej.application_id
            LEFT JOIN users u ON u.id = ej.created_by
            ORDER BY ej.id DESC
            """
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": [serialize_export_job(row) for row in rows],
    }


@router.delete("/exports/{export_id}")
def delete_export(export_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT *
            FROM export_jobs
            WHERE id = ?
            """,
            (export_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="export job not found")
        if row["status"] == "processing":
            raise HTTPException(status_code=409, detail="processing export job cannot be deleted")

        file_path = Path(row["file_path"]) if row["file_path"] else None
        job_id = row["job_id"]
        export_file_glob = f"export_{export_id}_*"
        cursor.execute("DELETE FROM export_jobs WHERE id = ?", (export_id,))

    if file_path and file_path.exists():
        file_path.unlink()
    for orphaned_file in EXPORT_DIR.glob(export_file_glob):
        if orphaned_file.is_file():
            orphaned_file.unlink()

    for status in ("pending", "processing", "done", "failed"):
        queue_path = QUEUE_DIR / status / f"{job_id}.json"
        if queue_path.exists():
            queue_path.unlink()
        error_path = QUEUE_DIR / status / f"{job_id}.error.txt"
        if error_path.exists():
            error_path.unlink()

    return {"code": 0, "message": "ok", "data": {"id": export_id}}


@news_router.get("/api/exports/stats")
def export_stats(current_user: CurrentUser = Depends(get_current_user)):
    with db_cursor() as cursor:
        daily_import_rows = cursor.execute(
            """
            WITH RECURSIVE days(day) AS (
              SELECT date('now', '-55 day')
              UNION ALL
              SELECT date(day, '+1 day') FROM days WHERE day < date('now')
            )
            SELECT
              days.day AS period,
              COALESCE(imports.import_count, 0) AS import_count,
              COALESCE(reviews.review_count, 0) AS review_count
            FROM days
            LEFT JOIN (
              SELECT date(created_at) AS day, COUNT(*) AS import_count
              FROM qa_items
              GROUP BY date(created_at)
            ) imports ON imports.day = days.day
            LEFT JOIN (
              SELECT date(submitted_at) AS day, COUNT(*) AS review_count
              FROM evaluation_tasks
              WHERE status = 'submitted' AND submitted_at IS NOT NULL
              GROUP BY date(submitted_at)
            ) reviews ON reviews.day = days.day
            ORDER BY days.day DESC
            """
        ).fetchall()
        weekly_import_rows = cursor.execute(
            """
            SELECT
              strftime('%Y-W%W', periods.week_start) AS period,
              periods.week_start AS period_start,
              date(periods.week_start, '+6 day') AS period_end,
              COALESCE(imports.import_count, 0) AS import_count,
              COALESCE(reviews.review_count, 0) AS review_count
            FROM (
              SELECT week_start FROM (
                SELECT date(
                  created_at,
                  printf('-%d day', (CAST(strftime('%w', created_at) AS integer) + 6) % 7)
                ) AS week_start
                FROM qa_items
                UNION
                SELECT date(
                  submitted_at,
                  printf('-%d day', (CAST(strftime('%w', submitted_at) AS integer) + 6) % 7)
                ) AS week_start
                FROM evaluation_tasks
                WHERE status = 'submitted' AND submitted_at IS NOT NULL
              )
              WHERE week_start IS NOT NULL
              ORDER BY week_start DESC
              LIMIT 8
            ) periods
            LEFT JOIN (
              SELECT
                date(
                  created_at,
                  printf('-%d day', (CAST(strftime('%w', created_at) AS integer) + 6) % 7)
                ) AS week_start,
                COUNT(*) AS import_count
              FROM qa_items
              GROUP BY week_start
            ) imports ON imports.week_start = periods.week_start
            LEFT JOIN (
              SELECT
                date(
                  submitted_at,
                  printf('-%d day', (CAST(strftime('%w', submitted_at) AS integer) + 6) % 7)
                ) AS week_start,
                COUNT(*) AS review_count
              FROM evaluation_tasks
              WHERE status = 'submitted' AND submitted_at IS NOT NULL
              GROUP BY week_start
            ) reviews ON reviews.week_start = periods.week_start
            ORDER BY periods.week_start DESC
            """
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "daily": [dict(row) for row in daily_import_rows],
            "weekly": [dict(row) for row in weekly_import_rows],
        },
    }


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: int,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT id, file_path, export_type, file_format, status
            FROM export_jobs
            WHERE id = ?
            """,
            (export_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="export not found")
    if row["status"] != "done" or not row["file_path"]:
        raise HTTPException(status_code=409, detail="export file not ready")

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="export file missing")

    return FileResponse(
        path=file_path,
        media_type="application/json",
        filename=file_path.name,
    )


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, current_user: CurrentUser = Depends(require_admin)):
    failed_path = QUEUE_DIR / "failed" / f"{job_id}.json"
    if not failed_path.exists():
        raise HTTPException(status_code=404, detail="failed job not found")
    pending_path = QUEUE_DIR / "pending" / failed_path.name
    error_path = failed_path.with_suffix(".error.txt")
    if pending_path.exists():
        raise HTTPException(status_code=409, detail="job already pending")
    payload = json.loads(failed_path.read_text(encoding="utf-8"))
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    payload["meta"] = {
        **meta,
        "retry_count": int(meta.get("retry_count", 0)) + 1,
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
        "last_error": None,
    }
    failed_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failed_path.replace(pending_path)
    if error_path.exists():
        error_path.unlink()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "job_id": job_id,
            "status": "pending",
            "retry_count": payload["meta"]["retry_count"],
        },
    }


@router.post("/jobs/run-once")
def run_one_job(current_user: CurrentUser = Depends(require_admin)):
    next_job = get_next_job()
    if next_job is None:
        return {"code": 0, "message": "ok", "data": {"processed": False, "job_id": None}}
    job_id = next_job.stem
    process_job(next_job)
    return {"code": 0, "message": "ok", "data": {"processed": True, "job_id": job_id}}


@router.get("/experts")
def list_experts(
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin),
):
    query = """
        SELECT
          u.id,
          u.username,
          u.full_name,
          u.organization,
          u.title,
          u.status,
          u.created_at,
          u.allow_cross_business_review
        FROM users u
        WHERE u.role = 'expert'
    """
    params: Tuple[str, ...] = ()
    if status:
        query += " AND u.status = ?"
        params = (status,)
    query += " ORDER BY u.id DESC"
    with db_cursor() as cursor:
        rows = cursor.execute(query, params).fetchall()
        experts = [dict(row) for row in rows]
        if not experts:
            return {"code": 0, "message": "ok", "data": []}

        expert_ids = tuple(expert["id"] for expert in experts)
        placeholders = ",".join("?" for _ in expert_ids)
        application_rows = cursor.execute(
            f"""
            SELECT ea.expert_user_id, a.id, a.name
            FROM expert_applications ea
            JOIN applications a ON a.id = ea.application_id
            WHERE ea.expert_user_id IN ({placeholders})
            ORDER BY ea.priority ASC, a.name ASC
            """,
            expert_ids,
        ).fetchall()
        business_tag_rows = cursor.execute(
            f"""
            SELECT ebt.expert_user_id, b.id, b.name
            FROM expert_business_tags ebt
            JOIN business_tags b ON b.id = ebt.business_tag_id
            WHERE ebt.expert_user_id IN ({placeholders})
            ORDER BY ebt.priority ASC, b.name ASC
            """,
            expert_ids,
        ).fetchall()

    application_map: dict[int, list[dict]] = {}
    for row in application_rows:
        application_map.setdefault(row["expert_user_id"], []).append(
            {"id": row["id"], "name": row["name"]}
        )

    business_tag_map: dict[int, list[dict]] = {}
    for row in business_tag_rows:
        business_tag_map.setdefault(row["expert_user_id"], []).append(
            {"id": row["id"], "name": row["name"]}
        )

    for expert in experts:
        expert["applications"] = application_map.get(expert["id"], [])
        expert["business_tags"] = business_tag_map.get(expert["id"], [])
        expert["allow_cross_business_review"] = bool(expert["allow_cross_business_review"])

    return {"code": 0, "message": "ok", "data": experts}


@router.patch("/experts/{expert_id}")
def update_expert_settings(
    expert_id: int,
    payload: ExpertSettingsPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    updated_at = now_iso()
    selected_business_tags: set[str] = set()
    with db_cursor() as cursor:
        expert = cursor.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'expert'",
            (expert_id,),
        ).fetchone()
        if not expert:
            raise HTTPException(status_code=404, detail="expert not found")

        cursor.execute(
            """
            UPDATE users
            SET allow_cross_business_review = ?
            WHERE id = ?
            """,
            (1 if payload.allow_cross_business_review else 0, expert_id),
        )
        cursor.execute(
            "DELETE FROM expert_business_tags WHERE expert_user_id = ?",
            (expert_id,),
        )
        for priority, business_tag_id in enumerate(payload.business_tag_ids, start=1):
            tag = cursor.execute(
                "SELECT code FROM business_tags WHERE id = ?",
                (business_tag_id,),
            ).fetchone()
            if not tag:
                continue
            selected_business_tags.add(tag["code"])
            cursor.execute(
                """
                INSERT INTO expert_business_tags (
                  expert_user_id, business_tag_id, priority, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (expert_id, business_tag_id, priority, updated_at),
            )
        if not payload.allow_cross_business_review:
            pending_tasks = cursor.execute(
                """
                SELECT t.id, q.business_tags_json
                FROM evaluation_tasks t
                JOIN qa_items q ON q.id = t.qa_item_id
                WHERE t.expert_user_id = ?
                  AND t.status IN ('pending', 'in_progress')
                """,
                (expert_id,),
            ).fetchall()
            for task in pending_tasks:
                qa_tags = parse_tag_codes(task["business_tags_json"])
                if qa_tags and not (qa_tags & selected_business_tags):
                    cursor.execute(
                        """
                        UPDATE evaluation_tasks
                        SET status = 'cancelled'
                        WHERE id = ?
                        """,
                        (task["id"],),
                    )

    return {"code": 0, "message": "ok", "data": {"id": expert_id}}


@router.post("/experts/{expert_id}/approve")
def approve_expert(
    expert_id: int,
    payload: ExpertDecisionPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    approved_at = now_iso()
    with db_cursor() as cursor:
        updated = cursor.execute(
            """
            UPDATE users
            SET status = 'approved', approved_at = ?
            WHERE id = ? AND role = 'expert'
            """,
            (approved_at, expert_id),
        ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="expert not found")
    return {"code": 0, "message": "ok", "data": {"id": expert_id, "status": "approved"}}


@router.post("/experts/{expert_id}/reject")
def reject_expert(
    expert_id: int,
    payload: ExpertDecisionPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        updated = cursor.execute(
            """
            UPDATE users
            SET status = 'rejected'
            WHERE id = ? AND role = 'expert'
            """,
            (expert_id,),
        ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="expert not found")
    return {"code": 0, "message": "ok", "data": {"id": expert_id, "status": "rejected"}}


class ResetPasswordPayload(BaseModel):
    new_password: str = Field(min_length=6)


class NewsCreatePayload(BaseModel):
    title: str
    content: str
    is_published: bool = False


class NewsUpdatePayload(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_published: Optional[bool] = None


class FeedbackPayload(BaseModel):
    title: str
    content: str
    category: str = "general"


@router.post("/experts/{expert_id}/disable")
def disable_expert(
    expert_id: int,
    payload: ExpertDecisionPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        updated = cursor.execute(
            """
            UPDATE users
            SET status = 'disabled'
            WHERE id = ? AND role = 'expert'
            """,
            (expert_id,),
        ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="expert not found")
    return {"code": 0, "message": "ok", "data": {"id": expert_id, "status": "disabled"}}


@router.post("/experts/{expert_id}/reset-password")
def reset_expert_password(
    expert_id: int,
    payload: ResetPasswordPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        expert = cursor.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'expert'",
            (expert_id,),
        ).fetchone()
        if not expert:
            raise HTTPException(status_code=404, detail="expert not found")
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(payload.new_password), expert_id),
        )
        cursor.execute(
            "DELETE FROM auth_sessions WHERE user_id = ?",
            (expert_id,),
        )
    return {"code": 0, "message": "ok", "data": {"id": expert_id}}


@router.post("/imports/upload")
async def upload_import(
    file: UploadFile = File(...),
    name: str = Form(default="default-batch"),
    source: str = Form(default="manual-upload"),
    application_id: int = Form(...),
    technical_type_code: str = Form(...),
    business_tags_json: str = Form(default="[]"),
    current_user: CurrentUser = Depends(require_admin),
):
    business_tags = parse_import_business_tags(business_tags_json)
    application_db_id, technical_type_id = validate_import_target(
        application_id,
        technical_type_code,
        business_tags,
    )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}_{Path(file.filename or 'dataset.json').name}"
    file_path = UPLOAD_DIR / filename
    file_path.write_bytes(await file.read())

    batch_id = create_dataset_batch(
        name=name,
        source=source,
        file_path=file_path,
        application_id=application_db_id,
        technical_type_id=technical_type_id,
        business_tags=business_tags,
        created_by=current_user["id"],
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {"batch_id": batch_id, "file_path": str(file_path), "import_status": "uploaded"},
    }


@router.post("/imports/push")
def push_import(payload: ImportPushPayload, current_user: CurrentUser = Depends(require_admin)):
    if not payload.rows:
        raise HTTPException(status_code=400, detail="rows must not be empty")

    business_tags = [code for code in payload.business_tag_codes if code]
    application_db_id, technical_type_id = validate_import_target(
        payload.application_id,
        payload.technical_type_code,
        business_tags,
    )

    rows = [row.model_dump(exclude_none=True) for row in payload.rows]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}_remote_sync.json"
    file_path = UPLOAD_DIR / filename
    file_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    batch_id = create_dataset_batch(
        name=payload.name,
        source=payload.source,
        file_path=file_path,
        application_id=application_db_id,
        technical_type_id=technical_type_id,
        business_tags=business_tags,
        created_by=current_user["id"],
    )

    job_id = None
    parse_queued = False
    if payload.auto_parse:
        job_id, parse_queued = queue_unique_import_job(batch_id)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "batch_id": batch_id,
            "job_id": job_id,
            "file_path": str(file_path),
            "import_status": "uploaded",
            "parse_queued": parse_queued,
        },
    }


@router.post("/imports/{batch_id}/parse")
def parse_import(batch_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        batch = cursor.execute(
            "SELECT id, import_status FROM dataset_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")
    if batch["import_status"] == "parsed":
        return {
            "code": 0,
            "message": "ok",
            "data": {"job_id": None, "parse_queued": False, "import_status": "parsed"},
        }
    job_id, parse_queued = queue_unique_import_job(batch_id)
    return {
        "code": 0,
        "message": "ok",
        "data": {"job_id": job_id, "parse_queued": parse_queued, "import_status": batch["import_status"]},
    }


@router.get("/imports")
def list_imports(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT
              b.id,
              b.name,
              b.source,
              b.file_path,
              b.import_status,
              b.total_count,
              b.success_count,
              b.fail_count,
              b.created_at,
              b.application_id,
              b.source_batch_name,
              b.external_batch_id,
              b.uploader_user_id,
              b.business_tags_json,
              a.name AS application_name,
              u.username AS uploader_username,
              u.full_name AS uploader_full_name,
              tt.code AS technical_type_code,
              tt.name AS technical_type_name
            FROM dataset_batches b
            LEFT JOIN applications a ON a.id = b.application_id
            LEFT JOIN users u ON u.id = b.uploader_user_id
            LEFT JOIN technical_types tt ON tt.id = b.technical_type_id
            ORDER BY b.id DESC
            """
        ).fetchall()
    return {"code": 0, "message": "ok", "data": [dict(row) for row in rows]}


@router.get("/imports/{batch_id}")
def get_import_detail(batch_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        batch = cursor.execute(
            """
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
              b.business_tags_json,
              b.uploader_user_id,
              b.self_review_status,
              b.peer_review_status,
              a.name AS application_name,
              u.username AS uploader_username,
              u.full_name AS uploader_full_name,
              tt.code AS technical_type_code,
              tt.name AS technical_type_name
            FROM dataset_batches b
            LEFT JOIN applications a ON a.id = b.application_id
            LEFT JOIN users u ON u.id = b.uploader_user_id
            LEFT JOIN technical_types tt ON tt.id = b.technical_type_id
            WHERE b.id = ?
            """,
            (batch_id,),
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="batch not found")

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
              q.context_text,
              q.source,
              q.source_model,
              q.metadata_json,
              ans.id AS current_answer_id,
              ans.answer_text AS current_answer_text,
              (
                SELECT COUNT(*)
                FROM evaluation_tasks t
                WHERE t.answer_id = ans.id
                  AND t.task_type = 'initial_review'
              ) AS review_task_total,
              (
                SELECT COUNT(*)
                FROM evaluation_tasks t
                WHERE t.answer_id = ans.id
                  AND t.task_type = 'initial_review'
                  AND t.status = 'submitted'
              ) AS review_task_submitted
            FROM qa_items q
            LEFT JOIN qa_answers ans ON ans.qa_item_id = q.id AND ans.is_current = 1
            WHERE q.dataset_batch_id = ?
            ORDER BY q.id DESC
            """,
            (batch_id,),
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "batch": dict(batch),
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


@router.get("/imports/{batch_id}/failures")
def list_import_failures(batch_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        batch = cursor.execute(
            """
            SELECT
              b.id,
              b.name,
              b.import_status,
              b.total_count,
              b.success_count,
              b.fail_count,
              b.application_id,
              b.source_batch_name,
              b.external_batch_id,
              b.uploader_user_id,
              b.business_tags_json,
              a.name AS application_name,
              u.username AS uploader_username,
              u.full_name AS uploader_full_name,
              tt.code AS technical_type_code,
              tt.name AS technical_type_name
            FROM dataset_batches b
            LEFT JOIN applications a ON a.id = b.application_id
            LEFT JOIN users u ON u.id = b.uploader_user_id
            LEFT JOIN technical_types tt ON tt.id = b.technical_type_id
            WHERE b.id = ?
            """,
            (batch_id,),
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="batch not found")

        rows = cursor.execute(
            """
            SELECT id, row_no, external_id, question_preview, error_message, raw_payload_json, created_at
            FROM dataset_batch_failures
            WHERE dataset_batch_id = ?
            ORDER BY row_no ASC, id ASC
            """,
            (batch_id,),
        ).fetchall()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "batch": dict(batch),
            "failures": [dict(row) for row in rows],
        },
    }


@router.get("/qas")
def list_qas(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    keyword: Optional[str] = Query(default=None),
    operational_state: Optional[str] = Query(default=None),
    technical_type_code: Optional[str] = Query(default=None),
    business_tag_code: Optional[str] = Query(default=None),
    module_key: Optional[str] = Query(default=None),
    action_key: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(require_admin),
):
    normalized_keyword = keyword.strip().lower() if keyword else ""
    state_map = {
        "待聚合": "(agg.final_decision IS NULL OR agg.final_decision = 'pending')",
        "待最终确认": "(agg.final_decision IS NOT NULL AND agg.final_decision != 'pending' AND agg.final_standard_answer_id IS NULL)",
        "聚合与最终不一致": "(agg.current_answer_id IS NOT NULL AND agg.final_standard_answer_id IS NOT NULL AND agg.current_answer_id != agg.final_standard_answer_id)",
        "已闭环": "(agg.final_decision IS NOT NULL AND agg.final_decision != 'pending' AND agg.final_standard_answer_id IS NOT NULL AND (agg.current_answer_id IS NULL OR agg.current_answer_id = agg.final_standard_answer_id))",
    }

    def build_filter_parts(
        *,
        include_module_filter: bool = True,
        include_action_filter: bool = True,
    ) -> tuple[str, list[object]]:
        conditions: list[str] = []
        params: list[object] = []

        if normalized_keyword:
            keyword_like = f"%{normalized_keyword}%"
            conditions.append(
                """
                (
                  LOWER(a.name) LIKE ?
                  OR LOWER(COALESCE(tt.name, '')) LIKE ?
                  OR LOWER(COALESCE(tt.code, '')) LIKE ?
                  OR LOWER(q.question_text) LIKE ?
                  OR LOWER(q.status) LIKE ?
                  OR LOWER(COALESCE(agg.final_decision, '')) LIKE ?
                  OR LOWER(COALESCE(json_extract(q.metadata_json, '$.scene_name'), '')) LIKE ?
                  OR LOWER(COALESCE(json_extract(q.metadata_json, '$.module_name'), '')) LIKE ?
                  OR LOWER(COALESCE(json_extract(q.metadata_json, '$.action_name'), '')) LIKE ?
                  OR LOWER(COALESCE(q.business_tags_json, '')) LIKE ?
                )
                """
            )
            params.extend([keyword_like] * 10)

        if technical_type_code and technical_type_code != "all":
            conditions.append("tt.code = ?")
            params.append(technical_type_code)

        if business_tag_code and business_tag_code != "all":
            conditions.append(
                "EXISTS (SELECT 1 FROM json_each(COALESCE(q.business_tags_json, '[]')) je WHERE je.value = ?)"
            )
            params.append(business_tag_code)

        if include_module_filter and module_key and module_key != "all":
            conditions.append("json_extract(q.metadata_json, '$.module_key') = ?")
            params.append(module_key)

        if include_action_filter and action_key and action_key != "all":
            conditions.append("json_extract(q.metadata_json, '$.action_key') = ?")
            params.append(action_key)

        if operational_state and operational_state != "all":
            condition = state_map.get(operational_state)
            if condition:
                conditions.append(condition)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        base_from_sql = f"""
            FROM qa_items q
            JOIN applications a ON a.id = q.application_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
            LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
            {where_sql}
        """
        return base_from_sql, params

    base_from_sql, params = build_filter_parts()
    module_from_sql, module_params = build_filter_parts(include_module_filter=False)
    action_from_sql, action_params = build_filter_parts(include_action_filter=False)

    with db_cursor() as cursor:
        total = cursor.execute(
            f"SELECT COUNT(*) AS count {base_from_sql}",
            tuple(params),
        ).fetchone()["count"]
        summary_row = cursor.execute(
            f"""
            SELECT
              SUM(CASE WHEN agg.final_decision IS NULL OR agg.final_decision = 'pending' THEN 1 ELSE 0 END) AS pending_aggregate,
              SUM(CASE WHEN agg.final_decision IS NOT NULL AND agg.final_decision != 'pending' AND agg.final_standard_answer_id IS NULL THEN 1 ELSE 0 END) AS pending_final,
              SUM(CASE WHEN agg.current_answer_id IS NOT NULL AND agg.final_standard_answer_id IS NOT NULL AND agg.current_answer_id != agg.final_standard_answer_id THEN 1 ELSE 0 END) AS mismatch,
              SUM(CASE WHEN agg.final_decision IS NOT NULL AND agg.final_decision != 'pending' AND agg.final_standard_answer_id IS NOT NULL AND (agg.current_answer_id IS NULL OR agg.current_answer_id = agg.final_standard_answer_id) THEN 1 ELSE 0 END) AS closed
            {base_from_sql}
            """,
            tuple(params),
        ).fetchone()
        module_rows = cursor.execute(
            f"""
            SELECT
              option_key,
              option_label,
              COUNT(*) AS item_count
            FROM (
              SELECT
                json_extract(q.metadata_json, '$.module_key') AS option_key,
                COALESCE(
                  NULLIF(json_extract(q.metadata_json, '$.module_name'), ''),
                  json_extract(q.metadata_json, '$.module_key')
                ) AS option_label
              {module_from_sql}
            ) module_options
            WHERE option_key IS NOT NULL
              AND option_key != ''
            GROUP BY option_key, option_label
            ORDER BY item_count DESC, option_label ASC
            """,
            tuple(module_params),
        ).fetchall()
        action_rows = cursor.execute(
            f"""
            SELECT
              option_key,
              option_label,
              COUNT(*) AS item_count
            FROM (
              SELECT
                json_extract(q.metadata_json, '$.action_key') AS option_key,
                COALESCE(
                  NULLIF(json_extract(q.metadata_json, '$.action_name'), ''),
                  json_extract(q.metadata_json, '$.action_key')
                ) AS option_label
              {action_from_sql}
            ) action_options
            WHERE option_key IS NOT NULL
              AND option_key != ''
            GROUP BY option_key, option_label
            ORDER BY item_count DESC, option_label ASC
            """,
            tuple(action_params),
        ).fetchall()
        total_pages = max((total + page_size - 1) // page_size, 1)
        current_page = min(page, total_pages) if total else 1
        offset = (current_page - 1) * page_size
        rows = cursor.execute(
            f"""
            SELECT
              q.id,
              q.external_id,
              q.question_text,
              q.status,
              q.business_tags_json,
              q.metadata_json,
              a.name AS application_name,
              tt.code AS technical_type_code,
              tt.name AS technical_type_name,
              agg.review_count,
              agg.final_decision,
              agg.agreement_score,
              agg.current_answer_id,
              agg.final_standard_answer_id
            {base_from_sql}
            ORDER BY q.id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
    data = []
    for row in rows:
        item = dict(row)
        item["question_summary"] = item["question_text"][:80]
        item.pop("question_text", None)
        data.append(item)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "items": data,
            "page": current_page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "summary": {
                "pending_aggregate": int(summary_row["pending_aggregate"] or 0),
                "pending_final": int(summary_row["pending_final"] or 0),
                "mismatch": int(summary_row["mismatch"] or 0),
                "closed": int(summary_row["closed"] or 0),
            },
            "facets": {
                "modules": [
                    {
                        "key": row["option_key"],
                        "label": row["option_label"],
                        "count": int(row["item_count"]),
                    }
                    for row in module_rows
                ],
                "actions": [
                    {
                        "key": row["option_key"],
                        "label": row["option_label"],
                        "count": int(row["item_count"]),
                    }
                    for row in action_rows
                ],
            },
        },
    }


@router.get("/qas/{qa_id}")
def get_qa_detail(qa_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        qa_item = cursor.execute(
            """
            SELECT q.*, a.name AS application_name, tt.code AS technical_type_code, tt.name AS technical_type_name
            FROM qa_items q
            JOIN applications a ON a.id = q.application_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
            WHERE q.id = ?
            """,
            (qa_id,),
        ).fetchone()
        if not qa_item:
            raise HTTPException(status_code=404, detail="qa not found")

        answers = cursor.execute(
            "SELECT * FROM qa_answers WHERE qa_item_id = ? ORDER BY id DESC",
            (qa_id,),
        ).fetchall()
        tasks = cursor.execute(
            "SELECT * FROM evaluation_tasks WHERE qa_item_id = ? ORDER BY id DESC",
            (qa_id,),
        ).fetchall()
        records = cursor.execute(
            "SELECT * FROM evaluation_records WHERE qa_item_id = ? ORDER BY id DESC",
            (qa_id,),
        ).fetchall()
        aggregate = cursor.execute(
            "SELECT * FROM qa_aggregates WHERE qa_item_id = ?",
            (qa_id,),
        ).fetchone()

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "qa_item": dict(qa_item),
            "answers": [dict(row) for row in answers],
            "tasks": [dict(row) for row in tasks],
            "records": [dict(row) for row in records],
            "aggregate": dict(aggregate) if aggregate else None,
        },
    }


@router.post("/qas/{qa_id}/aggregate/run")
def rerun_aggregate(qa_id: int, current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        qa_item = cursor.execute(
            "SELECT id FROM qa_items WHERE id = ?",
            (qa_id,),
        ).fetchone()
        if not qa_item:
            raise HTTPException(status_code=404, detail="qa not found")

        latest_record = cursor.execute(
            """
            SELECT answer_id
            FROM evaluation_records
            WHERE qa_item_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (qa_id,),
        ).fetchone()
        if latest_record:
            answer_id = latest_record["answer_id"]
        else:
            latest_task = cursor.execute(
                """
                SELECT answer_id
                FROM evaluation_tasks
                WHERE qa_item_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (qa_id,),
            ).fetchone()
            if not latest_task:
                raise HTTPException(status_code=409, detail="qa has no evaluation task to aggregate")
            answer_id = latest_task["answer_id"]

    job_id = queue_job("aggregate", {"qa_item_id": qa_id, "answer_id": answer_id})
    return {
        "code": 0,
        "message": "ok",
        "data": {"qa_id": qa_id, "answer_id": answer_id, "job_id": job_id},
    }


@router.post("/qas/{qa_id}/final-answer")
def confirm_final_answer(
    qa_id: int,
    payload: FinalAnswerPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        qa_item = cursor.execute(
            "SELECT id, status FROM qa_items WHERE id = ?",
            (qa_id,),
        ).fetchone()
        if not qa_item:
            raise HTTPException(status_code=404, detail="qa not found")

        answer = cursor.execute(
            """
            SELECT id, qa_item_id
            FROM qa_answers
            WHERE id = ? AND qa_item_id = ?
            """,
            (payload.answer_id, qa_id),
        ).fetchone()
        if not answer:
            raise HTTPException(status_code=404, detail="answer not found")

        cursor.execute(
            """
            UPDATE qa_answers
            SET answer_type = CASE
              WHEN answer_type = 'final_standard' THEN 'expert_confirmed_standard'
              ELSE answer_type
            END
            WHERE qa_item_id = ?
            """,
            (qa_id,),
        )
        cursor.execute(
            """
            UPDATE qa_answers
            SET answer_type = 'final_standard'
            WHERE id = ?
            """,
            (payload.answer_id,),
        )
        cursor.execute(
            """
            INSERT INTO qa_aggregates (
              qa_item_id, current_answer_id, review_count, final_decision,
              final_standard_answer_id, aggregated_at
            ) VALUES (?, ?, 0, 'pending', ?, ?)
            ON CONFLICT(qa_item_id) DO UPDATE SET
              final_standard_answer_id = excluded.final_standard_answer_id,
              aggregated_at = excluded.aggregated_at
            """,
            (qa_id, payload.answer_id, payload.answer_id, now_iso()),
        )
        cursor.execute(
            """
            UPDATE qa_items
            SET status = 'reviewed'
            WHERE id = ?
            """,
            (qa_id,),
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {"qa_id": qa_id, "final_standard_answer_id": payload.answer_id},
    }


@router.post("/tasks/dispatch")
def dispatch_tasks(
    payload: DispatchPayload,
    current_user: CurrentUser = Depends(require_admin),
):
    job_id = queue_job(
        "dispatch",
        {"application_id": payload.application_id, "limit": payload.limit},
    )
    return {"code": 0, "message": "ok", "data": {"job_id": job_id}}


def serialize_news(row, *, with_author: bool = True):
    item = dict(row)
    item["is_published"] = bool(item["is_published"])
    return item


@news_router.get("/api/news")
def list_published_news(current_user: CurrentUser = Depends(get_current_user)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT n.id, n.title, n.content, n.is_published, n.created_by,
                   n.created_at, n.updated_at, u.full_name AS created_by_name
            FROM news n
            LEFT JOIN users u ON u.id = n.created_by
            WHERE n.is_published = 1
            ORDER BY n.created_at DESC
            LIMIT 10
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [serialize_news(row) for row in rows],
    }


@router.get("/news")
def list_all_news(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT n.id, n.title, n.content, n.is_published, n.created_by,
                   n.created_at, n.updated_at, u.full_name AS created_by_name
            FROM news n
            LEFT JOIN users u ON u.id = n.created_by
            ORDER BY n.created_at DESC
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [serialize_news(row) for row in rows],
    }


@router.post("/news")
def create_news(
    payload: NewsCreatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO news (title, content, is_published, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.title.strip(),
                payload.content.strip(),
                1 if payload.is_published else 0,
                current_user["id"],
                created_at,
                created_at,
            ),
        )
        news_id = int(cursor.lastrowid)
    return {"code": 0, "message": "ok", "data": {"id": news_id}}


@router.patch("/news/{news_id}")
def update_news(
    news_id: int,
    payload: NewsUpdatePayload,
    current_user: CurrentUser = Depends(require_admin),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return {"code": 0, "message": "ok", "data": {"id": news_id}}
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id FROM news WHERE id = ?",
            (news_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="news not found")
        fields = []
        values: list[object] = []
        for key, value in updates.items():
            if key == "is_published":
                fields.append("is_published = ?")
                values.append(1 if value else 0)
            elif key == "title":
                fields.append("title = ?")
                values.append(value.strip())
            elif key == "content":
                fields.append("content = ?")
                values.append(value.strip())
        if fields:
            fields.append("updated_at = ?")
            values.append(now_iso())
            values.append(news_id)
            cursor.execute(
                f"UPDATE news SET {', '.join(fields)} WHERE id = ?",
                tuple(values),
            )
    return {"code": 0, "message": "ok", "data": {"id": news_id}}


@router.delete("/news/{news_id}")
def delete_news(
    news_id: int,
    current_user: CurrentUser = Depends(require_admin),
):
    with db_cursor() as cursor:
        existing = cursor.execute(
            "SELECT id FROM news WHERE id = ?",
            (news_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="news not found")
        cursor.execute("DELETE FROM news WHERE id = ?", (news_id,))
    return {"code": 0, "message": "ok", "data": {"id": news_id}}


@news_router.post("/api/feedback")
def submit_feedback(
    payload: FeedbackPayload,
    current_user: CurrentUser = Depends(get_current_user),
):
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO feedbacks (title, content, category, user_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (payload.title.strip(), payload.content.strip(), payload.category.strip(), current_user["id"], created_at),
        )
        feedback_id = int(cursor.lastrowid)
    return {"code": 0, "message": "ok", "data": {"id": feedback_id, "created_at": created_at}}


@router.get("/feedbacks")
def list_feedbacks(current_user: CurrentUser = Depends(require_admin)):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT f.id, f.title, f.content, f.category, f.user_id, f.created_at,
                   u.full_name AS user_name, u.username
            FROM feedbacks f
            LEFT JOIN users u ON u.id = f.user_id
            ORDER BY f.created_at DESC
            LIMIT 100
            """
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [dict(row) for row in rows],
    }


@news_router.get("/api/models/changelog")
def get_model_changelog(
    days: int = 7,
    current_user: CurrentUser = Depends(get_current_user),
):
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, model_name, change_type, description, created_at
            FROM model_changelogs
            WHERE created_at >= date('now', ? || ' days')
            ORDER BY created_at DESC
            """,
            (f"-{days}",),
        ).fetchall()
    return {
        "code": 0,
        "message": "ok",
        "data": [dict(row) for row in rows],
    }


@news_router.get("/api/stats")
def get_public_stats(current_user: CurrentUser = Depends(get_current_user)):
    with db_cursor() as cursor:
        today_qa = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM qa_items
            WHERE date(created_at) = date('now')
            """
        ).fetchone()["count"]
        week_qa = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM qa_items
            WHERE created_at >= date('now', '-6 days')
            """
        ).fetchone()["count"]
        today_reviews = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM evaluation_records
            WHERE date(created_at) = date('now')
            """
        ).fetchone()["count"]
        week_reviews = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM evaluation_records
            WHERE created_at >= date('now', '-6 days')
            """
        ).fetchone()["count"]
        total_models = cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM llm_configs
            WHERE is_trial_enabled = 1 AND is_enabled = 1
            """
        ).fetchone()["count"]
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "today_qa_count": today_qa,
            "week_qa_count": week_qa,
            "today_review_count": today_reviews,
            "week_review_count": week_reviews,
            "available_model_count": total_models,
        },
    }
