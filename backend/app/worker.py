from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil
import time
from typing import Dict, Optional

from .config import EXPORT_DIR, QUEUE_DIR
from .db import db_cursor, init_db


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def ensure_application(cursor, name: str) -> int:
    row = cursor.execute(
        "SELECT id FROM applications WHERE name = ?",
        (name,),
    ).fetchone()
    if row:
        return row["id"]
    cursor.execute(
        """
        INSERT INTO applications (name, description, is_active, created_at)
        VALUES (?, '', 1, ?)
        """,
        (name, now_iso()),
    )
    return int(cursor.lastrowid)


def import_batch(batch_id: int) -> None:
    with db_cursor() as cursor:
        batch = cursor.execute(
            "SELECT id, file_path FROM dataset_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if not batch:
            raise ValueError(f"batch {batch_id} not found")
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
                application_name = item["application"]
                technical_type_code = item["technical_type"]
                business_tags = item.get("business_tags", [])
                question = item["question"]
                answer = item.get("answer")
                if not answer and item.get("candidate_answers"):
                    answer = item["candidate_answers"][0]["answer"]
                if not answer:
                    raise ValueError("missing answer")
                if not isinstance(business_tags, list):
                    raise ValueError("business_tags must be an array")

                application_id = ensure_application(cursor, application_name)
                technical_type = cursor.execute(
                    """
                    SELECT id
                    FROM technical_types
                    WHERE code = ? AND is_active = 1
                    """,
                    (technical_type_code,),
                ).fetchone()
                if not technical_type:
                    raise ValueError(f"technical_type not found: {technical_type_code}")

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
                        raise ValueError(f"business_tag not found: {missing_codes[0]}")

                cursor.execute(
                    """
                    INSERT INTO qa_items (
                      external_id, technical_type_id, business_tags_json, application_id,
                      dataset_batch_id, question_text, context_text, tags_json,
                      difficulty, source, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                    """,
                    (
                        item.get("id"),
                        technical_type["id"],
                        json.dumps(business_tags, ensure_ascii=False),
                        application_id,
                        batch_id,
                        question,
                        item.get("context"),
                        json.dumps(business_tags, ensure_ascii=False),
                        item.get("difficulty"),
                        item.get("source"),
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


def dispatch_tasks(application_id: int, limit: int) -> None:
    with db_cursor() as cursor:
        experts = cursor.execute(
            """
            SELECT DISTINCT u.id
            FROM users u
            JOIN expert_applications ea ON ea.expert_user_id = u.id
            WHERE u.role = 'expert'
              AND u.status = 'approved'
              AND ea.application_id = ?
            ORDER BY u.id ASC
            """,
            (application_id,),
        ).fetchall()
        expert_ids = [row["id"] for row in experts]
        if len(expert_ids) < 2:
            return

        answers = cursor.execute(
            """
            SELECT ans.id, ans.qa_item_id
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

            for expert_id in expert_ids[:2]:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO evaluation_tasks (
                      qa_item_id, answer_id, expert_user_id, round_no,
                      task_type, status, assigned_at
                    ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
                    """,
                    (answer["qa_item_id"], answer["id"], expert_id, now_iso()),
                )
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
            third_expert = cursor.execute(
                """
                SELECT DISTINCT u.id
                FROM users u
                JOIN expert_applications ea ON ea.expert_user_id = u.id
                JOIN qa_items q ON q.application_id = ea.application_id
                WHERE q.id = ?
                  AND u.role = 'expert'
                  AND u.status = 'approved'
                  AND u.id NOT IN (
                    SELECT expert_user_id
                    FROM evaluation_tasks
                    WHERE answer_id = ?
                  )
                ORDER BY u.id ASC
                LIMIT 1
                """,
                (qa_item_id, answer_id),
            ).fetchone()
            if third_expert:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO evaluation_tasks (
                      qa_item_id, answer_id, expert_user_id, round_no,
                      task_type, status, assigned_at
                    ) VALUES (?, ?, ?, 2, 'dispute_review', 'pending', ?)
                    """,
                    (qa_item_id, answer_id, third_expert["id"], now_iso()),
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
        JOIN qa_aggregates agg ON agg.qa_item_id = q.id
        LEFT JOIN qa_answers final_answer
          ON final_answer.id = COALESCE(agg.final_standard_answer_id, agg.current_answer_id)
        WHERE agg.final_decision IN ('pass', 'rewrite', 'fail')
    """
    params: list[object] = []
    if export_job["application_id"] is not None:
        query += " AND q.application_id = ?"
        params.append(export_job["application_id"])
    if export_job["date_from"]:
        query += " AND date(agg.aggregated_at) >= date(?)"
        params.append(export_job["date_from"])
    if export_job["date_to"]:
        query += " AND date(agg.aggregated_at) <= date(?)"
        params.append(export_job["date_to"])
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
        JOIN qa_answers ans ON ans.id = r.answer_id
        JOIN users u ON u.id = r.expert_user_id
        LEFT JOIN qa_answers adopted ON adopted.id = r.adopted_rewrite_answer_id
        WHERE 1 = 1
    """
    params: list[object] = []
    if export_job["application_id"] is not None:
        query += " AND q.application_id = ?"
        params.append(export_job["application_id"])
    if export_job["date_from"]:
        query += " AND date(r.created_at) >= date(?)"
        params.append(export_job["date_from"])
    if export_job["date_to"]:
        query += " AND date(r.created_at) <= date(?)"
        params.append(export_job["date_to"])
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
          agg.review_count,
          agg.agreement_score,
          agg.final_decision,
          agg.aggregated_at,
          answer.id AS answer_id,
          answer.answer_text
        FROM qa_items q
        JOIN applications a ON a.id = q.application_id
        JOIN evaluation_tasks t ON t.qa_item_id = q.id AND t.task_type = 'dispute_review'
        LEFT JOIN qa_aggregates agg ON agg.qa_item_id = q.id
        LEFT JOIN qa_answers answer
          ON answer.id = COALESCE(agg.current_answer_id, t.answer_id)
        WHERE 1 = 1
    """
    params: list[object] = []
    if export_job["application_id"] is not None:
        query += " AND q.application_id = ?"
        params.append(export_job["application_id"])
    if export_job["date_from"]:
        query += " AND date(COALESCE(agg.aggregated_at, t.assigned_at)) >= date(?)"
        params.append(export_job["date_from"])
    if export_job["date_to"]:
        query += " AND date(COALESCE(agg.aggregated_at, t.assigned_at)) <= date(?)"
        params.append(export_job["date_to"])
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
    else:
        raise ValueError(f"unsupported export type: {export_type}")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"export_{export_job_id}_{export_type}_{timestamp}.{export_record['file_format']}"
    file_path = EXPORT_DIR / filename
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
) -> None:
    with db_cursor() as cursor:
        task = cursor.execute(
            """
            SELECT t.id, t.qa_item_id, t.answer_id, q.question_text, ans.answer_text
            FROM evaluation_tasks t
            JOIN qa_items q ON q.id = t.qa_item_id
            JOIN qa_answers ans ON ans.id = t.answer_id
            WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
        if not task:
            raise ValueError(f"task {task_id} not found")

        if action == "rewrite":
            candidate_text = (
                "建议采用更完整、更保守的标准答案："
                f"{task['answer_text']} 请结合发病初期处理、环境管理和规范用药给出答复。"
            )
            cursor.execute(
                """
                INSERT INTO qa_answers (
                  qa_item_id, answer_text, answer_type, source_model,
                  source_user_id, parent_answer_id, version_no, is_current, created_at
                ) VALUES (?, ?, 'llm_generated_candidate', 'demo-llm', NULL, ?, 2, 0, ?)
                """,
                (
                    task["qa_item_id"],
                    candidate_text,
                    task["answer_id"],
                    now_iso(),
                ),
            )
            answer_note = "已生成 1 条候选标准答案，可由专家确认。"
        else:
            answer_note = (
                f"LLM {action} 结果：问题“{task['question_text']}”的当前答案建议结合用户提示继续核查。"
            )
        cursor.execute(
            """
            INSERT INTO llm_messages (session_id, role, content, created_at)
            VALUES (?, 'assistant', ?, ?)
            """,
            (
                session_id,
                f"{answer_note} mode={mode or '-'} prompt={prompt or '-'}",
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
