# QA 评测平台

> 声明：这是一个实验性项目，当前主要用于原型验证、本地试运行和流程打磨，不应直接视为生产级系统。

这是一个面向 QA 对评测的数据平台，核心目标不是“做一个很重的标注系统”，而是借助 LLM，让专家更快完成 QA 对质量判断、答案修正和标准答案沉淀。

## 项目特点

- `LLM 辅助评测`：专家可以围绕问题和待评测答案，与模型持续对话，快速得到评价意见和修正版答案。
- `结构化评测`：专家主要做选择题式判断，而不是长篇论述，评测过程更稳定、更快。
- `轻量化架构`：后端使用 `FastAPI + SQLite`，缓存与队列基于文件目录，部署和迁移成本低。
- `面向训练数据生产`：支持导入大批量 QA，对答案进行多专家评审、聚合、沉淀，形成可继续用于模型训练的数据资产。
- `聚焦 QA 场景`：平台只做 QA 对评测，不额外引入复杂流程。

## 快速启动

开发环境：

```bash
cp .env.development.example .env.development.local
./scripts/start-dev.sh
```

生产环境：

```bash
cp .env.production.example .env.production.local
./scripts/prepare-prod.sh
./scripts/start-prod.sh
```

停止服务：

```bash
./scripts/stop.sh
```

更完整的启动、部署、环境隔离、导入验证和运行说明见 [DETAILS.md](/Users/kentnf/projects/ai4s/qaevaluate/DETAILS.md)。

## 示例账号

- 管理员：`admin / admin123`
- 专家：`expert01 / expert123`

## License

本项目采用 [MIT License](/Users/kentnf/projects/ai4s/qaevaluate/LICENSE)。
