from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import db_cursor, init_db


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def ensure_column(cursor, table_name: str, ddl: str, column_name: str) -> None:
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def ensure_technical_type(cursor, code: str, name: str, description: str, sort_order: int) -> int:
    existing = cursor.execute(
        "SELECT id FROM technical_types WHERE code = ?",
        (code,),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE technical_types
            SET name = ?, description = ?, is_active = 1, sort_order = ?
            WHERE id = ?
            """,
            (name, description, sort_order, existing["id"]),
        )
        return existing["id"]

    cursor.execute(
        """
        INSERT INTO technical_types (code, name, description, is_active, sort_order, created_at)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (code, name, description, sort_order, now_iso()),
    )
    return int(cursor.lastrowid)


if __name__ == "__main__":
    init_db()
    with db_cursor() as cursor:
        ensure_column(cursor, "qa_items", "technical_type_id INTEGER", "technical_type_id")
        ensure_column(cursor, "qa_items", "business_tags_json TEXT", "business_tags_json")
        ensure_column(
            cursor,
            "evaluation_records",
            "reasoning_completeness TEXT CHECK(reasoning_completeness IN ('strong', 'medium', 'weak'))",
            "reasoning_completeness",
        )
        ensure_column(
            cursor,
            "evaluation_records",
            "reasoning_consistency TEXT CHECK(reasoning_consistency IN ('strong', 'medium', 'weak'))",
            "reasoning_consistency",
        )
        ensure_column(
            cursor,
            "evaluation_records",
            "reasoning_support TEXT CHECK(reasoning_support IN ('strong', 'medium', 'weak'))",
            "reasoning_support",
        )

        direct_qa_id = ensure_technical_type(
            cursor, "direct_qa", "普通问答", "直接回答型 QA", 10
        )
        ensure_technical_type(
            cursor, "cot_qa", "长思维链问答", "带推理过程的 QA", 20
        )

        cursor.execute(
            """
            UPDATE qa_items
            SET technical_type_id = COALESCE(technical_type_id, ?),
                business_tags_json = COALESCE(business_tags_json, tags_json, '[]')
            """,
            (direct_qa_id,),
        )

    print("taxonomy migration completed")
