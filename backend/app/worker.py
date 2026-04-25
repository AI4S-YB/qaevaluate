from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import time
from typing import Dict, Optional
from uuid import uuid4

from .config import EXPORT_DIR, QUEUE_DIR
from .db import db_cursor, init_db
from .llm_client import (
    LlmClientError,
    build_task_messages,
    call_openai_compatible_chat,
    format_review_message,
    parse_review_response,
)
from .llm_config_store import get_llm_api_key


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


IMPORT_PARSE_LOCK_TIMEOUT = timedelta(minutes=30)


def stale_import_lock_before_iso() -> str:
    return (datetime.utcnow() - IMPORT_PARSE_LOCK_TIMEOUT).replace(microsecond=0).isoformat()


def claim_import_batch_lock(cursor, batch_id: int) -> Optional[str]:
    lock_token = uuid4().hex
    locked_at = now_iso()
    cursor.execute(
        """
        UPDATE dataset_batches
        SET parse_lock_token = ?, parse_lock_acquired_at = ?
        WHERE id = ?
          AND import_status != 'parsed'
          AND (
            parse_lock_token IS NULL
            OR parse_lock_token = ''
            OR parse_lock_acquired_at IS NULL
            OR parse_lock_acquired_at < ?
          )
        """,
        (lock_token, locked_at, batch_id, stale_import_lock_before_iso()),
    )
    if cursor.rowcount:
        return lock_token
    return None


def release_import_batch_lock(cursor, batch_id: int, lock_token: str) -> None:
    cursor.execute(
        """
        UPDATE dataset_batches
        SET parse_lock_token = NULL, parse_lock_acquired_at = NULL
        WHERE id = ? AND parse_lock_token = ?
        """,
        (batch_id, lock_token),
    )


def mark_import_batch_failed(cursor, batch_id: int) -> None:
    cursor.execute(
        """
        UPDATE dataset_batches
        SET import_status = 'failed',
            parse_lock_token = NULL,
            parse_lock_acquired_at = NULL
        WHERE id = ?
        """,
        (batch_id,),
    )


def parse_business_tag_codes(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item) for item in parsed if isinstance(item, str) and item}


def normalize_answer_text(value: str) -> str:
    return " ".join(value.split()).strip()


def expert_can_review_business_tags(
    qa_business_tags: set[str],
    allow_cross_business_review: bool,
    expert_business_tags: set[str],
) -> bool:
    if allow_cross_business_review:
        return True
    if not qa_business_tags:
        return True
    return bool(qa_business_tags & expert_business_tags)


def load_application_experts(cursor, application_id: int) -> dict[int, dict]:
    rows = cursor.execute(
        """
        SELECT
          u.id,
          u.allow_cross_business_review,
          b.code AS business_tag_code
        FROM users u
        JOIN expert_applications ea ON ea.expert_user_id = u.id
        LEFT JOIN expert_business_tags ebt ON ebt.expert_user_id = u.id
        LEFT JOIN business_tags b ON b.id = ebt.business_tag_id
        WHERE u.role = 'expert'
          AND u.status = 'approved'
          AND ea.application_id = ?
        ORDER BY u.id ASC, ebt.priority ASC, b.name ASC
        """,
        (application_id,),
    ).fetchall()

    experts: dict[int, dict] = {}
    for row in rows:
        expert = experts.setdefault(
            row["id"],
            {
                "id": row["id"],
                "allow_cross_business_review": bool(row["allow_cross_business_review"]),
                "business_tags": set(),
            },
        )
        if row["business_tag_code"]:
            expert["business_tags"].add(row["business_tag_code"])
    return experts


def create_self_review_tasks_for_batch(cursor, batch_id: int, uploader_user_id: int) -> int:
    rows = cursor.execute(
        """
        SELECT
          q.id AS qa_item_id,
          ans.id AS answer_id
        FROM qa_items q
        JOIN qa_answers ans ON ans.qa_item_id = q.id
        WHERE q.dataset_batch_id = ?
          AND ans.is_current = 1
        ORDER BY q.id ASC, ans.id ASC
        """,
        (batch_id,),
    ).fetchall()

    created_count = 0
    for row in rows:
        existing = cursor.execute(
            """
            SELECT id
            FROM evaluation_tasks
            WHERE qa_item_id = ?
              AND answer_id = ?
              AND expert_user_id = ?
              AND round_no = 1
              AND task_type = 'initial_review'
            """,
            (row["qa_item_id"], row["answer_id"], uploader_user_id),
        ).fetchone()
        if existing:
            continue
        cursor.execute(
            """
            INSERT INTO evaluation_tasks (
              qa_item_id, answer_id, expert_user_id, round_no,
              task_type, status, assigned_at
            ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
            """,
            (row["qa_item_id"], row["answer_id"], uploader_user_id, now_iso()),
        )
        cursor.execute(
            "UPDATE qa_items SET status = 'in_review' WHERE id = ?",
            (row["qa_item_id"],),
        )
        created_count += 1

    return created_count


def move_job(path: Path, target_dir: str) -> Path:
    destination = QUEUE_DIR / target_dir / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), destination)
    return destination


def get_next_job() -> Optional[Path]:
    pending_dir = QUEUE_DIR / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    jobs = sorted(pending_dir.glob("*.json"))
    if not jobs:
        return None
    return jobs[0]


def import_batch(batch_id: int) -> None:
    lock_token: Optional[str] = None
    try:
        with db_cursor() as cursor:
            batch = cursor.execute(
                """
                SELECT
                  b.id,
                  b.file_path,
                  b.application_id,
                  b.business_tags_json,
                  b.uploader_user_id,
                  b.self_review_status,
                  b.import_status,
                  a.name AS application_name,
                  tt.id AS technical_type_id,
                  tt.code AS technical_type_code
                FROM dataset_batches b
                LEFT JOIN applications a ON a.id = b.application_id
                LEFT JOIN technical_types tt ON tt.id = b.technical_type_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            if not batch:
                raise ValueError(f"batch {batch_id} not found")
            if batch["import_status"] == "parsed":
                return
            lock_token = claim_import_batch_lock(cursor, batch_id)
            if not lock_token:
                return
            if not batch["application_id"] or not batch["application_name"]:
                raise ValueError("batch application not configured")
            if not batch["technical_type_id"] or not batch["technical_type_code"]:
                raise ValueError("batch technical_type not configured")
            batch_business_tags = parse_business_tag_codes(batch["business_tags_json"])
            rows = json.loads(Path(batch["file_path"]).read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise ValueError("import file must be a JSON array")

            success_count = 0
            fail_count = 0
            total_count = len(rows)
            cursor.execute(
                "DELETE FROM dataset_batch_failures WHERE dataset_batch_id = ?",
                (batch_id,),
            )

            for index, item in enumerate(rows, start=1):
                try:
                    if not isinstance(item, dict):
                        raise ValueError("row must be a JSON object")
                    question = item["question"]
                    answer = item.get("answer")
                    if not answer and item.get("candidate_answers"):
                        answer = item["candidate_answers"][0]["answer"]
                    if not answer:
                        raise ValueError("missing answer")

                    cursor.execute(
                        """
                        INSERT INTO qa_items (
                          external_id, technical_type_id, business_tags_json, application_id,
                          dataset_batch_id, question_text, context_text, metadata_json, tags_json,
                          difficulty, source, source_model, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                        """,
                        (
                            item.get("id"),
                            batch["technical_type_id"],
                            json.dumps(sorted(batch_business_tags), ensure_ascii=False),
                            batch["application_id"],
                            batch_id,
                            question,
                            item.get("context"),
                            json.dumps(item.get("metadata"), ensure_ascii=False)
                            if isinstance(item.get("metadata"), dict)
                            else None,
                            json.dumps(sorted(batch_business_tags), ensure_ascii=False),
                            item.get("difficulty"),
                            item.get("source"),
                            item.get("model"),
                            now_iso(),
                        ),
                    )
                    qa_item_id = int(cursor.lastrowid)
                    cursor.execute(
                        """
                        INSERT INTO qa_answers (
                          qa_item_id, answer_text, answer_type, source_model,
                          source_user_id, parent_answer_id, version_no, is_current, created_at
                        ) VALUES (?, ?, 'imported_candidate', ?, NULL, NULL, 1, 1, ?)
                        """,
                        (
                            qa_item_id,
                            answer,
                            item.get("model"),
                            now_iso(),
                        ),
                    )
                    success_count += 1
                except Exception as exc:
                    fail_count += 1
                    cursor.execute(
                        """
                        INSERT INTO dataset_batch_failures (
                          dataset_batch_id, row_no, external_id, question_preview,
                          error_message, raw_payload_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            batch_id,
                            index,
                            item.get("id") if isinstance(item, dict) else None,
                            (
                                str(item.get("question", ""))[:120]
                                if isinstance(item, dict)
                                else str(item)[:120]
                            ),
                            str(exc),
                            json.dumps(item, ensure_ascii=False)
                            if isinstance(item, (dict, list))
                            else json.dumps({"raw_value": item}, ensure_ascii=False),
                            now_iso(),
                        ),
                    )

            cursor.execute(
                """
                UPDATE dataset_batches
                SET import_status = 'parsed',
                    total_count = ?,
                    success_count = ?,
                    fail_count = ?
                WHERE id = ?
                """,
                (total_count, success_count, fail_count, batch_id),
            )
            if batch["uploader_user_id"] is not None and batch["self_review_status"] == "queued":
                create_self_review_tasks_for_batch(cursor, batch_id, int(batch["uploader_user_id"]))
                cursor.execute(
                    """
                    UPDATE dataset_batches
                    SET self_review_status = CASE WHEN success_count > 0 THEN 'pending' ELSE 'none' END
                    WHERE id = ?
                    """,
                    (batch_id,),
                )
            release_import_batch_lock(cursor, batch_id, lock_token)
            lock_token = None
    except Exception:
        if lock_token:
            with db_cursor() as cursor:
                mark_import_batch_failed(cursor, batch_id)
        raise


def dispatch_tasks(application_id: int, limit: int) -> None:
    with db_cursor() as cursor:
        experts = load_application_experts(cursor, application_id)
        if len(experts) < 2:
            return

        answers = cursor.execute(
            """
            SELECT ans.id, ans.qa_item_id, q.business_tags_json
            FROM qa_answers ans
            JOIN qa_items q ON q.id = ans.qa_item_id
            WHERE q.application_id = ?
              AND q.status IN ('active', 'in_review')
              AND ans.is_current = 1
            ORDER BY ans.id ASC
            LIMIT ?
            """,
            (application_id, limit),
        ).fetchall()

        for answer in answers:
            qa_business_tags = parse_business_tag_codes(answer["business_tags_json"])
            eligible_expert_ids = [
                expert_id
                for expert_id, expert in experts.items()
                if expert_can_review_business_tags(
                    qa_business_tags,
                    expert["allow_cross_business_review"],
                    expert["business_tags"],
                )
            ]
            if len(eligible_expert_ids) < 2:
                continue

            existing_expert_rows = cursor.execute(
                """
                SELECT expert_user_id
                FROM evaluation_tasks
                WHERE answer_id = ?
                  AND task_type = 'initial_review'
                ORDER BY expert_user_id ASC
                """,
                (answer["id"],),
            ).fetchall()
            abandoned_rows = cursor.execute(
                """
                SELECT expert_user_id
                FROM expert_task_abandons
                WHERE answer_id = ?
                  AND task_type = 'initial_review'
                ORDER BY expert_user_id ASC
                """,
                (answer["id"],),
            ).fetchall()
            existing_expert_ids = {row["expert_user_id"] for row in existing_expert_rows}
            existing_expert_ids.update(row["expert_user_id"] for row in abandoned_rows)
            existing = cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM evaluation_tasks
                WHERE answer_id = ?
                  AND task_type = 'initial_review'
                """,
                (answer["id"],),
            ).fetchone()
            if existing["count"] >= 2:
                continue

            assigned_count = existing["count"]
            for expert_id in eligible_expert_ids:
                if expert_id in existing_expert_ids:
                    continue
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO evaluation_tasks (
                      qa_item_id, answer_id, expert_user_id, round_no,
                      task_type, status, assigned_at
                    ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
                    """,
                    (answer["qa_item_id"], answer["id"], expert_id, now_iso()),
                )
                assigned_count += 1
                if assigned_count >= 2:
                    break
            cursor.execute(
                "UPDATE qa_items SET status = 'in_review' WHERE id = ?",
                (answer["qa_item_id"],),
            )


def parse_json_text(value: Optional[str], fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed
    except json.JSONDecodeError:
        return fallback


def apply_export_job_filters(
    query: str,
    params: list[object],
    export_job: dict,
    *,
    date_field_sql: str,
    qa_alias: str = "q",
    technical_type_field_sql: Optional[str] = None,
) -> tuple[str, list[object]]:
    if export_job["application_id"] is not None:
        query += f" AND {qa_alias}.application_id = ?"
        params.append(export_job["application_id"])

    technical_type_codes = parse_json_text(export_job.get("technical_type_codes_json"), [])
    if (
        technical_type_field_sql
        and isinstance(technical_type_codes, list)
        and technical_type_codes
        and all(isinstance(code, str) and code for code in technical_type_codes)
    ):
        query += f" AND {technical_type_field_sql} IN ({','.join('?' for _ in technical_type_codes)})"
        params.extend(technical_type_codes)

    if export_job["date_from"]:
        query += f" AND date({date_field_sql}) >= date(?)"
        params.append(export_job["date_from"])
    if export_job["date_to"]:
        query += f" AND date({date_field_sql}) <= date(?)"
        params.append(export_job["date_to"])

    return query, params


def score_to_value(score: str, mapping: Dict[str, float]) -> Optional[float]:
    return mapping.get(score)


def pick_majority_value(values: list[object]) -> tuple[Optional[object], int]:
    if not values:
        return None, 0
    counts = Counter(values)
    top_value, top_count = counts.most_common(1)[0]
    return top_value, top_count


def resolve_final_decision(records: list[dict]) -> tuple[str, float]:
    decisions = [record["overall_decision"] for record in records]
    winning_decision, winning_count = pick_majority_value(decisions)
    agreement_score = winning_count / len(records) if records else 0.0

    if len(records) == 2:
        if winning_count == 2 and winning_decision is not None:
            return str(winning_decision), agreement_score
        return "pending", agreement_score

    if len(records) >= 3:
        if winning_count >= 2 and winning_decision is not None:
            return str(winning_decision), agreement_score
        return "pending", agreement_score

    return "pending", agreement_score


def resolve_rewrite_answer_id(records: list[dict]) -> Optional[int]:
    rewrite_records = [
        int(record["adopted_rewrite_answer_id"])
        for record in records
        if record["overall_decision"] == "rewrite"
        and record["adopted_rewrite_answer_id"] is not None
    ]
    if not rewrite_records:
        return None

    winning_answer_id, winning_count = pick_majority_value(rewrite_records)
    if winning_answer_id is None:
        return None
    if winning_count > len(rewrite_records) / 2:
        return int(winning_answer_id)
    return None


def aggregate_answer(qa_item_id: int, answer_id: int) -> None:
    with db_cursor() as cursor:
        records = cursor.execute(
            """
            SELECT *
            FROM evaluation_records
            WHERE qa_item_id = ? AND answer_id = ?
            ORDER BY id ASC
            """,
            (qa_item_id, answer_id),
        ).fetchall()
        if len(records) < 2:
            return

        correctness_map = {"good": 1.0, "medium": 0.5, "bad": 0.0}
        completeness_map = {"full": 1.0, "partial": 0.5, "missing": 0.0}
        relevance_map = {"relevant": 1.0, "partial": 0.5, "offtopic": 0.0}
        clarity_map = {"clear": 1.0, "normal": 0.5, "unclear": 0.0}

        final_decision, agreement_score = resolve_final_decision(records)
        current_answer_id = answer_id
        if final_decision == "rewrite":
            rewrite_answer_id = resolve_rewrite_answer_id(records)
            if rewrite_answer_id is not None:
                current_answer_id = rewrite_answer_id

        avg_correctness = sum(
            score_to_value(record["correctness_rating"], correctness_map) or 0 for record in records
        ) / len(records)
        avg_completeness = sum(
            score_to_value(record["completeness_rating"], completeness_map) or 0 for record in records
        ) / len(records)
        avg_relevance = sum(
            score_to_value(record["relevance_rating"], relevance_map) or 0 for record in records
        ) / len(records)
        avg_clarity = sum(
            score_to_value(record["clarity_rating"], clarity_map) or 0 for record in records
        ) / len(records)

        if final_decision == "pending" and len(records) == 2:
            qa_item = cursor.execute(
                """
                SELECT application_id, business_tags_json
                FROM qa_items
                WHERE id = ?
                """,
                (qa_item_id,),
            ).fetchone()
            assigned_experts = cursor.execute(
                """
                SELECT expert_user_id
                FROM evaluation_tasks
                WHERE answer_id = ?
                """,
                (answer_id,),
            ).fetchall()
            excluded_expert_ids = {row["expert_user_id"] for row in assigned_experts}
            third_expert_id = None
            if qa_item:
                qa_business_tags = parse_business_tag_codes(qa_item["business_tags_json"])
                experts = load_application_experts(cursor, qa_item["application_id"])
                for expert_id, expert in experts.items():
                    if expert_id in excluded_expert_ids:
                        continue
                    if expert_can_review_business_tags(
                        qa_business_tags,
                        expert["allow_cross_business_review"],
                        expert["business_tags"],
                    ):
                        third_expert_id = expert_id
                        break
            if third_expert_id is not None:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO evaluation_tasks (
                      qa_item_id, answer_id, expert_user_id, round_no,
                      task_type, status, assigned_at
                    ) VALUES (?, ?, ?, 2, 'dispute_review', 'pending', ?)
                    """,
                    (qa_item_id, answer_id, third_expert_id, now_iso()),
                )

        cursor.execute(
            """
            INSERT INTO qa_aggregates (
              qa_item_id, current_answer_id, review_count,
              avg_correctness, avg_completeness, avg_relevance, avg_clarity,
              agreement_score, final_decision, aggregated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(qa_item_id) DO UPDATE SET
              current_answer_id = excluded.current_answer_id,
              review_count = excluded.review_count,
              avg_correctness = excluded.avg_correctness,
              avg_completeness = excluded.avg_completeness,
              avg_relevance = excluded.avg_relevance,
              avg_clarity = excluded.avg_clarity,
              agreement_score = excluded.agreement_score,
              final_decision = excluded.final_decision,
              aggregated_at = excluded.aggregated_at
            """,
            (
                qa_item_id,
                current_answer_id,
                len(records),
                avg_correctness,
                avg_completeness,
                avg_relevance,
                avg_clarity,
                agreement_score,
                final_decision,
                now_iso(),
            ),
        )
        if final_decision != "pending":
            cursor.execute(
                "UPDATE qa_items SET status = 'reviewed' WHERE id = ?",
                (qa_item_id,),
            )
        else:
            cursor.execute(
                "UPDATE qa_items SET status = 'in_review' WHERE id = ?",
                (qa_item_id,),
            )


def build_final_dataset_rows(export_job: dict) -> list[dict]:
    query = """
        SELECT
          q.id AS qa_item_id,
          q.external_id,
          q.question_text,
          q.context_text,
          q.tags_json,
          q.difficulty,
          q.source,
          q.created_at,
          a.id AS application_id,
          a.name AS application_name,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          agg.review_count,
          agg.agreement_score,
          agg.final_decision,
          agg.aggregated_at,
          final_answer.id AS final_answer_id,
          final_answer.answer_text AS final_answer_text,
          final_answer.answer_type AS final_answer_type,
          final_answer.source_model AS final_answer_source_model
        FROM qa_items q
        JOIN applications a ON a.id = q.application_id
        LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
        JOIN qa_aggregates agg ON agg.qa_item_id = q.id
        LEFT JOIN qa_answers final_answer
          ON final_answer.id = COALESCE(agg.final_standard_answer_id, agg.current_answer_id)
        WHERE agg.final_decision IN ('pass', 'rewrite', 'fail')
    """
    params: list[object] = []
    query, params = apply_export_job_filters(
        query,
        params,
        export_job,
        date_field_sql="agg.aggregated_at",
        technical_type_field_sql="tt.code",
    )
    query += " ORDER BY agg.aggregated_at DESC, q.id DESC"

    with db_cursor() as cursor:
        rows = cursor.execute(query, tuple(params)).fetchall()

    return [
        {
            "qa_item_id": row["qa_item_id"],
            "external_id": row["external_id"],
            "application": {
                "id": row["application_id"],
                "name": row["application_name"],
            },
            "technical_type": {
                "code": row["technical_type_code"],
                "name": row["technical_type_name"],
            },
            "question": row["question_text"],
            "context": row["context_text"],
            "tags": parse_json_text(row["tags_json"], []),
            "difficulty": row["difficulty"],
            "source": row["source"],
            "created_at": row["created_at"],
            "review": {
                "review_count": row["review_count"],
                "agreement_score": row["agreement_score"],
                "final_decision": row["final_decision"],
                "aggregated_at": row["aggregated_at"],
            },
            "final_answer": {
                "id": row["final_answer_id"],
                "text": row["final_answer_text"],
                "type": row["final_answer_type"],
                "source_model": row["final_answer_source_model"],
            },
        }
        for row in rows
    ]


def build_review_record_rows(export_job: dict) -> list[dict]:
    query = """
        SELECT
          r.id AS record_id,
          r.task_id,
          r.qa_item_id,
          q.external_id,
          q.question_text,
          a.id AS application_id,
          a.name AS application_name,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          ans.id AS answer_id,
          ans.answer_text,
          u.id AS expert_user_id,
          u.full_name AS expert_name,
          r.correctness_rating,
          r.completeness_rating,
          r.relevance_rating,
          r.clarity_rating,
          r.risk_flag,
          r.overall_decision,
          r.quick_comment_codes,
          adopted.id AS adopted_rewrite_answer_id,
          adopted.answer_text AS adopted_rewrite_answer_text,
          r.created_at
        FROM evaluation_records r
        JOIN qa_items q ON q.id = r.qa_item_id
        JOIN applications a ON a.id = q.application_id
        LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
        JOIN qa_answers ans ON ans.id = r.answer_id
        JOIN users u ON u.id = r.expert_user_id
        LEFT JOIN qa_answers adopted ON adopted.id = r.adopted_rewrite_answer_id
        WHERE 1 = 1
    """
    params: list[object] = []
    query, params = apply_export_job_filters(
        query,
        params,
        export_job,
        date_field_sql="r.created_at",
        technical_type_field_sql="tt.code",
    )
    query += " ORDER BY r.created_at DESC, r.id DESC"

    with db_cursor() as cursor:
        rows = cursor.execute(query, tuple(params)).fetchall()

    return [
        {
            "record_id": row["record_id"],
            "task_id": row["task_id"],
            "qa_item_id": row["qa_item_id"],
            "external_id": row["external_id"],
            "application": {
                "id": row["application_id"],
                "name": row["application_name"],
            },
            "technical_type": {
                "code": row["technical_type_code"],
                "name": row["technical_type_name"],
            },
            "question": row["question_text"],
            "answer": {
                "id": row["answer_id"],
                "text": row["answer_text"],
            },
            "expert": {
                "id": row["expert_user_id"],
                "name": row["expert_name"],
            },
            "evaluation": {
                "correctness_rating": row["correctness_rating"],
                "completeness_rating": row["completeness_rating"],
                "relevance_rating": row["relevance_rating"],
                "clarity_rating": row["clarity_rating"],
                "risk_flag": row["risk_flag"],
                "overall_decision": row["overall_decision"],
                "quick_comment_codes": parse_json_text(row["quick_comment_codes"], []),
            },
            "adopted_rewrite_answer": (
                {
                    "id": row["adopted_rewrite_answer_id"],
                    "text": row["adopted_rewrite_answer_text"],
                }
                if row["adopted_rewrite_answer_id"] is not None
                else None
            ),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def build_disputed_case_rows(export_job: dict) -> list[dict]:
    query = """
        SELECT DISTINCT
          q.id AS qa_item_id,
          q.external_id,
          q.question_text,
          a.id AS application_id,
          a.name AS application_name,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          agg.review_count,
          agg.agreement_score,
          agg.final_decision,
          agg.aggregated_at,
          answer.id AS answer_id,
          answer.answer_text
        FROM qa_items q
        JOIN applications a ON a.id = q.application_id
        LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
        JOIN evaluation_tasks t ON t.qa_item_id = q.id AND t.task_type = 'dispute_review'
        LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
        LEFT JOIN qa_answers answer
          ON answer.id = COALESCE(agg.current_answer_id, t.answer_id)
        WHERE 1 = 1
    """
    params: list[object] = []
    query, params = apply_export_job_filters(
        query,
        params,
        export_job,
        date_field_sql="COALESCE(agg.aggregated_at, t.assigned_at)",
        technical_type_field_sql="tt.code",
    )
    query += " ORDER BY COALESCE(agg.aggregated_at, t.assigned_at) DESC, q.id DESC"

    with db_cursor() as cursor:
        rows = cursor.execute(query, tuple(params)).fetchall()

    return [
        {
            "qa_item_id": row["qa_item_id"],
            "external_id": row["external_id"],
            "application": {
                "id": row["application_id"],
                "name": row["application_name"],
            },
            "technical_type": {
                "code": row["technical_type_code"],
                "name": row["technical_type_name"],
            },
            "question": row["question_text"],
            "current_answer": {
                "id": row["answer_id"],
                "text": row["answer_text"],
            },
            "review": {
                "review_count": row["review_count"],
                "agreement_score": row["agreement_score"],
                "final_decision": row["final_decision"],
                "aggregated_at": row["aggregated_at"],
            },
        }
        for row in rows
    ]


def clean_sft_text(value: Optional[str]) -> str:
    if not value:
        return ""
    lines = [line.rstrip() for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    collapsed: list[str] = []
    blank_pending = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if collapsed and not blank_pending:
                collapsed.append("")
                blank_pending = True
            continue
        collapsed.append(stripped if not line.startswith(" ") else line.strip())
        blank_pending = False
    return "\n".join(collapsed).strip()


def build_sft_user_content(question_text: Optional[str], context_text: Optional[str]) -> str:
    question = clean_sft_text(question_text)
    context = clean_sft_text(context_text)
    if context:
        return f"{question}\n\n补充背景：\n{context}"
    return question


def build_sft_dataset_rows(export_job: dict) -> list[dict]:
    query = """
        SELECT
          q.id AS qa_item_id,
          q.external_id,
          q.question_text,
          q.context_text,
          q.difficulty,
          q.source,
          q.created_at,
          q.status,
          a.id AS application_id,
          a.name AS application_name,
          tt.code AS technical_type_code,
          tt.name AS technical_type_name,
          agg.final_decision,
          agg.aggregated_at,
          final_answer.id AS final_answer_id,
          final_answer.answer_text AS final_answer_text,
          final_answer.answer_type AS final_answer_type,
          final_answer.source_model AS final_answer_source_model,
          current_answer.id AS current_answer_id,
          current_answer.answer_text AS current_answer_text,
          current_answer.answer_type AS current_answer_type,
          current_answer.source_model AS current_answer_source_model,
          current_live.id AS current_live_answer_id,
          current_live.answer_text AS current_live_answer_text,
          current_live.answer_type AS current_live_answer_type,
          current_live.source_model AS current_live_answer_source_model
        FROM qa_items q
        JOIN applications a ON a.id = q.application_id
        LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
        LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
        LEFT JOIN qa_answers final_answer
          ON final_answer.id = COALESCE(agg.final_standard_answer_id, agg.current_answer_id)
        LEFT JOIN qa_answers current_answer
          ON current_answer.id = agg.current_answer_id
        LEFT JOIN qa_answers current_live
          ON current_live.qa_item_id = q.id AND current_live.is_current = 1
        WHERE 1 = 1
    """
    params: list[object] = []
    query, params = apply_export_job_filters(
        query,
        params,
        export_job,
        date_field_sql="COALESCE(agg.aggregated_at, q.created_at)",
        technical_type_field_sql="tt.code",
    )
    query += " ORDER BY COALESCE(agg.aggregated_at, q.created_at) DESC, q.id DESC"

    with db_cursor() as cursor:
        rows = cursor.execute(query, tuple(params)).fetchall()

    exported_rows: list[dict] = []
    for row in rows:
        answer_text = clean_sft_text(
            row["final_answer_text"]
            or row["current_answer_text"]
            or row["current_live_answer_text"]
        )
        question_text = clean_sft_text(row["question_text"])
        if not question_text or not answer_text:
            continue
        user_content = build_sft_user_content(row["question_text"], row["context_text"])
        answer_source = (
            "reviewed_final"
            if row["final_answer_text"]
            else ("aggregate_current" if row["current_answer_text"] else "live_current")
        )
        exported_rows.append(
            {
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": answer_text},
                ],
                "metadata": {
                    "qa_item_id": row["qa_item_id"],
                    "external_id": row["external_id"],
                    "application": {
                        "id": row["application_id"],
                        "name": row["application_name"],
                    },
                    "technical_type": {
                        "code": row["technical_type_code"],
                        "name": row["technical_type_name"],
                    },
                    "difficulty": row["difficulty"],
                    "source": row["source"],
                    "status": row["status"],
                    "answer_source": answer_source,
                    "final_decision": row["final_decision"],
                    "answer_type": (
                        row["final_answer_type"]
                        or row["current_answer_type"]
                        or row["current_live_answer_type"]
                    ),
                    "source_model": (
                        row["final_answer_source_model"]
                        or row["current_answer_source_model"]
                        or row["current_live_answer_source_model"]
                    ),
                    "created_at": row["created_at"],
                    "aggregated_at": row["aggregated_at"],
                },
            }
        )
    return exported_rows


def write_export_file(path: Path, file_format: str, rows: list[dict]) -> None:
    if file_format == "json":
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def export_dataset(export_job_id: int) -> None:
    with db_cursor() as cursor:
        export_job = cursor.execute(
            """
            SELECT ej.*, a.name AS application_name
            FROM export_jobs ej
            LEFT JOIN applications a ON a.id = ej.application_id
            WHERE ej.id = ?
            """,
            (export_job_id,),
        ).fetchone()
        if not export_job:
            raise ValueError(f"export job {export_job_id} not found")
        cursor.execute(
            """
            UPDATE export_jobs
            SET status = 'processing',
                started_at = ?,
                error_message = NULL
            WHERE id = ?
            """,
            (now_iso(), export_job_id),
        )

    export_record = dict(export_job)
    export_type = export_record["export_type"]
    if export_type == "final_dataset":
        rows = build_final_dataset_rows(export_record)
    elif export_type == "review_records":
        rows = build_review_record_rows(export_record)
    elif export_type == "disputed_cases":
        rows = build_disputed_case_rows(export_record)
    elif export_type == "sft_dataset":
        rows = build_sft_dataset_rows(export_record)
    else:
        raise ValueError(f"unsupported export type: {export_type}")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"export_{export_job_id}_{export_type}_{timestamp}.{export_record['file_format']}"
    file_path = EXPORT_DIR / filename
    previous_file_path = Path(export_record["file_path"]) if export_record.get("file_path") else None
    if previous_file_path and previous_file_path.exists():
        previous_file_path.unlink()
    write_export_file(file_path, export_record["file_format"], rows)

    with db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE export_jobs
            SET status = 'done',
                file_path = ?,
                total_records = ?,
                file_size_bytes = ?,
                completed_at = ?,
                error_message = NULL
            WHERE id = ?
            """,
            (
                str(file_path),
                len(rows),
                file_path.stat().st_size,
                now_iso(),
                export_job_id,
            ),
        )


def handle_llm(
    task_id: int,
    session_id: int,
    action: str,
    prompt: Optional[str],
    mode: Optional[str],
    target_answer_id: Optional[int],
    score_context: Optional[dict],
) -> None:
    with db_cursor() as cursor:
        task = cursor.execute(
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
        if not task:
            raise ValueError(f"task {task_id} not found")
        selected_answer_id = target_answer_id or task["answer_id"]
        selected_answer = cursor.execute(
            """
            SELECT id, answer_text, version_no
            FROM qa_answers
            WHERE id = ? AND qa_item_id = ?
            """,
            (selected_answer_id, task["qa_item_id"]),
        ).fetchone()
        if not selected_answer:
            raise ValueError(f"answer {selected_answer_id} not found for task {task_id}")
        conversation_history = cursor.execute(
            """
            SELECT role, content
            FROM llm_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        session = cursor.execute(
            """
            SELECT llm_config_id
            FROM llm_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

        if session and session["llm_config_id"] is not None:
            llm_config = cursor.execute(
                """
                SELECT
                  id, name, provider_type, base_url, api_key, model_name,
                  system_prompt, temperature, is_enabled
                FROM llm_configs
                WHERE id = ?
                LIMIT 1
                """,
                (int(session["llm_config_id"]),),
            ).fetchone()
        else:
            llm_config = cursor.execute(
                """
                SELECT
                  id, name, provider_type, base_url, api_key, model_name,
                  system_prompt, temperature, is_enabled
                FROM llm_configs
                WHERE is_active = 1
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if not llm_config:
            raise LlmClientError("no active llm config")
        if not bool(llm_config["is_enabled"]):
            raise LlmClientError("selected llm config is disabled")
        api_key = get_llm_api_key(int(llm_config["id"]), llm_config["api_key"])
        if not api_key:
            raise LlmClientError("selected llm config missing api key in local secrets")

        messages = build_task_messages(
            action=action,
            question_text=task["question_text"],
            context_text=task["context_text"],
            answer_text=selected_answer["answer_text"],
            technical_type_code=task["technical_type_code"],
            score_context=score_context,
            conversation_history=[dict(row) for row in conversation_history],
            system_prompt=llm_config["system_prompt"],
        )

        if llm_config["provider_type"] != "openai_compatible":
            raise LlmClientError(f"unsupported provider: {llm_config['provider_type']}")

        assistant_text = call_openai_compatible_chat(
            base_url=llm_config["base_url"],
            api_key=api_key,
            model_name=llm_config["model_name"],
            messages=messages,
            temperature=float(llm_config["temperature"]),
        )

        review = parse_review_response(assistant_text)
        candidate_answer_id = None
        revised_answer = review["revised_answer"]
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
                    selected_answer["id"],
                    int(selected_answer["version_no"] or 1) + 1,
                    now_iso(),
                ),
            )
            candidate_answer_id = int(cursor.lastrowid)
        answer_note = format_review_message(review, candidate_answer_id)
        cursor.execute(
            """
            INSERT INTO llm_messages (
              session_id, role, content, target_answer_id, generated_answer_id, review_json, created_at
            )
            VALUES (?, 'assistant', ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                answer_note,
                selected_answer["id"],
                candidate_answer_id,
                json.dumps(review, ensure_ascii=False),
                now_iso(),
            ),
        )
        cursor.execute(
            "UPDATE llm_sessions SET status = 'completed' WHERE id = ?",
            (session_id,),
        )


def process_job(job_path: Path) -> None:
    processing_path = move_job(job_path, "processing")
    job = None
    payload = {}
    job_type = "unknown"
    started_at = now_iso()
    started_monotonic = time.perf_counter()
    try:
        job = load_json(processing_path)
        payload = job.get("payload", {})
        job_type = job["type"]
        meta = job.setdefault("meta", {})
        meta.setdefault("created_at", started_at)
        meta.setdefault("retry_count", 0)
        meta["started_at"] = started_at
        meta["completed_at"] = None
        meta["duration_ms"] = None
        meta["last_error"] = None
        save_json(processing_path, job)
        if job_type == "import":
            import_batch(int(payload["batch_id"]))
        elif job_type == "dispatch":
            dispatch_tasks(int(payload["application_id"]), int(payload.get("limit", 100)))
        elif job_type == "aggregate":
            aggregate_answer(int(payload["qa_item_id"]), int(payload["answer_id"]))
        elif job_type == "llm":
            handle_llm(
                int(payload["task_id"]),
                int(payload["session_id"]),
                str(payload.get("action", "compare")),
                payload.get("prompt"),
                payload.get("mode"),
                payload.get("target_answer_id"),
                payload.get("score_context"),
            )
        elif job_type == "export":
            export_dataset(int(payload["export_job_id"]))
        completed_at = now_iso()
        meta["completed_at"] = completed_at
        meta["duration_ms"] = int((time.perf_counter() - started_monotonic) * 1000)
        save_json(processing_path, job)
        move_job(processing_path, "done")
    except Exception as exc:
        failed_at = now_iso()
        if job is not None:
            meta = job.setdefault("meta", {})
            meta.setdefault("created_at", started_at)
            meta.setdefault("retry_count", 0)
            meta["started_at"] = meta.get("started_at") or started_at
            meta["completed_at"] = failed_at
            meta["duration_ms"] = int((time.perf_counter() - started_monotonic) * 1000)
            meta["last_error"] = str(exc)
            save_json(processing_path, job)
        failed_path = move_job(processing_path, "failed")
        failed_log = failed_path.with_suffix(".error.txt")
        failed_log.write_text(str(exc), encoding="utf-8")
        if job_type == "llm" and payload.get("session_id") is not None:
            with db_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE llm_sessions
                    SET status = 'failed'
                    WHERE id = ?
                    """,
                    (int(payload["session_id"]),),
                )
                cursor.execute(
                    """
                    INSERT INTO llm_messages (
                      session_id, role, content, target_answer_id, created_at
                    )
                    VALUES (?, 'assistant', ?, ?, ?)
                    """,
                    (
                        int(payload["session_id"]),
                        f"LLM 调用失败：{str(exc)}",
                        payload.get("target_answer_id"),
                        now_iso(),
                    ),
                )
        if job_type == "export" and payload.get("export_job_id") is not None:
            with db_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE export_jobs
                    SET status = 'failed',
                        completed_at = ?,
                        error_message = ?
                    WHERE id = ?
                    """,
                    (now_iso(), str(exc), int(payload["export_job_id"])),
                )


def run_worker(once: bool, interval: float) -> None:
    init_db()
    for folder in ("pending", "processing", "done", "failed"):
        (QUEUE_DIR / folder).mkdir(parents=True, exist_ok=True)

    while True:
        job = get_next_job()
        if job is None:
            if once:
                return
            time.sleep(interval)
            continue
        process_job(job)
        if once:
            return


def main() -> None:
    parser = ArgumentParser(description="Run the file queue worker")
    parser.add_argument("--once", action="store_true", help="Process one job and exit")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    args = parser.parse_args()
    run_worker(once=args.once, interval=args.interval)


if __name__ == "__main__":
    main()
