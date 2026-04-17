# QA 评测平台

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

## 本地启动

### 1. 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_demo.py
uvicorn app.main:app --reload --port 8100
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

## 示例账号

- 管理员：`admin / admin123`
- 专家：`expert01 / expert123`

## 当前限制

- LLM 仍是示例 worker 逻辑，尚未接入真实模型
- 认证仍是轻量实现，未做更严格的安全策略
- 导出格式目前只支持 `JSON / JSONL`
- 生产化部署、日志、监控、备份等能力尚未接入

## 说明

- `docs/` 目录下的设计文档当前仅作为本地参考，已加入忽略规则，不纳入仓库跟踪
- 数据文件、导出结果、队列运行态文件也已通过 `.gitignore` 排除
