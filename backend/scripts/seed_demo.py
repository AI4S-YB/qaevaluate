from datetime import datetime
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import db_cursor, init_db


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def password_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    init_db()
    created_at = now_iso()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (
              id, username, password_hash, role, status, full_name, created_at
            ) VALUES (1, 'admin', ?, 'admin', 'approved', 'System Admin', ?)
            """,
            (password_hash("admin123"), created_at),
        )
        for username, name in (("expert01", "张三"), ("expert02", "李四"), ("expert03", "王五")):
            cursor.execute(
                """
                INSERT OR IGNORE INTO users (
                  username, password_hash, role, status, full_name, organization, title, created_at
                ) VALUES (?, ?, 'expert', 'approved', ?, '示例机构', '研究员', ?)
                """,
                (username, password_hash("expert123"), name, created_at),
            )

        cursor.execute(
            """
            INSERT OR IGNORE INTO applications (id, name, description, is_active, created_at)
            VALUES (1, '农业问答', '病虫害与种植管理', 1, ?)
            """,
            (created_at,),
        )

        expert_ids = cursor.execute(
            "SELECT id FROM users WHERE role = 'expert' ORDER BY id ASC",
        ).fetchall()
        for order, row in enumerate(expert_ids, start=1):
            cursor.execute(
                """
                INSERT OR IGNORE INTO expert_applications (
                  expert_user_id, application_id, priority, created_at
                ) VALUES (?, 1, ?, ?)
                """,
                (row["id"], order, created_at),
            )

        qa_item = cursor.execute(
            "SELECT id FROM qa_items WHERE external_id = 'qa_demo_001'",
            (),
        ).fetchone()
        if qa_item:
            qa_item_id = qa_item["id"]
        else:
            cursor.execute(
                """
                INSERT INTO qa_items (
                  external_id, application_id, question_text, tags_json, source, status, created_at
                ) VALUES (
                  'qa_demo_001', 1, '番茄晚疫病如何防治？',
                  '["病害","番茄"]', 'demo-seed', 'active', ?
                )
                """,
                (created_at,),
            )
            qa_item_id = cursor.lastrowid

        answer = cursor.execute(
            """
            SELECT id
            FROM qa_answers
            WHERE qa_item_id = ? AND answer_type = 'imported_candidate'
            ORDER BY id ASC
            LIMIT 1
            """,
            (qa_item_id,),
        ).fetchone()
        if answer:
            answer_id = answer["id"]
        else:
            cursor.execute(
                """
                INSERT INTO qa_answers (
                  qa_item_id, answer_text, answer_type, source_model, version_no, is_current, created_at
                ) VALUES (
                  ?, '可通过轮作、降低湿度、及时喷施保护性杀菌剂等方式防治。',
                  'imported_candidate', 'seed-model', 1, 1, ?
                )
                """,
                (qa_item_id, created_at),
            )
            answer_id = cursor.lastrowid

        for expert_row in expert_ids[:2]:
            cursor.execute(
                """
                INSERT OR IGNORE INTO evaluation_tasks (
                  qa_item_id, answer_id, expert_user_id, round_no,
                  task_type, status, assigned_at
                ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
                """,
                (qa_item_id, answer_id, expert_row["id"], created_at),
            )
    print("seed data inserted")
