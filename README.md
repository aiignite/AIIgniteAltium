# AIDriveAltium · 大模型辅助硬件设计平台

通过 MCP / 离线解析双通道连接 Altium Designer 的大模型辅助硬件设计系统。
当前为**第一阶段**：平台前后端 + Altium 文件离线读取与查看。与运行中 Altium 的实时连接（DelphiScript 桥 + gateway MCP）为**第二步**。

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0 async + PostgreSQL(pgvector) + 隔离解析 worker（altium-monkey，子进程，ADR-002）
- 前端：React 19 + TypeScript + Vite + Mantine 9
- AI 引擎：多 provider（mock / OpenAI 兼容 / Anthropic）、技能注册表、SSE 流式对话、设计上下文注入

## 快速开始（本地）

```bash
# 1. 数据库（本机 PostgreSQL，也可用 docker compose up -d postgres）
createdb -U postgres aidrive_altium
# pgvector 可选（用于后续 RAG）：psql -U postgres -d aidrive_altium -c "CREATE EXTENSION IF NOT EXISTS vector"

# 2. 配置
cp backend/.env.example backend/.env   # 修改 DATABASE_URL 指向你的 PG

# 3. 一键启动
bash start.sh
```

- 前端：http://localhost:3290
- 后端 API 文档：http://localhost:3295/docs
- 默认管理员：`admin@example.com / admin123456`

## Docker 部署

```bash
docker compose up -d --build
```

## 功能（第一阶段）

| 功能 | 说明 |
|---|---|
| 用户认证 | JWT 注册/登录，启动自动创建管理员 |
| 工程文件 | 上传 .PrjPcb/.SchDoc/.PcbDoc（可多文件，无 PrjPcb 时自动合成工程） |
| 离线解析 | 隔离 worker 调用 altium-monkey：元件/网络(引脚级)/BOM/PCB 统计/板框/叠层 |
| 可视化查看 | 原理图 SVG、PCB SVG、元件表、网络表（含单端网络标记）、BOM 合并视图 |
| AI 对话 | 工作台对话，可选技能（原理图审查/PCB 审查/需求分析）与关联工程，设计上下文自动注入 |
| 模型管理 | 多 provider 配置（内置无需 Key 的演示引擎，支持 OpenAI 兼容/Ollama/Anthropic） |

## 已知问题

- 个别 Altium 文件（如本机 jlink_pcb.PcbDoc）存在嵌入字体损坏与非零板框原点，PCB SVG 视口计算异常（文字以占位框渲染、比例失真）；常规文件渲染正常
- 解析依赖 altium-monkey（AGPL-3.0）：以独立子进程隔离运行，详见 `docs/design/adr/ADR-002-altium-monkey-offline-engine.md`

## 设计文档

- [大模型最大程度辅助设计分析](docs/design/llm-max-assist-analysis.md)
- [ADR-001 语义描述到设计输出的执行路径](docs/design/adr/ADR-001-semantic-to-design-execution.md)
- [ADR-002 altium-monkey 离线引擎](docs/design/adr/ADR-002-altium-monkey-offline-engine.md)
- [模块开发规范](docs/design/module-conventions.md)

## 路线图

- **第二步**：altium-gateway（Windows + Altium）：DelphiScript 脚本桥 + MCP server + 连接管理
- 第三步：规则引擎（ERC/DRC/DFM）+ AI 审查报告 + RAG 知识库
- 第四步：元件选型/BOM 风险；第五步：写命令（意图命令层 + dry-run 确认 + 审计）
