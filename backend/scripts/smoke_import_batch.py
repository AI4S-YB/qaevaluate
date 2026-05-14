from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from urllib import error, request


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.config import APP_ENV, DB_PATH  # noqa: E402

API_BASE = "http://127.0.0.1:8100"
USERNAME = "admin"
PASSWORD = "admin123"
APPLICATION_ID = 1
TECHNICAL_TYPE_CODE = "cot_qa"
BUSINESS_TAG_CODES = ["tomato", "pest_control"]


def http_json(url: str, method: str = "GET", token: str | None = None, payload: dict | None = None):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_multipart_form(file_path: Path, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----qaevaluate-{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
                "Content-Type: application/json\r\n\r\n"
            ).encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks), boundary


def upload_file(token: str, file_path: Path, fields: dict[str, str]) -> dict:
    body, boundary = build_multipart_form(file_path, fields)
    req = request.Request(
        f"{API_BASE}/api/admin/imports/upload",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def wait_for_batch(batch_id: int, timeout_seconds: int = 20) -> sqlite3.Row:
    deadline = time.time() + timeout_seconds
    last_row = None
    while time.time() < deadline:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT id, import_status, total_count, success_count, fail_count
                FROM dataset_batches
                WHERE id = ?
                """,
                (batch_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f"batch {batch_id} not found")
        last_row = row
        if row["import_status"] in {"parsed", "failed"}:
            return row
        time.sleep(1)
    raise RuntimeError(f"batch {batch_id} still pending: {dict(last_row) if last_row else 'unknown'}")


def assert_import_result(batch_id: int) -> None:
    with get_db() as conn:
        items = conn.execute(
            """
            SELECT
              q.external_id,
              q.application_id,
              q.technical_type_id,
              q.business_tags_json,
              q.dataset_batch_id,
              a.name AS application_name,
              tt.code AS technical_type_code
            FROM qa_items q
            JOIN applications a ON a.id = q.application_id
            LEFT JOIN technical_types tt ON tt.id = q.technical_type_id
            WHERE q.dataset_batch_id = ?
            ORDER BY q.id ASC
            """,
            (batch_id,),
        ).fetchall()
        answers = conn.execute(
            """
            SELECT qa.answer_type, qa.version_no, qa.is_current, q.external_id
            FROM qa_answers qa
            JOIN qa_items q ON q.id = qa.qa_item_id
            WHERE q.dataset_batch_id = ?
            ORDER BY qa.id ASC
            """,
            (batch_id,),
        ).fetchall()

    if len(items) != 2:
        raise RuntimeError(f"expected 2 qa_items, got {len(items)}")
    if len(answers) != 2:
        raise RuntimeError(f"expected 2 qa_answers, got {len(answers)}")

    expected_tags = json.dumps(sorted(BUSINESS_TAG_CODES), ensure_ascii=False)
    for item in items:
        if item["application_id"] != APPLICATION_ID:
            raise RuntimeError(f"unexpected application_id for {item['external_id']}: {item['application_id']}")
        if item["technical_type_code"] != TECHNICAL_TYPE_CODE:
            raise RuntimeError(
                f"unexpected technical_type_code for {item['external_id']}: {item['technical_type_code']}"
            )
        if item["business_tags_json"] != expected_tags:
            raise RuntimeError(
                f"unexpected business_tags_json for {item['external_id']}: {item['business_tags_json']}"
            )

    for answer in answers:
        if answer["answer_type"] != "imported_candidate" or answer["version_no"] != 1 or answer["is_current"] != 1:
            raise RuntimeError(f"unexpected answer row: {dict(answer)}")


def main() -> int:
    sample_rows = [
        {
            "id": f"smoke_import_{int(time.time())}_001",
            "question": "番茄叶片黄化时第一步应先检查哪些条件？",
            "answer": "应先结合根系状态、水肥管理和环境变化，优先排查积水、缺素和病害等原因。",
            "context": "设施栽培，近几日光照偏弱。",
        },
        {
            "id": f"smoke_import_{int(time.time())}_002",
            "question": "番茄花期坐果率偏低时先看哪些管理因素？",
            "answer": "可先检查温湿度、授粉条件、营养生长是否过旺，以及花期灌溉施肥是否平衡。",
            "context": "棚内午间温度偏高，近期氮肥投入较多。",
        },
    ]

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(sample_rows, tmp, ensure_ascii=False, indent=2)
        temp_path = Path(tmp.name)

    try:
        login = http_json(
            f"{API_BASE}/api/auth/login",
            method="POST",
            payload={"username": USERNAME, "password": PASSWORD},
        )
        token = login["data"]["token"]
        upload = upload_file(
            token,
            temp_path,
            {
                "name": f"smoke-batch-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "source": "smoke-test",
                "application_id": str(APPLICATION_ID),
                "technical_type_code": TECHNICAL_TYPE_CODE,
                "business_tags_json": json.dumps(BUSINESS_TAG_CODES, ensure_ascii=False),
            },
        )
        batch_id = int(upload["data"]["batch_id"])
        http_json(
            f"{API_BASE}/api/admin/imports/{batch_id}/parse",
            method="POST",
            token=token,
        )
        batch = wait_for_batch(batch_id)
        if batch["import_status"] != "parsed" or batch["success_count"] != 2 or batch["fail_count"] != 0:
            raise RuntimeError(f"unexpected batch status: {dict(batch)}")
        assert_import_result(batch_id)
        print(f"smoke import passed: batch_id={batch_id}")
        return 0
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"http error {exc.code}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    print(f"running smoke import against env={APP_ENV} db={DB_PATH}")
    raise SystemExit(main())
