import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DB_PATH, SCHEMA_PATH


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_parent_dir(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not table_exists(conn, table_name):
        return False
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def ensure_column(conn: sqlite3.Connection, table_name: str, ddl: str, column_name: str) -> None:
    if table_exists(conn, table_name) and not column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def apply_legacy_migrations(conn: sqlite3.Connection) -> None:
    # Keep startup compatible with older local SQLite files before running schema.sql.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS technical_types (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL UNIQUE,
          description TEXT,
          is_active INTEGER NOT NULL DEFAULT 1,
          sort_order INTEGER NOT NULL DEFAULT 100,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tags (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL UNIQUE,
          description TEXT,
          is_active INTEGER NOT NULL DEFAULT 1,
          sort_order INTEGER NOT NULL DEFAULT 100,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_configs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          llm_use_case TEXT NOT NULL DEFAULT 'evaluation' CHECK(llm_use_case IN ('evaluation', 'trial')),
          provider_code TEXT NOT NULL DEFAULT 'custom_openai',
          provider_type TEXT NOT NULL CHECK(provider_type IN ('openai_compatible')),
          base_url TEXT NOT NULL,
          api_key TEXT NOT NULL,
          model_name TEXT NOT NULL,
          system_prompt TEXT,
          temperature REAL NOT NULL DEFAULT 0.2,
          is_enabled INTEGER NOT NULL DEFAULT 1,
          is_active INTEGER NOT NULL DEFAULT 0,
          last_tested_at TEXT,
          last_test_status TEXT CHECK(last_test_status IN ('passed', 'failed')),
          last_test_message TEXT,
          last_test_latency_ms INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expert_business_tags (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          expert_user_id INTEGER NOT NULL,
          business_tag_id INTEGER NOT NULL,
          priority INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          UNIQUE(expert_user_id, business_tag_id),
          FOREIGN KEY (expert_user_id) REFERENCES users(id),
          FOREIGN KEY (business_tag_id) REFERENCES business_tags(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expert_task_abandons (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          qa_item_id INTEGER NOT NULL,
          answer_id INTEGER NOT NULL,
          expert_user_id INTEGER NOT NULL,
          task_type TEXT NOT NULL CHECK(task_type IN ('initial_review', 'dispute_review', 'final_confirm')),
          created_at TEXT NOT NULL,
          UNIQUE(answer_id, expert_user_id, task_type),
          FOREIGN KEY (qa_item_id) REFERENCES qa_items(id),
          FOREIGN KEY (answer_id) REFERENCES qa_answers(id),
          FOREIGN KEY (expert_user_id) REFERENCES users(id)
        )
        """
    )
    ensure_column(conn, "qa_items", "technical_type_id INTEGER", "technical_type_id")
    ensure_column(conn, "qa_items", "business_tags_json TEXT", "business_tags_json")
    ensure_column(conn, "qa_items", "metadata_json TEXT", "metadata_json")
    ensure_column(conn, "qa_items", "source_model TEXT", "source_model")
    ensure_column(
        conn,
        "dataset_batches",
        "application_id INTEGER REFERENCES applications(id)",
        "application_id",
    )
    ensure_column(conn, "dataset_batches", "source_batch_name TEXT", "source_batch_name")
    ensure_column(conn, "dataset_batches", "external_batch_id TEXT", "external_batch_id")
    ensure_column(conn, "dataset_batches", "technical_type_id INTEGER", "technical_type_id")
    ensure_column(conn, "dataset_batches", "business_tags_json TEXT", "business_tags_json")
    ensure_column(conn, "dataset_batches", "parse_lock_token TEXT", "parse_lock_token")
    ensure_column(
        conn,
        "dataset_batches",
        "parse_lock_acquired_at TEXT",
        "parse_lock_acquired_at",
    )
    ensure_column(
        conn,
        "dataset_batches",
        "uploader_user_id INTEGER REFERENCES users(id)",
        "uploader_user_id",
    )
    ensure_column(
        conn,
        "dataset_batches",
        "self_review_status TEXT NOT NULL DEFAULT 'none' CHECK(self_review_status IN ('none', 'queued', 'pending', 'in_progress', 'submitted'))",
        "self_review_status",
    )
    ensure_column(
        conn,
        "dataset_batches",
        "peer_review_status TEXT NOT NULL DEFAULT 'none' CHECK(peer_review_status IN ('none', 'queued', 'pending', 'in_progress', 'completed'))",
        "peer_review_status",
    )
    ensure_column(conn, "llm_configs", "last_tested_at TEXT", "last_tested_at")
    ensure_column(
        conn,
        "llm_configs",
        "llm_use_case TEXT NOT NULL DEFAULT 'evaluation' CHECK(llm_use_case IN ('evaluation', 'trial'))",
        "llm_use_case",
    )
    ensure_column(
        conn,
        "llm_configs",
        "provider_code TEXT NOT NULL DEFAULT 'custom_openai'",
        "provider_code",
    )
    ensure_column(
        conn,
        "llm_configs",
        "is_enabled INTEGER NOT NULL DEFAULT 1",
        "is_enabled",
    )
    ensure_column(
        conn,
        "llm_configs",
        "is_trial_enabled INTEGER NOT NULL DEFAULT 0",
        "is_trial_enabled",
    )
    ensure_column(
        conn,
        "llm_configs",
        "last_test_status TEXT CHECK(last_test_status IN ('passed', 'failed'))",
        "last_test_status",
    )
    ensure_column(conn, "llm_configs", "last_test_message TEXT", "last_test_message")
    ensure_column(conn, "llm_configs", "last_test_latency_ms INTEGER", "last_test_latency_ms")
    ensure_column(
        conn,
        "users",
        "allow_cross_business_review INTEGER NOT NULL DEFAULT 0",
        "allow_cross_business_review",
    )
    ensure_column(
        conn,
        "evaluation_records",
        "reasoning_completeness TEXT CHECK(reasoning_completeness IN ('strong', 'medium', 'weak'))",
        "reasoning_completeness",
    )
    ensure_column(
        conn,
        "evaluation_records",
        "reasoning_consistency TEXT CHECK(reasoning_consistency IN ('strong', 'medium', 'weak'))",
        "reasoning_consistency",
    )
    ensure_column(
        conn,
        "evaluation_records",
        "reasoning_support TEXT CHECK(reasoning_support IN ('strong', 'medium', 'weak'))",
        "reasoning_support",
    )
    ensure_column(conn, "llm_messages", "target_answer_id INTEGER", "target_answer_id")
    ensure_column(conn, "llm_messages", "generated_answer_id INTEGER", "generated_answer_id")
    ensure_column(conn, "llm_messages", "review_json TEXT", "review_json")
    ensure_column(conn, "llm_sessions", "llm_config_id INTEGER", "llm_config_id")
    ensure_column(conn, "llm_sessions", "llm_config_name TEXT", "llm_config_name")
    ensure_column(conn, "llm_sessions", "llm_model_name TEXT", "llm_model_name")
    if table_exists(conn, "llm_configs") and column_exists(conn, "llm_configs", "llm_use_case"):
        conn.execute(
            """
            UPDATE llm_configs
            SET llm_use_case = CASE
              WHEN COALESCE(is_trial_enabled, 0) = 1 THEN 'trial'
              ELSE 'evaluation'
            END
            WHERE llm_use_case IS NULL
               OR llm_use_case NOT IN ('evaluation', 'trial')
            """
        )
    conn.commit()


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    ensure_parent_dir(DB_PATH)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        apply_legacy_migrations(conn)
        conn.executescript(schema)
