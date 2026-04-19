from datetime import datetime
import hashlib
import json
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


APPLICATIONS = [
    ("农业问答", "病虫害与种植管理"),
    ("农机问答", "农机使用与维护"),
]

TECHNICAL_TYPES = [
    ("direct_qa", "普通问答", "直接回答型 QA", 10),
    ("cot_qa", "长思维链问答", "带推理过程的 QA", 20),
]

BUSINESS_TAGS = [
    ("pest_control", "病虫害", "病虫害防治相关", 10),
    ("tomato", "番茄", "番茄相关", 20),
    ("cucumber", "黄瓜", "黄瓜相关", 30),
    ("rice", "水稻", "水稻相关", 40),
    ("corn", "玉米", "玉米相关", 50),
    ("farm_machinery", "农机", "农机设备相关", 60),
]

EXPERTS = [
    ("expert01", "张三"),
    ("expert02", "李四"),
    ("expert03", "王五"),
    ("expert04", "赵六"),
]

EXPERT_BUSINESS_TAGS = {
    "expert01": ["pest_control", "tomato", "rice"],
    "expert02": ["farm_machinery", "corn"],
    "expert03": ["cucumber", "pest_control"],
    "expert04": ["farm_machinery", "tomato"],
}

QA_SEEDS = [
    {
        "external_id": "qa_demo_001",
        "application": "农业问答",
        "technical_type": "direct_qa",
        "business_tags": ["pest_control", "tomato"],
        "question_text": "番茄晚疫病如何防治？",
        "context_text": "露地栽培，近期连续阴雨。",
        "answer_text": "可通过轮作、降低湿度、及时喷施保护性杀菌剂等方式防治。",
    },
    {
        "external_id": "qa_demo_002",
        "application": "农业问答",
        "technical_type": "direct_qa",
        "business_tags": ["pest_control", "cucumber"],
        "question_text": "黄瓜白粉病初期有哪些处理办法？",
        "context_text": "棚内湿度较高，叶片出现白色粉状斑。",
        "answer_text": "加强通风、摘除病叶，并在初期使用针对性药剂控制扩展。",
    },
    {
        "external_id": "qa_demo_003",
        "application": "农业问答",
        "technical_type": "cot_qa",
        "business_tags": ["corn"],
        "question_text": "玉米倒伏后应如何补救？",
        "context_text": "大风后部分地块出现根倒和茎倒。",
        "answer_text": "根据倒伏程度扶正培土，及时排水，并结合叶面补肥促进恢复。",
    },
    {
        "external_id": "qa_demo_004",
        "application": "农业问答",
        "technical_type": "direct_qa",
        "business_tags": ["pest_control", "rice"],
        "question_text": "水稻纹枯病高发期如何降低损失？",
        "context_text": "分蘖后期到抽穗期，高温高湿。",
        "answer_text": "控制氮肥、改善通风条件，并在适期使用登记药剂进行防治。",
    },
    {
        "external_id": "qa_demo_005",
        "application": "农业问答",
        "technical_type": "direct_qa",
        "business_tags": [],
        "question_text": "苹果树春季修剪要注意什么？",
        "context_text": "目标是改善通风透光和结果枝组布局。",
        "answer_text": "以疏枝、回缩和更新复壮为主，避免一次性过度短截。",
    },
    {
        "external_id": "qa_demo_006",
        "application": "农业问答",
        "technical_type": "direct_qa",
        "business_tags": [],
        "question_text": "辣椒出现落花落果的常见原因有哪些？",
        "context_text": "近期温差大，部分植株长势偏旺。",
        "answer_text": "常见原因包括温度不稳、水肥失衡和授粉受阻，应针对性调整管理。",
    },
    {
        "external_id": "qa_demo_007",
        "application": "农机问答",
        "technical_type": "direct_qa",
        "business_tags": ["farm_machinery"],
        "question_text": "拖拉机冷启动困难时应优先检查哪些项目？",
        "context_text": "早晨低温环境，启动时间明显变长。",
        "answer_text": "优先检查电瓶电量、燃油供给、机油黏度以及预热系统是否正常。",
    },
    {
        "external_id": "qa_demo_008",
        "application": "农机问答",
        "technical_type": "direct_qa",
        "business_tags": ["farm_machinery"],
        "question_text": "播种机下籽不均匀通常是什么原因？",
        "context_text": "同一垄出现漏播和重播。",
        "answer_text": "要检查排种器磨损、传动打滑、种子规格不一致和机具调校是否准确。",
    },
    {
        "external_id": "qa_demo_009",
        "application": "农机问答",
        "technical_type": "cot_qa",
        "business_tags": ["farm_machinery"],
        "question_text": "植保无人机喷幅重叠过大如何调整？",
        "context_text": "作业后发现部分区域药液覆盖过量。",
        "answer_text": "应重新校准航线、飞行速度与喷幅参数，并结合风速条件优化作业设置。",
    },
    {
        "external_id": "qa_demo_010",
        "application": "农机问答",
        "technical_type": "cot_qa",
        "business_tags": ["farm_machinery"],
        "question_text": "联合收割机作业损失率偏高怎么办？",
        "context_text": "籽粒抛撒明显，地块成熟度不完全一致。",
        "answer_text": "需结合作物状态调整滚筒、风量、筛片和行进速度，减少过度脱粒与抛撒。",
    },
    {
        "external_id": "qa_demo_011",
        "application": "农业问答",
        "technical_type": "direct_qa",
        "business_tags": ["pest_control"],
        "question_text": "草莓灰霉病在采收前怎样控病更稳妥？",
        "context_text": "设施栽培，近一周湿度持续偏高。",
        "answer_text": "重点是控湿、摘除病果病叶，并严格按安全间隔期选择合规防治措施。",
    },
    {
        "external_id": "qa_demo_012",
        "application": "农业问答",
        "technical_type": "cot_qa",
        "business_tags": ["tomato"],
        "question_text": "大棚番茄裂果与哪些管理因素有关？",
        "context_text": "近期浇水不均，昼夜温差较大。",
        "answer_text": "裂果常与水分波动、温湿度变化和钙硼供应不足有关，应综合调整。",
    },
]


def ensure_user(cursor, username: str, password: str, role: str, status: str, full_name: str):
    created_at = now_iso()
    existing = cursor.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE users
            SET password_hash = ?, role = ?, status = ?, full_name = ?
            WHERE username = ?
            """,
            (password_hash(password), role, status, full_name, username),
        )
        return existing["id"]

    cursor.execute(
        """
        INSERT INTO users (
          username, password_hash, role, status, full_name, organization, title, created_at
        ) VALUES (?, ?, ?, ?, ?, '示例机构', '研究员', ?)
        """,
        (username, password_hash(password), role, status, full_name, created_at),
    )
    return cursor.lastrowid


def ensure_application(cursor, name: str, description: str):
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
        return existing["id"]

    cursor.execute(
        """
        INSERT INTO applications (name, description, is_active, created_at)
        VALUES (?, ?, 1, ?)
        """,
        (name, description, created_at),
    )
    return cursor.lastrowid


def ensure_technical_type(cursor, code: str, name: str, description: str, sort_order: int):
    created_at = now_iso()
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
        (code, name, description, sort_order, created_at),
    )
    return cursor.lastrowid


def ensure_business_tag(cursor, code: str, name: str, description: str, sort_order: int):
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
        return existing["id"]

    cursor.execute(
        """
        INSERT INTO business_tags (code, name, description, is_active, sort_order, created_at)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (code, name, description, sort_order, created_at),
    )
    return cursor.lastrowid


def ensure_qa_item(cursor, application_id: int, technical_type_id: int, seed: dict):
    created_at = now_iso()
    business_tags_json = json.dumps(seed["business_tags"], ensure_ascii=False)
    existing = cursor.execute(
        "SELECT id FROM qa_items WHERE external_id = ? ORDER BY id ASC LIMIT 1",
        (seed["external_id"],),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE qa_items
            SET technical_type_id = ?, application_id = ?, question_text = ?, context_text = ?,
                business_tags_json = ?, tags_json = ?,
                source = 'demo-seed', status = 'active'
            WHERE id = ?
            """,
            (
                technical_type_id,
                application_id,
                seed["question_text"],
                seed["context_text"],
                business_tags_json,
                business_tags_json,
                existing["id"],
            ),
        )
        return existing["id"]

    cursor.execute(
        """
        INSERT INTO qa_items (
          external_id, technical_type_id, business_tags_json, application_id,
          question_text, context_text, tags_json, source, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'demo-seed', 'active', ?)
        """,
        (
            seed["external_id"],
            technical_type_id,
            business_tags_json,
            application_id,
            seed["question_text"],
            seed["context_text"],
            business_tags_json,
            created_at,
        ),
    )
    return cursor.lastrowid


def ensure_answer(cursor, qa_item_id: int, answer_text: str):
    created_at = now_iso()
    existing = cursor.execute(
        """
        SELECT id
        FROM qa_answers
        WHERE qa_item_id = ? AND answer_type = 'imported_candidate'
        ORDER BY id ASC
        LIMIT 1
        """,
        (qa_item_id,),
    ).fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE qa_answers
            SET answer_text = ?, source_model = 'seed-model', version_no = 1, is_current = 1
            WHERE id = ?
            """,
            (answer_text, existing["id"]),
        )
        return existing["id"]

    cursor.execute(
        """
        INSERT INTO qa_answers (
          qa_item_id, answer_text, answer_type, source_model, version_no, is_current, created_at
        ) VALUES (?, ?, 'imported_candidate', 'seed-model', 1, 1, ?)
        """,
        (qa_item_id, answer_text, created_at),
    )
    return cursor.lastrowid


if __name__ == "__main__":
    init_db()
    with db_cursor() as cursor:
        ensure_user(cursor, "admin", "admin123", "admin", "approved", "System Admin")

        expert_ids = []
        for username, name in EXPERTS:
            expert_ids.append(
                ensure_user(cursor, username, "expert123", "expert", "approved", name)
            )

        application_ids = {}
        for name, description in APPLICATIONS:
            application_ids[name] = ensure_application(cursor, name, description)

        technical_type_ids = {}
        for code, name, description, sort_order in TECHNICAL_TYPES:
            technical_type_ids[code] = ensure_technical_type(
                cursor, code, name, description, sort_order
            )

        for code, name, description, sort_order in BUSINESS_TAGS:
            ensure_business_tag(cursor, code, name, description, sort_order)

        business_tag_ids = {
            row["code"]: row["id"]
            for row in cursor.execute(
                "SELECT id, code FROM business_tags WHERE is_active = 1"
            ).fetchall()
        }

        for expert_order, expert_id in enumerate(expert_ids, start=1):
            for app_name, app_id in application_ids.items():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO expert_applications (
                      expert_user_id, application_id, priority, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (expert_id, app_id, expert_order, now_iso()),
                )
        for username, _name in EXPERTS:
            expert_row = cursor.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not expert_row:
                continue
            cursor.execute(
                "DELETE FROM expert_business_tags WHERE expert_user_id = ?",
                (expert_row["id"],),
            )
            for priority, tag_code in enumerate(EXPERT_BUSINESS_TAGS.get(username, []), start=1):
                tag_id = business_tag_ids.get(tag_code)
                if not tag_id:
                    continue
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO expert_business_tags (
                      expert_user_id, business_tag_id, priority, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (expert_row["id"], tag_id, priority, now_iso()),
                )

        assigned_experts = expert_ids[:2]
        for seed in QA_SEEDS:
            qa_item_id = ensure_qa_item(
                cursor,
                application_ids[seed["application"]],
                technical_type_ids[seed["technical_type"]],
                seed,
            )
            answer_id = ensure_answer(cursor, qa_item_id, seed["answer_text"])
            for expert_id in assigned_experts:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO evaluation_tasks (
                      qa_item_id, answer_id, expert_user_id, round_no,
                      task_type, status, assigned_at
                    ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
                    """,
                    (qa_item_id, answer_id, expert_id, now_iso()),
                )

    print(f"seed data inserted: {len(QA_SEEDS)} qa items, {len(EXPERTS)} experts")
