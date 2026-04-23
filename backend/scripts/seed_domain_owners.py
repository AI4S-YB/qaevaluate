from datetime import datetime
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import APP_ENV, DB_PATH, IS_DEVELOPMENT
from app.db import db_cursor, init_db


UNIFIED_PASSWORD = "Ai4s#2026!Owner"

AI4S_APPLICATION = (
    "AI4S攻关任务",
    "AI4S 攻关任务统一项目，八个方向作为领域场景管理和评测。",
)

LEGACY_PROGRAM_APPLICATION_NAMES = [
    "农业问答",
    "农机问答",
    "野生稻资源评价与利用",
    "大豆协同优化",
    "玉米高蛋白饲用",
    "光合固氮协同提升生物量",
    "作物病害机制及防控",
    "猪育种与生产",
    "水稻 AI 育种家",
    "具身智能（牛魔王）",
]


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def password_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


PROGRAMS = [
    {
        "program_name": "野生稻资源评价与利用",
        "business_tag": (
            "wild_rice_resource_utilization",
            "野生稻种质快速评价与利用",
            "围绕野生稻种质快速评价、数字孪生建模与资源智慧化利用。",
            10,
        ),
        "owners": [("sunjian", "孙健", ["expert_sunjian"])],
    },
    {
        "program_name": "大豆协同优化",
        "business_tag": (
            "soybean_synergy_optimization",
            "耐密植、高油、高蛋白协同优化",
            "围绕耐密植、高油、高蛋白性状拮抗与协同优化开展评价与利用。",
            20,
        ),
        "owners": [("shenyanting", "申研婷", ["expert_shenyanting"])],
    },
    {
        "program_name": "玉米高蛋白饲用",
        "business_tag": (
            "maize_high_protein_feed",
            "高蛋白饲用玉米综合利用",
            "面向高蛋白饲用玉米的综合性状评价、风险控制与利用。",
            30,
        ),
        "owners": [("shaoyang", "邵扬", ["expert_shaoyang"])],
    },
    {
        "program_name": "光合固氮协同提升生物量",
        "business_tag": (
            "photosynthesis_nitrogen_biomass",
            "生物量最大化与养分调控",
            "聚焦光合固氮协同、生物量最大化与分时期养分调控。",
            40,
        ),
        "owners": [
            ("wanghaifeng", "王海峰", ["expert_wanghaifeng"]),
            ("xuyongxin", "徐永欣", ["expert_xuyongxin"]),
        ],
    },
    {
        "program_name": "作物病害机制及防控",
        "business_tag": (
            "crop_disease_mechanism_control",
            "病害胁迫下稳产机制",
            "围绕病害胁迫、稳产机制与资源评价体系构建。",
            50,
        ),
        "owners": [
            ("mashengwei", "马省伟", ["expert_mashengwei"]),
            ("yangzhiquan", "杨植全", ["expert_yangzhiquan"]),
        ],
    },
    {
        "program_name": "猪育种与生产",
        "business_tag": (
            "pig_breeding_production",
            "提高生猪的饲料转化效率",
            "面向生猪育种与生产的饲料转化效率提升和精准饲喂。",
            60,
        ),
        "owners": [("lixin", "黎欣", ["expert_lixin"])],
    },
    {
        "program_name": "水稻 AI 育种家",
        "business_tag": (
            "rice_ai_breeder",
            "育种家经验AI化与主栽品种改良",
            "围绕水稻 AI 育种家、经验建模与区域主栽品种精准改良。",
            70,
        ),
        "owners": [("fanlongjiang", "樊龙江", ["expert_fanlongjiang"])],
    },
    {
        "program_name": "具身智能（牛魔王）",
        "business_tag": (
            "embodied_intelligence_agri",
            "快速表型采集与生产匹配",
            "面向具身智能农业场景的快速表型采集、农业性状评价与生产匹配。",
            80,
        ),
        "owners": [("yangwanneng", "杨万能", ["expert_yangwanneng"])],
    },
]


def ensure_user(cursor, username: str, full_name: str, legacy_usernames: list[str]) -> int:
    created_at = now_iso()
    existing = cursor.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not existing and legacy_usernames:
        placeholders = ",".join("?" for _ in legacy_usernames)
        existing = cursor.execute(
            f"SELECT id FROM users WHERE username IN ({placeholders}) ORDER BY id ASC LIMIT 1",
            tuple(legacy_usernames),
        ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE users
            SET password_hash = ?,
                role = 'expert',
                status = 'approved',
                username = ?,
                full_name = ?,
                organization = 'AI4S 项目组',
                title = '领域负责人'
            WHERE id = ?
            """,
            (password_hash(UNIFIED_PASSWORD), username, full_name, existing["id"]),
        )
        return int(existing["id"])

    cursor.execute(
        """
        INSERT INTO users (
          username, password_hash, role, status, full_name,
          organization, title, created_at
        ) VALUES (?, ?, 'expert', 'approved', ?, 'AI4S 项目组', '领域负责人', ?)
        """,
        (username, password_hash(UNIFIED_PASSWORD), full_name, created_at),
    )
    return int(cursor.lastrowid)


def ensure_application(cursor, name: str, description: str) -> int:
    created_at = now_iso()
    existing = cursor.execute(
        "SELECT id FROM applications WHERE name = ?",
        (name,),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE applications
            SET description = ?, is_active = 1
            WHERE id = ?
            """,
            (description, existing["id"]),
        )
        return int(existing["id"])

    cursor.execute(
        """
        INSERT INTO applications (name, description, is_active, created_at)
        VALUES (?, ?, 1, ?)
        """,
        (name, description, created_at),
    )
    return int(cursor.lastrowid)


def ensure_business_tag(
    cursor, code: str, name: str, description: str, sort_order: int
) -> int:
    created_at = now_iso()
    existing = cursor.execute(
        "SELECT id FROM business_tags WHERE code = ?",
        (code,),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE business_tags
            SET name = ?, description = ?, is_active = 1, sort_order = ?
            WHERE id = ?
            """,
            (name, description, sort_order, existing["id"]),
        )
        return int(existing["id"])

    cursor.execute(
        """
        INSERT INTO business_tags (code, name, description, is_active, sort_order, created_at)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (code, name, description, sort_order, created_at),
    )
    return int(cursor.lastrowid)


def bind_owner_scope(cursor, expert_user_id: int, application_id: int, business_tag_id: int) -> None:
    created_at = now_iso()
    cursor.execute(
        """
        INSERT OR IGNORE INTO expert_applications (
          expert_user_id, application_id, priority, created_at
        ) VALUES (?, ?, 1, ?)
        """,
        (expert_user_id, application_id, created_at),
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO expert_business_tags (
          expert_user_id, business_tag_id, priority, created_at
        ) VALUES (?, ?, 1, ?)
        """,
        (expert_user_id, business_tag_id, created_at),
    )


def delete_legacy_program_applications(cursor) -> None:
    if not LEGACY_PROGRAM_APPLICATION_NAMES:
        return
    legacy_rows = cursor.execute(
        f"""
        SELECT id
        FROM applications
        WHERE name IN ({",".join("?" for _ in LEGACY_PROGRAM_APPLICATION_NAMES)})
        """,
        tuple(LEGACY_PROGRAM_APPLICATION_NAMES),
    ).fetchall()
    if not legacy_rows:
        return

    application_ids = [int(row["id"]) for row in legacy_rows]
    application_placeholders = ",".join("?" for _ in application_ids)

    qa_item_rows = cursor.execute(
        f"""
        SELECT id
        FROM qa_items
        WHERE application_id IN ({application_placeholders})
        """,
        tuple(application_ids),
    ).fetchall()
    qa_item_ids = [int(row["id"]) for row in qa_item_rows]
    if qa_item_ids:
        qa_item_placeholders = ",".join("?" for _ in qa_item_ids)
        answer_rows = cursor.execute(
            f"SELECT id FROM qa_answers WHERE qa_item_id IN ({qa_item_placeholders})",
            tuple(qa_item_ids),
        ).fetchall()
        answer_ids = [int(row["id"]) for row in answer_rows]

        task_rows = cursor.execute(
            f"SELECT id FROM evaluation_tasks WHERE qa_item_id IN ({qa_item_placeholders})",
            tuple(qa_item_ids),
        ).fetchall()
        task_ids = [int(row["id"]) for row in task_rows]
        if task_ids:
            task_placeholders = ",".join("?" for _ in task_ids)
            cursor.execute(
                f"DELETE FROM evaluation_records WHERE task_id IN ({task_placeholders})",
                tuple(task_ids),
            )
            cursor.execute(
                f"DELETE FROM evaluation_drafts WHERE task_id IN ({task_placeholders})",
                tuple(task_ids),
            )

        llm_session_rows = cursor.execute(
            f"SELECT id FROM llm_sessions WHERE qa_item_id IN ({qa_item_placeholders})",
            tuple(qa_item_ids),
        ).fetchall()
        llm_session_ids = [int(row["id"]) for row in llm_session_rows]
        if llm_session_ids:
            llm_session_placeholders = ",".join("?" for _ in llm_session_ids)
            cursor.execute(
                f"DELETE FROM llm_messages WHERE session_id IN ({llm_session_placeholders})",
                tuple(llm_session_ids),
            )
            cursor.execute(
                f"DELETE FROM llm_sessions WHERE id IN ({llm_session_placeholders})",
                tuple(llm_session_ids),
            )

        if answer_ids:
            answer_placeholders = ",".join("?" for _ in answer_ids)
            model_trial_rows = cursor.execute(
                f"""
                SELECT id
                FROM model_trial_sessions
                WHERE source_qa_item_id IN ({qa_item_placeholders})
                   OR source_answer_id IN ({answer_placeholders})
                """,
                tuple(qa_item_ids) + tuple(answer_ids),
            ).fetchall()
        else:
            model_trial_rows = cursor.execute(
                f"""
                SELECT id
                FROM model_trial_sessions
                WHERE source_qa_item_id IN ({qa_item_placeholders})
                """,
                tuple(qa_item_ids),
            ).fetchall()
        model_trial_ids = [int(row["id"]) for row in model_trial_rows]
        if model_trial_ids:
            model_trial_placeholders = ",".join("?" for _ in model_trial_ids)
            cursor.execute(
                f"DELETE FROM model_trial_messages WHERE session_id IN ({model_trial_placeholders})",
                tuple(model_trial_ids),
            )
            cursor.execute(
                f"DELETE FROM model_trial_sessions WHERE id IN ({model_trial_placeholders})",
                tuple(model_trial_ids),
            )

        cursor.execute(
            f"DELETE FROM expert_task_abandons WHERE qa_item_id IN ({qa_item_placeholders})",
            tuple(qa_item_ids),
        )
        cursor.execute(
            f"DELETE FROM evaluation_tasks WHERE qa_item_id IN ({qa_item_placeholders})",
            tuple(qa_item_ids),
        )

        if answer_ids:
            answer_placeholders = ",".join("?" for _ in answer_ids)
            cursor.execute(
                f"""
                DELETE FROM llm_messages
                WHERE target_answer_id IN ({answer_placeholders})
                   OR generated_answer_id IN ({answer_placeholders})
                """,
                tuple(answer_ids) + tuple(answer_ids),
            )
            cursor.execute(
                f"""
                DELETE FROM qa_aggregates
                WHERE current_answer_id IN ({answer_placeholders})
                   OR final_standard_answer_id IN ({answer_placeholders})
                """,
                tuple(answer_ids) + tuple(answer_ids),
            )
            cursor.execute(
                f"DELETE FROM qa_answers WHERE id IN ({answer_placeholders})",
                tuple(answer_ids),
            )

        cursor.execute(
            f"DELETE FROM qa_aggregates WHERE qa_item_id IN ({qa_item_placeholders})",
            tuple(qa_item_ids),
        )
        cursor.execute(
            f"DELETE FROM qa_items WHERE id IN ({qa_item_placeholders})",
            tuple(qa_item_ids),
        )

    dataset_batch_rows = cursor.execute(
        f"""
        SELECT id
        FROM dataset_batches
        WHERE application_id IN ({application_placeholders})
        """,
        tuple(application_ids),
    ).fetchall()
    dataset_batch_ids = [int(row["id"]) for row in dataset_batch_rows]
    if dataset_batch_ids:
        dataset_batch_placeholders = ",".join("?" for _ in dataset_batch_ids)
        cursor.execute(
            f"""
            DELETE FROM dataset_batch_failures
            WHERE dataset_batch_id IN ({dataset_batch_placeholders})
            """,
            tuple(dataset_batch_ids),
        )
        cursor.execute(
            f"DELETE FROM dataset_batches WHERE id IN ({dataset_batch_placeholders})",
            tuple(dataset_batch_ids),
        )

    cursor.execute(
        f"DELETE FROM export_jobs WHERE application_id IN ({application_placeholders})",
        tuple(application_ids),
    )
    cursor.execute(
        f"DELETE FROM expert_applications WHERE application_id IN ({application_placeholders})",
        tuple(application_ids),
    )
    cursor.execute(
        f"DELETE FROM applications WHERE id IN ({application_placeholders})",
        tuple(application_ids),
    )


if __name__ == "__main__":
    if not IS_DEVELOPMENT and os.getenv("QAEVALUATE_ALLOW_DEMO_SEED") != "1":
        raise SystemExit(
            f"refusing to seed domain owners in env={APP_ENV}. "
            "Set QAEVALUATE_ENV=development or QAEVALUATE_ALLOW_DEMO_SEED=1 to override."
        )

    init_db()

    with db_cursor() as cursor:
        application_id = ensure_application(cursor, *AI4S_APPLICATION)
        for program in PROGRAMS:
            business_tag_id = ensure_business_tag(cursor, *program["business_tag"])
            for username, full_name, legacy_usernames in program["owners"]:
                expert_user_id = ensure_user(cursor, username, full_name, legacy_usernames)
                cursor.execute(
                    "DELETE FROM expert_applications WHERE expert_user_id = ?",
                    (expert_user_id,),
                )
                bind_owner_scope(cursor, expert_user_id, application_id, business_tag_id)
        delete_legacy_program_applications(cursor)

    total_owners = sum(len(program["owners"]) for program in PROGRAMS)
    print(
        f"seeded AI4S application with {len(PROGRAMS)} domain programs and {total_owners} owner accounts "
        f"for env={APP_ENV} db={DB_PATH}"
    )
