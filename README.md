# QA 评测平台

> 声明：这是一个实验性项目，当前用于原型验证、流程设计和本地演示，不应直接视为生产可用系统。

这是一个轻量化的 QA 对评测平台原型，面向“导入大量 QA 数据 -> 分发给专家评测 -> 借助 LLM 辅助分析与改写 -> 聚合形成可训练数据”的闭环场景。

当前实现基于以下技术栈：

- 后端：`FastAPI + SQLite`
- 前端：`Next.js + Tailwind CSS + shadcn/ui 风格组件`
- 异步任务：`基于文件目录的队列 worker`

## 项目特点

- 使用 `SQLite`，整体依赖轻，便于本地启动
- 专家注册后需管理员审核
- 专家以结构化选择题方式完成评测
- 支持 LLM 辅助事实检查、风险检查、比较分析和改写候选答案
- 每个 QA 至少 2 位专家评测，冲突时可补第 3 位专家复核
- 管理端支持导入、分发、监控、聚合查看、最终标准答案确认和结果导出

## 当前已实现

- 专家端
  - 工作台
  - 任务列表
  - 任务详情
  - 结构化评分
  - 草稿保存
  - LLM 辅助分析与改写候选答案
  - 历史记录
  - 个人资料页
- 管理端
  - 仪表盘
  - 专家审核
  - 应用管理与运营概览
  - 数据导入与失败明细
  - QA 列表与 QA 详情
  - 任务分发与队列监控
  - 统计分析
  - 结果导出
- 队列任务
  - `import`
  - `dispatch`
  - `aggregate`
  - `llm`
  - `export`

## 目录结构

```text
backend/
  app/
  scripts/
frontend/
  app/
  components/
docs/
data/
  queue/
  uploads/
  exports/
```

## 环境隔离

- 系统通过 `QAEVALUATE_ENV` 区分运行环境
- 默认环境是 `development`
- `./scripts/start-dev.sh` 会自动使用 `QAEVALUATE_ENV=development`
- `./scripts/start-prod.sh` 会自动使用 `QAEVALUATE_ENV=production`

不同环境默认会使用不同的数据目录：

- 开发环境数据库：`backend/data/development/app.db`
- 生产环境数据库：`backend/data/production/app.db`
- 开发环境本地 LLM 密钥：`backend/data/development/llm_config_secrets.json`
- 生产环境本地 LLM 密钥：`backend/data/production/llm_config_secrets.json`
- 运行态目录：`data/development/` 与 `data/production/`

如果需要，也可以通过环境变量手动覆盖：

- `QAEVALUATE_DB_PATH`
- `QAEVALUATE_LLM_SECRETS_PATH`
- `QAEVALUATE_RUNTIME_DIR`
- `QAEVALUATE_BACKEND_DATA_DIR`

环境文件建议：

- 通用模板：`/.env.example`
- 开发模板：`/.env.development.example`
- 生产模板：`/.env.production.example`
- 本地实际配置建议使用：
  - `/.env.development.local`
  - `/.env.production.local`

启动脚本会自动加载：

- 开发脚本：`.env` -> `.env.development` -> `.env.development.local`
- 生产脚本：`.env` -> `.env.production` -> `.env.production.local`

## 本地启动

### 一键启动

开发模式：

```bash
cp .env.development.example .env.development.local
./scripts/start-dev.sh
```

生产模式：

```bash
cp .env.production.example .env.production.local
./scripts/start-prod.sh
```

停止服务：

```bash
./scripts/stop.sh
```

说明：

- 开发模式会同时启动后端 API、worker 和前端开发服务器
- 生产模式会先构建前端，再启动后端 API、worker 和前端生产服务
- 默认端口固定为：前端 `3100`，后端 `8100`
- 默认主机为：开发环境 `127.0.0.1`，生产环境 `0.0.0.0`
- 开发和生产默认不会共用同一个 SQLite 文件
- 如果存在对应的 `.env.*` 文件，启动脚本会自动加载
- 如果通过 `.env.*` 覆盖主机或端口，启动脚本会按覆盖值启动前后端服务

### 1. 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
QAEVALUATE_ENV=development python scripts/init_db.py
QAEVALUATE_ENV=development python scripts/seed_demo.py
QAEVALUATE_ENV=development uvicorn app.main:app --reload --port 8100
```

启动后可访问：

- 健康检查：`http://localhost:8100/health`
- Swagger：`http://localhost:8100/docs`

### 2. 启动 worker

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

如果只想处理一条任务：

```bash
python -m app.worker --once
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认地址：

- 前端：`http://localhost:3100`
- 后端：`http://localhost:8100`

## 导入验证

当前导入链路已经调整为“批次级指定项目、QA 类型、领域场景”，导入 JSON 本身只需要包含题目内容，例如：

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

本地服务启动后，可运行导入冒烟脚本验证整条链路：

```bash
QAEVALUATE_ENV=development python3 backend/scripts/smoke_import_batch.py
```

脚本会自动完成以下动作：

- 管理员登录
- 上传一批仅包含 `question / answer / context` 的 JSON 数据
- 在上传时绑定项目、QA 类型、领域场景
- 触发解析任务
- 校验批次状态、QA 入库结果和答案记录

## 示例账号

- 管理员：`admin / admin123`
- 专家：`expert01 / expert123`

## 当前限制

- LLM 依赖后台已配置并启用的 OpenAI 兼容模型配置
- 认证仍是轻量实现，未做更严格的安全策略
- 导出格式目前只支持 `JSON / JSONL`
- 生产化部署、日志、监控、备份等能力尚未接入

## 说明

- `docs/` 目录下的设计文档当前仅作为本地参考，已加入忽略规则，不纳入仓库跟踪
- 数据文件、导出结果、队列运行态文件也已通过 `.gitignore` 排除
- `seed_demo.py` 默认只允许在 `development` 环境执行，避免误向生产库写入测试数据
