# 详细说明

## 开发环境

推荐方式：

```bash
cp .env.development.example .env.development.local
./scripts/start-dev.sh
```

脚本会自动启动：

- 后端 API
- 后端 worker
- 前端开发服务器

如果需要手动启动：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
QAEVALUATE_ENV=development python scripts/init_db.py
QAEVALUATE_ENV=development python scripts/seed_demo.py
QAEVALUATE_ENV=development uvicorn app.main:app --reload --port 8100
```

另开一个终端启动 worker：

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

再另开一个终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

## 生产环境

推荐方式：

```bash
cp .env.production.example .env.production.local
./scripts/prepare-prod.sh
./scripts/start-prod.sh
```

`prepare-prod.sh` 会完成：

- 创建生产运行目录
- 初始化生产 SQLite 数据库
- 创建本机 LLM 密钥文件
- 构建前端生产包

仓库内也提供了部署模板：

- `deploy/systemd/qaevaluate-backend.service`
- `deploy/systemd/qaevaluate-worker.service`
- `deploy/systemd/qaevaluate-frontend.service`
- `deploy/systemd/qaevaluate-backup.service`
- `deploy/systemd/qaevaluate-backup.timer`
- `deploy/nginx/qaevaluate.conf`

典型部署流程：

```bash
cd /srv/qaevaluate/current
cp .env.production.example .env.production.local
./scripts/prepare-prod.sh
sudo cp deploy/systemd/qaevaluate-*.service /etc/systemd/system/
sudo cp deploy/systemd/qaevaluate-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qaevaluate-backend qaevaluate-worker qaevaluate-frontend
sudo systemctl enable --now qaevaluate-backup.timer
```

## 备份与恢复

建议定期备份 `SQLite` 数据库，尤其是生产环境。

备份：

```bash
./scripts/backup-db.sh production
```

也可以指定输出文件：

```bash
./scripts/backup-db.sh production /srv/qaevaluate/backups/app-prod-latest.sqlite3
```

清理旧备份，只保留最近 14 份：

```bash
./scripts/cleanup-backups.sh production 14
```

恢复前建议先停掉后端和 worker：

```bash
./scripts/stop.sh
./scripts/restore-db.sh production /srv/qaevaluate/backups/app-prod-latest.sqlite3
```

恢复脚本会在覆盖前自动为当前数据库再生成一份 `pre-restore` 快照。

如果使用仓库内的 `systemd` 模板：

- `qaevaluate-backup.service` 会执行一次备份并清理旧文件
- `qaevaluate-backup.timer` 默认每天 `03:30` 触发
- 可通过 `QAEVALUATE_BACKUP_KEEP_COUNT` 调整保留份数

## 环境隔离

系统通过 `QAEVALUATE_ENV` 区分开发和生产环境。

默认隔离规则：

- 开发数据库：`backend/data/development/app.db`
- 生产数据库：`backend/data/production/app.db`
- 开发 LLM 密钥：`backend/data/development/llm_config_secrets.json`
- 生产 LLM 密钥：`backend/data/production/llm_config_secrets.json`
- 开发运行目录：`data/development/`
- 生产运行目录：`data/production/`

可覆盖的环境变量：

- `QAEVALUATE_DB_PATH`
- `QAEVALUATE_LLM_SECRETS_PATH`
- `QAEVALUATE_RUNTIME_DIR`
- `QAEVALUATE_BACKEND_DATA_DIR`
- `BACKEND_HOST`
- `BACKEND_PORT`
- `FRONTEND_HOST`
- `FRONTEND_PORT`
- `NEXT_PUBLIC_API_BASE_URL`

脚本加载顺序：

- 开发：`.env` -> `.env.development` -> `.env.development.local`
- 生产：`.env` -> `.env.production` -> `.env.production.local`

## 导入验证

当前导入链路采用“批次级指定项目、QA 类型、领域场景”。

导入 JSON 只需要题目内容，例如：

```json
[
  {
    "id": "qa_001",
    "question": "番茄晚疫病如何防治？",
    "answer": "可通过轮作、降低湿度、及时喷施保护性杀菌剂等方式防治。",
    "context": "露地栽培，近期连续阴雨。"
  }
]
```

可用以下命令做冒烟验证：

```bash
QAEVALUATE_ENV=development python3 backend/scripts/smoke_import_batch.py
```

如果需要从另一套程序直接推送批量 QA，而不是走文件上传，也可以调用 JSON 接口：

```bash
curl -X POST http://127.0.0.1:8100/api/admin/imports/push \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "remote-sync-20260423",
    "source": "user-program",
    "application_id": 1,
    "technical_type_code": "cot_qa",
    "business_tag_codes": ["tomato"],
    "auto_parse": true,
    "rows": [
      {
        "id": "qa_ext_001",
        "question": "番茄裂果的常见原因是什么？",
        "answer": "常与水分波动、温差过大和钙硼供应不足有关。",
        "context": "设施栽培，近期灌溉不均。",
        "difficulty": "medium",
        "source": "user-program",
        "model": "generator-v1"
      }
    ]
  }'
```

返回结果会包含：

- `batch_id`：当前导入批次 ID
- `job_id`：如果 `auto_parse=true`，会返回异步解析任务 ID
- `parse_queued`：是否已经自动进入解析队列

该接口复用现有批次导入逻辑，`rows` 中每条记录至少需要 `question` 和 `answer`；
如果未显式提供 `answer`，也支持从 `candidate_answers[0].answer` 读取。

## 当前限制

- 当前仍是实验性原型，重点是流程和产品验证
- 认证与安全策略仍是轻量实现
- 生产监控、日志汇聚、备份恢复等能力还未完善
- 导出格式目前主要是基础 `JSON / JSONL`
- LLM 功能依赖后台已配置并启用的兼容模型
