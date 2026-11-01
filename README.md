# AIDriveAltium · 大模型辅助硬件设计平台

把 **Altium Designer 的设计数据**变成大模型可理解、可检索、可操作的上下文：离线文件解析 + 局域网实时桥 + 助手/技能编排 + 带确认的 AI 工具调用。

- **生产环境**：<https://www.aiignite.com.cn>（门户 → AIDriveAltium 卡片「启动」，或直达 [/altium/](https://www.aiignite.com.cn/altium/)）
- **GitHub**：https://github.com/aiignite/AIIgniteAltium （开源，欢迎 Issue / PR）
- **当前进度**：第一阶段（平台前后端 + Altium 文件离线读取/查看）与第二阶段（实时连接 + AI 工具链首版）均已完成，详见[路线图](#路线图)。
- **本地入口**：前端 `http://localhost:3340`（dev 与容器一致），后端 `http://localhost:3345/docs`（dev 与容器一致）。

```
┌──────────────────────┐   REST / SSE    ┌───────────────────────┐   REST   ┌────────────────────────┐
│ React 前端            │ ──────────────► │ FastAPI 后端           │ ───────► │ altium-gateway :3296    │
│ 工作台/工程/AI/连接    │                 │ AI 编排 · 解析 · 数据  │          │ Windows + Altium 机器   │
└──────────────────────┘                 └───────────┬───────────┘          └───────────┬────────────┘
                                                     │ 子进程（AGPL 隔离）               │ 文件乒乓（行式协议 v1）
                                                     ▼                                  ▼
                                       ┌───────────────────────┐            Altium 内 AIDriveBridge
                                       │ altium_files_worker   │            驻留脚本（TForm + TTimer）
                                       │ altium-monkey 解析渲染 │
                                       └───────────────────────┘
          PostgreSQL(+pgvector) / SQLite · Redis（预留）        MCP 客户端（Claude Desktop 等）──MCP──► gateway
```

## 功能总览

| 能力 | 状态 | 说明 |
|---|---|---|
| 用户认证 | ✅ | JWT（HS256）注册/登录，启动时幂等创建管理员 |
| 工程文件离线解析 | ✅ | 上传 `.PrjPcb/.SchDoc/.PcbDoc/.SchLib/.PcbLib`（也接受 `aidrive.snapshot.v0` JSON），隔离子进程解析为归一化快照 |
| 可视化查看 | ✅ | 原理图 SVG、PCB SVG、元件/网络/BOM 表格（搜索、分页、排序、单端网络标记、引脚明细） |
| AI 对话 | ✅ | 助手人设 + 技能提示词 + 设计上下文 + SSE 流式；对话历史持久化 |
| AI 配置中心 | ✅ | 独立页 `/ai-config`（模型 / 助手 / 技能三 Tab）；搜索筛选、卡片/列表双视图、连接测试、设默认、复制、导出 |
| 大模型配置 | ✅ | 5 类 provider（`mock` / OpenAI 兼容 / Ollama 原生 `/api/chat` / llama.cpp / Anthropic），采样参数（temperature/top_p/max_tokens）与能力开关（工具/图像）、一键预设模板；密钥加密落库、列表仅显示掩码；写操作默认限管理员 |
| AI 助手 | ✅ | 角色人设、系统提示词、开场白、推荐技能、工具子集、模型绑定与采样覆盖；支持复制与「预览系统提示词」；系统助手不可删 |
| 技能库 | ✅ | 任务级提示词模板 CRUD + 关键词打分编排（`POST /ai/skills/resolve`，含优先级加权与负向关键词）；可关联工具子集 |
| AI 工具调用 | ✅ | 拉取 gateway 工具清单动态注册，最多 5 轮工具循环；写操作必须先预览、再人工确认 |
| Altium 实时连接 | ✅ | 连接 CRUD/测试、实时摘要、实时截图、工作台右侧实时 PCB 面板 |
| 写命令（首版） | ✅ | 高亮网络 / 移动元件 / 旋转元件：`dry_run` 预览 → `confirmed` 执行 |
| MCP 服务 | ✅ | gateway 提供 stdio MCP server（8 个查询工具）；HTTP 方式需单独启动 |
| 规则引擎 / RAG / 选型 | 规划中 | 见[路线图](#路线图) |

## 系统架构

### 端口与地址

| 组件 | 本地开发 | 容器 / 生产 | 说明 |
|---|---|---|---|
| 前端（Vite / nginx） | **3340** | **3340** → 容器 `80` | 门户子路径 `/altium/`；`vite.config.ts` 固定 dev 端口 3340 |
| 后端（FastAPI） | **3345** | **3345** → 容器 `3345` | 业务前缀 `/api/v1`，文档 `/docs` |
| altium-gateway | **3296** | — | 部署在装有 Altium 的 Windows 机器 |
| PostgreSQL | `5432` | `5433` → `5432` | Docker 用 `pgvector/pgvector:pg16` |
| Redis | — | `6380` → `6379` | 依赖已编排，业务代码暂未使用 |
| SQLite | `backend/aidrive_altium.db` | — | 仓库内 `backend/.env` 当前使用，免数据库快速体验 |

> **端口口径**：自 2026-10-18 起开发态、容器、生产**统一为 3340/3345**，不再区分 dev 与生产端口（`vite.config.ts`、`backend/Dockerfile`、`frontend/nginx.conf`、`docker-compose.yml` 保持一致）。`docs/design/phase1-completion-audit.md` 中的 3290/3295 为当时的审计记录，保留为历史事实。

### 分层职责

- **前端**：React 19 + Mantine 9，单页应用（对话工作台、AI 配置、工程文件、Altium 连接、设置）。
- **后端**：模块化单体，按功能域分组（`system / ai / files / altium`），统一 `/api/v1` 前缀；AI 编排、文件解析调度、连接代理都在这一层。
- **解析 worker**：独立子进程，只 import `altium_monkey`，与后端通过 `job.json → result.json` 交换（AGPL 隔离，见 [ADR-002](docs/design/adr/ADR-002-altium-monkey-offline-engine.md)）。
- **gateway**：命令层（语义命令 → 桥 ops）+ 驱动层（mock / 文件乒乓）+ REST + MCP，部署在 Altium 机器上。
- **桥脚本**：Altium 内 DelphiScript 驻留窗口，轮询 `Documents\AltiumBridge\requests`，按行式协议回写 `responses`。

### 技术栈

- 后端：FastAPI、SQLAlchemy 2.0 async、Pydantic v2、python-jose + bcrypt、httpx、`altium-monkey>=2026.9`
- 前端：React 19、TypeScript、Vite、Mantine 9、Tabler Icons、react-router 7、oxlint
- 数据：PostgreSQL 16 + pgvector（生产）/ SQLite（本地兜底）
- 网关：FastAPI、uvicorn、httpx、`mcp`（FastMCP）、Pillow；DelphiScript 桥脚本

## 目录结构

```
AIDriveAltium/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 # 应用装配、启动引导（建表/管理员/mock 模型/种子）
│  │  ├─ config.py               # 环境变量配置（.env）
│  │  ├─ database.py             # async engine / session
│  │  ├─ schemas.py              # CamelModel（响应 camelCase）
│  │  ├─ security.py             # JWT 与密码哈希
│  │  ├─ modules/<group>/        # 路由注册入口（ALL_MODULES）
│  │  ├─ routers/{system,ai,files,altium}/
│  │  ├─ services/{ai,files,altium}/
│  │  │  ├─ ai/orchestrator.py   # 提示词组装、工具循环、SSE 事件
│  │  │  ├─ ai/providers/        # provider 包：base / openai_compat / ollama(原生 /api/chat) / llamacpp / anthropic / mock / factory
│  │  │  ├─ ai/llm_router.py     # 模型解析：请求 → 会话 → 助手 → 默认 → 兜底
│  │  │  ├─ ai/secret_crypto.py  # API Key Fernet 加密（enc:v1:）+ 掩码
│  │  │  ├─ ai/model_probe.py    # 连接测试与错误归类（含私网地址防护）
│  │  │  ├─ ai/seed_data.py      # 技能 / 助手 / 模型模板幂等补种
│  │  │  ├─ ai/design_context.py # 快照/实时摘要 → 上下文文本
│  │  │  ├─ files/parse_service.py
│  │  │  └─ altium/gateway_client.py
│  │  ├─ ai_tools/__init__.py    # ToolRegistry + gateway 工具同步
│  │  ├─ worker/altium_files_worker.py
│  │  ├─ models/{system,ai,altium,files}/
│  │  └─ database_patches.py     # 过渡期幂等补列（PG，含 AI_PLATFORM_STATEMENTS）
│  ├─ scripts/migrate_ai_platform.py  # AI 平台迁移独立重放入口（幂等，可反复执行）
│  ├─ requirements.txt
│  ├─ Dockerfile                 # 容器内监听 3345
│  └─ .env.example
├─ frontend/
│  ├─ src/pages/                 # Workbench / Projects / ProjectDetail / AIConfigPage / Connections / Settings / Login
│  ├─ src/pages/ai/              # ModelsPanel / AssistantsPanel / SkillsPanel
│  ├─ src/components/            # AppLayout、DesignDataTabs、ai/*（ModelPicker、ToolChipSelect…）
│  ├─ src/api/client.ts          # REST + SSE 客户端
│  ├─ nginx.conf                 # 子路径与 API 反代、SSE 关闭缓冲
│  ├─ vite.config.ts
│  └─ Dockerfile
├─ gateway/
│  ├─ altium_gateway/
│  │  ├─ app.py                  # REST（:3296）
│  │  ├─ commands.py             # 命令注册表 + dry-run + 确认
│  │  ├─ protocol.py             # 行式协议 v1 编解码
│  │  ├─ drivers/{base,mock,file_bridge}.py
│  │  └─ mcp_server.py           # stdio MCP server
│  ├─ altium_scripts/AIDriveBridge.*   # DelphiScript 驻留脚本（.PrjScr）
│  ├─ deploy/{install.bat,start_gateway.bat}
│  ├─ tests/test_protocol_mock.py      # 12 个协议/命令/mock 用例
│  └─ README.md
├─ docs/design/                  # 设计分析、ADR、模块规范、阶段审计
├─ scripts/                      # deploy-remote.sh、deploy.env.example
├─ screenshots/                  # 调试/联调截图统一归档（内容不入库，仅保留 README）
├─ test/                         # 手动联调/排障脚本（非自动化测试，清单见 test/README.md）
├─ docker-compose.yml
├─ start.sh                      # macOS/Linux 一键启动（bash）
└─ CLAUDE.md                     # 工程约定速览
```

## 仓库结构

```
AIDriveAltium/
├── backend/                  # FastAPI 后端 :3345
│   └── app/
│       ├── main.py           # lifespan + 启动建表/补种助手技能/管理员
│       ├── config.py         # Pydantic Settings
│       ├── database.py       # SQLAlchemy 2.0 async + async_session_maker
│       ├── database_patches.py  # 演进期的幂等补列
│       ├── schemas.py        # CamelModel（snake → camel 自动 alias）
│       ├── security.py       # JWT + bcrypt + get_current_user
│       ├── modules/          # 模块化单体入口注册表（system|ai|files|altium）
│       │   └── {group}/__init__.py::register_routers
│       ├── models/           # ORM 模型（按域目录分组，import 走 {group}/）
│       ├── routers/          # FastAPI APIRouter（按域目录分组）
│       ├── services/         # 业务逻辑层（编排器/技能解析/上下文构建/AI providers）
│       ├── ai_tools/         # 工具注册表（PLM PageAI 约定，逐步接入）
│       └── worker/           # 离线解析 worker 入口（独立子进程，仅 import altium_monkey）
├── frontend/                 # React 前端 :3340（门户子路径 /altium/）
│   ├── src/
│   │   ├── App.tsx           # 路由（React.lazy）
│   │   ├── pages/            # LoginPage/ProjectsPage/WorkbenchPage/
│   │   │                       ProjectDetailPage/AssistantsPage/ConnectionsPage/SettingsPage
│   │   ├── components/ai/    # AssistantAvatar/Picker/SkillActivationCard
│   │   ├── components/DesignDataTabs.tsx  # 设计数据 Tab 容器
│   │   └── api/client.ts     # buildQuery（snake_case key）
│   └── nginx.conf            # /altium/ 反代到 :3345 backend
├── gateway/                  # 实时网关 :3296（部署在 Windows+Altium 机）
│   └── altium_gateway/
│       ├── app.py            # FastAPI 网关（/health /tools /command /live/summary /mcp）
│       ├── commands.py       # 意图命令层注册表（v1: 8 只读查询）
│       ├── mcp_server.py     # 把命令层封装为 MCP tools（stdio/HTTP）
│       ├── protocol.py       # 行式文件乒乓协议 encode_request / parse_response
│       ├── config.py         # mode (live|mock) + bridge_dir + op_timeout
│       └── drivers/
│           ├── base.py           # AltiumDriver 接口
│           ├── file_bridge.py    # live：req_/resp_ 文件乒乓
│           └── mock.py           # mock：测试/无 Altium 联调
├── altium_scripts/          # gateway/ 内的 DelphiScript 驻留脚本
│   └── AIDriveBridge.PrjSrc # Altium 内 RunAIDriveBridge 启动桥
├── scripts/                  # 部署与运维
│   ├── deploy-remote.sh      # rsync + docker compose 一键部署
│   ├── deploy.env(.example)  # SSH/路径/容器编排配置
│   └── start.sh              # 本地一键启动（建 venv/建表/创管理员）
├── docs/design/              # 设计文档（ADR 与审计报告）
├── docker-compose.yml        # pgvector/pg16 + redis + backend(:3345) + frontend(nginx :3340)
└── CLAUDE.md                 # 工程约定速览
```

## 关键技术亮点

| 维度 | 方案 | 关键文件 |
|---|---|---|
| 模块化单体 | 按功能域分组（`system\|ai\|files\|altium`），`register_routers(app)` 统一注册；表前缀 `sys_/ai_/alt_/rvw_/cmp_/bom_/knw_/fls_` | `app/modules/__init__.py`、`docs/design/module-conventions.md` |
| 离线解析合规 | `altium-monkey`（AGPL-3.0）跑独立 worker 子进程，**不**在后端进程内 import；job.json → result.json 协议 | `backend/app/worker/altium_files_worker.py`、`ADR-002` |
| 写路径铁律 | LLM → 意图命令层 → 命令执行器 → 文件乒乓桥 → DelphiScript；**文件直改仅限受控例外**（ADR-001） | `gateway/altium_gateway/commands.py`、`ADR-001` |
| AI 编排 | `BASE_PROMPT + 助手人设 + 技能提示词 + 设计上下文` 四段拼 system prompt；SSE 流式 + `meta/skills_activated/delta/error/done` 五类事件 | `backend/app/services/ai/orchestrator.py` |
| 技能匹配评分 | 关键词命中 15/技能名 40/code 50/助手绑定 10，阈值 15，Top-3；可手动增删 | `backend/app/routers/ai/skills.py`、`app/services/ai/seed_data.py` |
| 设计上下文 | 离线快照取「25 元件 + 30 网络 + 12 BOM 行 + 板框」压成紧凑文本，标记单端可疑网络；未选工程时自动注入实时摘要 | `backend/app/services/ai/design_context.py` |
| 实时连接 | gateway 7 只读语义命令 + 截图，**同一组命令封装为 MCP server**（stdio + HTTP 双入口） | `gateway/altium_gateway/{app,commands,mcp_server}.py` |
| 协议隔离 | Altium↔gateway 用 `%USERPROFILE%\Documents\AltiumBridge\requests\|responses` 目录 req_/resp_ 文件乒乓；UUID + 5min 心跳 | `gateway/drivers/file_bridge.py`、`gateway/protocol.py` |
| 助手/技能可配 | 启动幂等补种 4 助手 + 4 技能（不覆盖用户修改）；系统技能不可删改 code，系统助手不可删 | `app/services/ai/seed_data.py` |
| API 一致性 | 响应 camelCase（`CamelModel` alias）；列表端点 `{items,total}`；前端 `buildQuery` key 用 snake_case | `app/schemas.py`、`frontend/src/api/client.ts` |

## REST API 速览

| 域 | 端点 | 说明 |
|---|---|---|
| 系统 | `POST /auth/register`、`POST /auth/login`、`GET /auth/me` | JWT 认证 |
| 工程 | `POST /files/projects`（上传+触发解析 worker）、`GET /files/projects/page`、`GET /files/projects/{id}` | 离线解析入库 |
| 设计数据 | `GET /files/projects/{id}/schematic.svg`、`GET /files/projects/{id}/pcb.svg`、`GET /files/projects/{id}/nets`、`GET /files/projects/{id}/bom` | 元件/网络/BOM/板框/叠层 |
| AI | `POST /ai/chat/stream`（SSE）、`/ai/skills(CRUD)`、`POST /ai/skills/resolve`、`/ai/assistants(CRUD)`、`GET /ai/assistants/default` | 流式对话 + 技能解析 + 助手 |
| 模型 | `/ai/models(CRUD)`、`POST /ai/models/{id}/test` | mock/OpenAI/Anthropic 多 provider |
| 连接 | `POST /altium/connections`、`POST /altium/connections/{id}/test`、`GET /altium/connections/{id}/live-summary` | Altium gateway 接入 |
| gateway（:3296） | `GET /health`、`GET /tools`、`POST /command/{name}`、`GET /live/summary`、`GET /screenshot`、`POST /mcp` | 命令层 + MCP 流式 HTTP |

完整 OpenAPI 文档见 `http://localhost:3345/docs`。

## 架构设计决策（ADR）

| 编号 | 题目 | 关键决策 |
|---|---|---|
| [ADR-001](docs/design/adr/ADR-001-semantic-to-design-execution.md) | 语义描述到设计输出的执行路径 | 写操作 100% 走 DelphiScript 脚本桥（活会话、可撤销、自动维护派生数据）；LLM 只面对结构化意图命令层，不做几何；文件直改仅受控例外（新建库/模板/离线生成产物） |
| [ADR-002](docs/design/adr/ADR-002-altium-monkey-offline-engine.md) | 采用 altium-monkey 作为离线引擎（含 AGPL 合规） | 独立 worker 进程隔离（聚合而非衍生）；实时写路径不受影响；PcbDoc 删除 API 成熟后再评估扩大离线写范围 |

补充文档：[大模型最大程度辅助设计分析](docs/design/llm-max-assist-analysis.md)、[模块开发规范](docs/design/module-conventions.md)、[第一阶段完成度审计](docs/design/phase1-completion-audit.md)。

---

## 快速开始

### 方式一：Docker Compose（含数据库，最接近生产）

```bash
docker compose up -d --build
```

> Compose 已为后端注入数据库地址、`SECRET_KEY` 与管理员账号；如需改端口或密钥，直接编辑 `docker-compose.yml`。

启动内容：`pgvector/pg16` + `redis` + 后端（宿主 `3345`）+ 前端（宿主 `3340`，nginx 反代 `/api`、SSE 关闭缓冲、上传上限 100MB）。

- 前端：<http://localhost:3340/>（门户方式访问 `/altium/`）
- API 文档：<http://localhost:3345/docs>
- 默认管理员：`admin@example.com / admin123456`（首次启动自动创建）

### 方式二：本地开发（macOS / Linux）

```bash
# 1) 数据库（二选一）
# A. 本机 PostgreSQL + pgvector
brew install postgresql@17 && brew services start postgresql@17
createdb -U postgres aidrive_altium
psql -U postgres -d aidrive_altium -c "CREATE EXTENSION IF NOT EXISTS vector"

# B. 仅数据库用 Docker
docker compose up -d postgres redis
# DATABASE_URL=postgresql+asyncpg://aidrive:aidrive_altium_dev@localhost:5433/aidrive_altium

# 2) 后端
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env      # 修改 DATABASE_URL
cd backend && ../.venv/bin/python -m uvicorn app.main:app --port 3345 --reload

# 3) 前端（新终端）
cd frontend
npm install
npm run dev                                # http://localhost:3340
```

`bash start.sh` 会建 venv、检查数据库、启动前后端（3345/3340，与 `vite.config.ts` 一致）。

### 方式三：本地开发（Windows PowerShell）

```powershell
# 1) 依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 2) 配置（默认 SQLite，可省去 PostgreSQL）
Copy-Item backend\.env.example backend\.env
# 修改 backend\.env：DATABASE_URL=sqlite+aiosqlite:///./aidrive_altium.db

# 3) 后端（终端 A）
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 3345 --reload

# 4) 前端（终端 B）
Set-Location frontend
npm install
npm run dev        # http://localhost:3340
```

> SQLite 模式下 `database_patches.ensure_extra_columns` 的 PG 语句会被跳过；首次建表由 `create_all()` 完成，功能不受影响（pgvector 仅后续 RAG 需要）。

### 首次使用

1. 打开前端 → 用默认管理员登录（或注册新账号）。
2. 「工程文件」→ 上传 Altium 工程文件 → 后台解析 → 查看原理图/PCB/元件/网络/BOM。
3. 「AI 配置」→「大模型」→ 新增模型（可用预设模板一键填 Base URL 与模型名）→ 填入 API Key → 测试连接 → 设为默认；列表只显示密钥掩码。**未配置任何模型时对话仍可用内置 mock 引擎。**
4. 「AI 配置」→「助手 / 技能」→ 调整人设、系统提示词、推荐技能与技能提示词；助手可绑定模型并覆盖温度 / 最大 Tokens。
5. 「对话工作台」→ 选择助手、关联工程、按需勾选技能 → 提问。
6. 「Altium 连接」→ 填写网关地址（如 `http://192.168.1.14:3296`）→ 测试连接 → 实时面板。
7. 连接在线时，工作台右侧自动显示 Altium 当前 PCB，并可直接让 AI 执行只读/写命令。

## 配置参考

### 后端 `backend/.env`

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/aidrive_altium` | SQLite 可写 `sqlite+aiosqlite:///./aidrive_altium.db` |
| `SECRET_KEY` | `dev-secret-change-me-in-production` | JWT 签名密钥，生产必须替换 |
| `ADMIN_EMAIL` | `admin@example.com` | 启动时若不存在则创建 |
| `ADMIN_PASSWORD` | `admin123456` | 同上；生产必须替换 |
| `ADMIN_BOOTSTRAP_RESET_PASSWORD` | `false` | 为 `true` 时每次启动重置管理员密码 |
| `DATA_DIR` | `./data` | 上传文件与 SVG 渲染产物根目录（容器内 `/data`） |
| `JWT_EXPIRE_DAYS` | `7` | Token 有效期 |
| `GATEWAY_URL` | `http://localhost:3296` | 预留项，当前连接地址以数据库中的连接记录为准 |
| `AI_SECRET_KEY` | 空 | API Key 加密密钥；留空时由 `SECRET_KEY` 派生（换此值会使已存密钥无法解密） |
| `AI_CONFIG_WRITE_ADMIN_ONLY` | `true` | 为 `true` 时模型配置的增删改与连接测试仅管理员可用（聊天不受限） |
| `AI_MODEL_TEST_TIMEOUT` | `8.0` | 「测试连接」超时（秒） |
| `AI_ALLOW_PRIVATE_MODEL_HOSTS` | `true` | 是否允许本地/私网地址（ollama / llama.cpp 必需）；云端 provider 填私网地址会被拒绝 |
| `AI_DEFAULT_TEMPERATURE` / `AI_DEFAULT_MAX_TOKENS` | `0.4` / `4096` | 新建模型配置时的默认采样参数 |

> `backend/.env.example` 目前只列了前 5 个变量，其余按需手写。

### 网关环境变量（Windows 机器）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ALTIUM_MODE` | `mock` | `mock` 内置演示数据；`live` 走文件乒乓桥 |
| `ALTIUM_BRIDGE_DIR` | `%USERPROFILE%\Documents\AltiumBridge` | 与 DelphiScript 共享的请求/响应目录 |
| `GATEWAY_PORT` | `3296` | 监听端口 |
| `GATEWAY_HOST` | `0.0.0.0` | 监听地址 |
| `GATEWAY_TOKEN` | 空 | 设置后除 `/health` 外都要求 `Authorization: Bearer <token>` |
| `ALTIUM_OP_TIMEOUT` | `20` | 单次桥事务超时（秒） |

### 前端

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_BASE_PATH` | `/` | 门户子路径部署时设为 `/altium/`，API 随之走 `/altium/api/v1` |

## 核心机制

### 1. 离线解析（ADR-002）

- 上传后由 `parse_service` 落盘到 `DATA_DIR/uploads/<projectId>`，再以 `asyncio.to_thread` 启动独立 worker。
- worker 协议：`argv[1] = job.json`（`jobId/projectDir/outDir/renderSvg/projectName`）→ `outDir/result.json`；产物含 `snapshot`、`svgManifest`、`design.json`。
- 快照 schema：`aidrive.snapshot.v0`，字段包括 `project/documents/stats/components/nets/bom/pcbs/warnings`；网络带引脚级 `terminals`。
- 兼容性：无 `PrjPcb` 时自动合成 `_synthesized.PrjPcb`；原理图编译/设计 JSON/BOM/PCB 各自 `try/except` 降级，失败写入 `warnings`。
- PCB 渲染降级链：`PcbSvgRenderOptions(allow_text_geometry_fallback=True)` → `to_board_outline_svg()`（板框兜底）。
- 也支持直接上传 `aidrive.snapshot.v0` JSON 作为快照，跳过解析（便于外部工具接入）。
- 快照渲染 id 强制 ASCII（`sch_*` / `pcb_*`），与 `/svgs/{svgId}` 的 `[A-Za-z0-9_-]+` 校验对齐。

### 2. AI 编排与技能

- 系统提示词 = `BASE_PROMPT` + 助手人设 + 命中技能提示词 + 设计上下文（`orchestrator.compose_system_prompt`）。
- 上下文双通道：关联工程时注入离线快照摘要，关联实时连接时注入该连接的实时摘要；两者都**只给概览 + 与提问命中的对象**，明细由查询工具按需拉取（见 3.2）。未关联工程/连接就不注入对应数据，不再「自动取第一条 `connected` 网关」。
- 上下文预算：单次注入默认不超过 6000 字符，超出时按「概览 → 命中项 → 网络 → BOM」优先级裁剪并标注截断提示。
- 技能编排打分：`code` 命中 50、技能名 40、每个关键词 15、助手绑定 10、技能优先级 0–10；`extra_config.negative_keywords` 命中扣 40（避免近义技能互相误命中）；阈值 15，默认 Top-3。
- 历史窗口 20 条消息；会话与消息入库，SSE 事件回显激活技能与工具调用。
- 模型解析五层：请求 `modelConfigId` → 会话绑定 → 助手绑定 → 系统默认 → 首个可用配置；候选会跳过已停用/软删、以及需要密钥却未配置密钥的 provider；无可用模型时抛 `NoAvailableModelError`（SSE `code=no_model`），前端给「去配置模型」入口。
- 工具裁剪：仅当模型 `supportsTools=true` 时注入 tools，并按「助手 `tool_codes` ∪ 各技能 `tool_codes`」取交集；空集合 = 全部。
- SSE 事件：`meta`（含 `provider` / `modelName` / `resolution`）、`skills_activated`、`delta`、`tool_call`、`tool_result`、`tool_confirmation_required`、`error`（含 `code`）、`done`（含 `durationMs` 与 `usage`）。

### 3. AI 工具调用与写操作确认

1. 每轮对话按**会话上下文**（`ToolContext`：用户 + 对话关联的连接/工程）执行 `sync_gateway_tools()`，从该连接的 `/tools` 拉取清单并按连接注册进 `ToolRegistry`（幂等；连接命令增删或下线时替换/清除旧工具，不留残留）。
2. 网关工具只对同一连接的会话可见、可执行；未关联连接的对话不会「挑一条在线连接」兜底，模型也无法用参数指定地址或令牌。连接的修改/删除会同步清掉其注册工具。
3. 模型以 function calling 选择工具；同一轮内的多个**只读**工具并发执行（`asyncio.gather`），含写工具时按顺序执行并回喂结果，最多 5 轮。
4. 写工具（`requires_confirmation=true`）由后端**先自动 dry-run**，产出预览并推送 `tool_confirmation_required`；本轮结果标记 `requiresConfirmation` 回喂模型。
5. 前端渲染确认卡（工具名 + 预览 + 参数）：点「确认执行」调用 `POST /altium/connections/{id}/command`（`confirmed=true` + 随机 `requestId` 幂等键），执行成功且可逆时展示「撤销这次修改」。
6. 工具执行日志随助手消息落库（`meta.toolLog`），历史对话回放仍可见；对话可经 `GET /ai/conversations/{id}/export.md` 导出 Markdown（含工具调用明细）。
7. 工具结果统一 `{"success": bool, ...}` 信封，异常不中断对话。

### 3.2 设计数据查询工具（渐进披露第二层）

系统提示词只放概览，明细由模型按需查询，避免整板数据入 prompt：

| 工具 | 数据来源 | 用途 |
|---|---|---|
| `find_components` | 离线快照 | 按位号/值/封装过滤，支持「缺封装/缺值」筛选 |
| `get_component` | 离线快照 | 单个元件的属性 + 所在网络引脚 + 对应 BOM 行 + 单端网络 |
| `find_nets` | 离线快照 | 按网络名片段与端子数过滤（`max_terminals=1` 找悬空网络） |
| `get_net` | 离线快照 | 单个网络的引脚级完整连接，未命中时给相近网络提示 |
| `get_bom_rows` | 离线快照 | 按位号/值/封装/DNP 过滤 BOM 行 |
| `get_review_findings` | 最近一次审查，缺省即时计算 | 按规则/级别/位号取确定性审查结论 |
| `altium_find_components` / `altium_find_nets` | 实时连接 | 在打开的 Altium 设计里做同样的过滤查询，复用既有桥操作 |

查询工具一律限定在当前对话关联的工程/连接并按所有者校验，返回 `matched / returned / truncated / hint` 信封，默认 20 条、上限 60 条。

### 3.1 写命令审计、幂等与撤销

- 仅对用户确认的 `altium_*` 写命令落审计表 `alt_command_audits`（执行人/连接/命令/参数/执行前状态/结果/状态/错误）。
- `requestId` 为幂等键：同一连接重复提交直接重放首次结果（`replayed=true`），不会二次执行。
- 移动/旋转元件在确认前用 dry-run 捕获原始位姿；`POST /altium/connections/{id}/commands/audit/{auditId}/undo` 生成确定性逆命令回滚，并新增一条 undo 审计（`undoOfId`）。执行前状态缺失时该记录不可撤销（`canUndo=false`）。
- 撤销前先复核当前位姿：若该命令之后设计又被改动（坐标/角度与执行后不一致），返回 **409** 并列出差异，不覆盖后续修改；逆命令执行失败时审计保持 `executed`、`canUndo=true`，可再次撤销。
- **写后即查（Post-Action Verification）**：写命令返回 `ok` 后，用 dry-run 读回受影响对象状态并与命令目标参数做一致性核验，结果内嵌审计 `result.verification`（`checked/ok/expected/actual/issues`）。回读不一致时不轻信 gateway 成功回执，审计标记 `verifyFailed=true`，前端在状态列显示「写后即查·未通过」并列出差异；这些失败项会回喂到下一轮 AI 对话上下文，提示复查或撤销。无状态可回读的命令（如高亮）返回 `checked=false`，不产生误报。撤销本身也是写操作，同样回读确认已恢复。这是 ADR-001 / 辅助级别 L2→L3 的验证门槛。
- 实时面板可将当前 Altium 设计与离线快照按位号/网络对比（`GET /altium/connections/{id}/drift?projectId=`），差异汇总可一键交给 AI 解读。
- 仍无跨命令事务回滚：撤销按单条命令回滚，不保证多条写命令的原子性（ADR-001 后续目标）。

### 4. 实时连接（gateway + DelphiScript 桥）

- 两种模式：`ALTIUM_MODE=mock`（默认，无 Altium 也能联调）与 `live`（文件乒乓）。
- 桥协议 v1（行式文本，避免 DelphiScript 侧 JSON 解析）：请求 `OP|<op>|k=v...` + `END|<id>`；响应 `RES|<idx>|OK|ITEM|ERR|...` + `END|<id>`。
- 传输使用**固定文件名** `requests/request.txt`、`responses/response.txt`，规避 DelphiScript 目录枚举问题；驱动内置 20s 超时与陈旧响应清理。
- 截图：桥端受 DLL 声明限制无法 GDI 截图，gateway 回退为 PowerShell + `PrintWindow` 截取 Altium 主窗口；仍失败则返回占位 SVG。

**命令清单（13 个：10 只读（含 2 条语义查询）+ 3 写）**

| 命令 | 类型 | 说明 |
|---|---|---|
| `altium_ping` | 只读 | 桥连通性（PONG） |
| `altium_get_project_info` | 只读 | 当前工程名称/路径/活动文档 |
| `altium_get_schematic_components` | 只读 | 当前原理图元件（位号/值/封装） |
| `altium_get_schematic_nets` | 只读 | 当前原理图网络与连接计数 |
| `altium_get_pcb_components` | 只读 | PCB 元件、层、坐标、旋转角 |
| `altium_get_pcb_stats` | 只读 | 元件/焊盘/走线/过孔/网络/板框/层数 |
| `altium_get_stackup` | 只读 | 板层名称列表 |
| `altium_take_screenshot` | 只读 | 当前文档画面（live 下 BMP→PNG） |
| `altium_find_components` | 只读（过滤） | 在原理图/PCB 中按位号/值/封装查询元件，支持 `limit` |
| `altium_find_nets` | 只读（过滤） | 按网络名片段与端子数查询网络，支持 `limit` |
| `altium_highlight_net` | 写（需确认） | 高亮/取消高亮网络（仅视觉） |
| `altium_move_component` | 写（需确认） | 按位号移动元件到坐标（mils） |
| `altium_rotate_component` | 写（需确认） | 按位号旋转元件（0–360°） |

**gateway REST**

| 端点 | 说明 |
|---|---|
| `GET /health` | 状态、模式、桥目录、Altium 是否在线、命令数 |
| `GET /tools` | 命令清单（含 `category` / `requiresConfirmation` / `paramsSchema`） |
| `POST /command/{name}` | 执行命令；写命令需 `dry_run` 或 `confirmed` |
| `GET /live/summary` | 聚合实时摘要（LLM 上下文用） |
| `GET /screenshot` | 当前窗口截图（PNG，失败为占位 SVG） |
| `GET /mcp` | **未挂载**；MCP 请用 stdio 入口或 `mcp_server --http` 单独启动 |

**MCP 客户端接入（Claude Desktop / ZCode）**

```json
{
  "mcpServers": {
    "altium": { "command": "D:\\altium-gateway\\.venv\\Scripts\\altium-gateway-mcp.exe" }
  }
}
```

## API 一览（后端 `/api/v1`）

| 分组 | 端点 |
|---|---|
| 认证 | `POST /auth/register`、`POST /auth/login`、`GET /auth/me` |
| 工程 | `GET/POST /files/projects`、`GET/DELETE /files/projects/{id}`、`POST /files/projects/{id}/reparse` |
| 工程数据 | `GET /files/projects/{id}/components`、`/nets`、`/nets/{net}`、`/bom`、`/svgs`、`/svgs/{svgId}` |
| 对话 | `POST /ai/chat/stream`（SSE）、`GET /ai/conversations`、`GET /ai/conversations/{id}/messages`、`GET /ai/conversations/{id}/export.md`、`DELETE /ai/conversations/{id}` |
| 模型 | `GET/POST /ai/models`、`PUT/DELETE /ai/models/{id}`、`GET /ai/models/providers`、`GET /ai/models/export?format=json\|csv`、`POST /ai/models/test`、`POST /ai/models/{id}/test`（别名 `/test-connection`）、`POST /ai/models/{id}/default`、`POST /ai/models/{id}/duplicate` |
| 技能 | `GET/POST /ai/skills`、`PUT/DELETE /ai/skills/{id}`、`POST /ai/skills/resolve`、`POST /ai/skills/{id}/duplicate` |
| 助手 | `GET/POST /ai/assistants`、`PUT/DELETE /ai/assistants/{id}`、`POST /ai/assistants/{id}/default`、`POST /ai/assistants/{id}/duplicate`（别名 `/clone`）、`POST /ai/assistants/{id}/prompt-preview` |
| AI 工具 | `GET /ai/tools/registry`（工具选择器数据源；带 `?connectionId=` 时只返回该连接会话可用的工具） |
| 实时连接 | `GET/POST /altium/connections`、`POST /{id}/test`、`POST /{id}/command`、`GET /{id}/live/summary`、`GET /{id}/screenshot`、`GET /{id}/commands/audit`、`POST /{id}/commands/audit/{auditId}/undo`、`GET /{id}/drift?projectId=`、`DELETE /{id}` |
| 健康检查 | `GET /health` |

约定：响应统一 camelCase（`CamelModel`），请求同时接受 camelCase / snake_case；工程数据的分页端点返回 `{items, total}`；业务实体软删（`is_deleted`）。

## 测试

```powershell
# gateway：协议编解码、命令注册表、dry-run/确认、mock 驱动
cd gateway
.\.venv\Scripts\python.exe -m pytest -q      # 12 passed

# AI 平台自检（无需数据库）：端点 / 模型与助手技能新增列 / 迁移语句 / 密钥加密 / provider 注册表 / SSRF 策略
cd ..\backend
..\.venv\Scripts\python.exe -B ..\test\check_ai_platform.py    # 12 passed

# AI 平台端到端冒烟（临时 SQLite，不依赖 PostgreSQL）：登录 → 工具注册表 → 模型 CRUD/测试/导出/默认 → 技能解析 → 提示词预览 → SSE 对话落库
cd ..
.\.venv\Scripts\python.exe -B test\smoke_ai_platform.py         # 20 passed
```

- 前端检查：`cd frontend && npm run lint && npm run build`（`tsc -b` + Vite 构建）。
- 后端 pytest（需隔离 PostgreSQL，测试内自动建 schema 并 `alembic upgrade head`）：`cd backend && TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:<port>/<db> pytest -q`，当前 **148 passed**（含迁移基线校验、写命令审计/幂等/撤销冲突、写后即查回读核验、失败核验回喂上下文、漂移、对话导出、工具日志与并发只读工具、工具执行上下文与连接隔离、快照查询工具、上下文预算）。
- 审查规则金标准评测（纯离线、无需数据库）：`cd backend && pytest tests/test_review_evals.py -q`，**5 passed**（缺陷板查全率 100%、干净板零误报、规则不误触发、命中项带 refs/severity、`summarize` 计数一致）。见 [docs/evals/README.md](docs/evals/README.md)。
- gateway pytest：`cd gateway && pytest -q`，当前 **15 passed**（协议、mock 驱动状态、写命令 dry-run/confirmed、过滤查询、文件桥）。
- 脚本清单见 [test/README.md](test/README.md)。
- 其余后端逻辑（worker 协议、快照结构、文件解析）尚无 pytest 覆盖，建议作为下一步基线（见已知限制）。

## 部署到服务器

```bash
cp scripts/deploy.env.example scripts/deploy.env   # 填 HOST / USER / PATH
bash scripts/deploy-remote.sh                      # rsync + 远程 compose 构建启动 + 健康检查
```

脚本会排除 `node_modules/.venv/data/backend/.env/gateway` 等目录，首次部署自动生成远程 `backend/.env`（随机 `SECRET_KEY`）。

## 已知限制与待办

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | ~~`start.sh` 3345/3340 与 `vite.config.ts` 3290/3295 不一致~~ **已修复（2026-10-18）** | — | 端口统一为 3340/3345（dev/容器/生产一致），见[端口与地址](#端口与地址) |
| 2 | ~~无 Alembic 迁移（启动 `create_all` + PG 补列）~~ **已修复** | — | Alembic 0001–0006；启动校验数据库版本与 head 一致，旧库走严格基线采纳（结构不一致即拒绝启动） |
| 3 | ~~AI API Key 明文存储且原样回显~~ **已修复** | — | Fernet（`enc:v1:`）加密落库，响应只给 `hasKey` / `keyHint`，历史明文启动时自动升级 |
| 4 | ~~写命令无审计、撤销、事务回滚、幂等键~~ **部分修复（2026-10-30）** | 单命令可审计/幂等/撤销；跨命令事务回滚仍缺失 | 审计表 `alt_command_audits` + `requestId` 幂等 + 确定性逆命令撤销；后续补事务边界 |
| 5 | 网关 `/mcp` 未挂载（仅文档字符串提及） | 无法用 REST 端口连 MCP | 在 `app.py` 挂载 FastMCP ASGI，或只用 stdio |
| 6 | `GET /api/v1/health` 的 `gatewayEnabled` 恒为 `false` | 该字段不代表实时状态 | 改查 `alt_connections` 或删除该字段 |
| 7 | `design_context` 中板框尺寸除以 1000 却仍标注 mil | AI 上下文里的板框数值偏小 | 与快照/前端口径统一（快照已是 mils） |
| 8 | 个别 PcbDoc（如 jlink_pcb）嵌入字体损坏、板框原点非零 | PCB SVG 视口异常 | worker 增加 viewBox/包围盒归一化；向 altium-monkey 反馈 |
| 9 | `test/` 手动脚本仍含本机硬编码路径（`E:\Projects\...`、`C:\Users\SEEYAO\...`） | 换机复用前需改路径 | 按需参数化；新截图放 `screenshots/`、新调试脚本放 `test/`，无长期价值直接删除 |
| 10 | 后端无测试、SSE 无心跳/断线重连、PCB 预览无缩放/层开关 | 回归与体验 | pytest + 心跳 + 画布控件 |
| 11 | DelphiScript 脚本按公开 RTL API 编写 | 不同 Altium 版本可能需要真机微调 | 已有逐字段 try/except；按版本做兼容矩阵 |
| 12 | AI 平台新增列（JSONB / TIMESTAMPTZ）的迁移语句未在真实 PostgreSQL 库执行过（SQLite 冒烟只覆盖逻辑） | 缺列导致查询报错 | 重启后端会自动执行；也可手动 `backend/scripts/migrate_ai_platform.py` |
| 13 | 模型配置写操作默认限管理员（`AI_CONFIG_WRITE_ADMIN_ONLY=true`） | 单人开发时被 403 | 需要放开时在 `backend/.env` 置 `false` |
| 14 | 旧的 `backend/app/services/ai/providers.py` 已停用但文件仍在（同名 `providers/` 包优先导入） | 阅读时易混淆 | 手工 `git rm backend/app/services/ai/providers.py` |
| 12 | AI 平台新增列（JSONB / TIMESTAMPTZ）的迁移语句未在真实 PostgreSQL 库执行过（SQLite 冒烟只覆盖逻辑） | 缺列导致查询报错 | 重启后端会自动执行；也可手动 `backend/scripts/migrate_ai_platform.py` |
| 13 | 模型配置写操作默认限管理员（`AI_CONFIG_WRITE_ADMIN_ONLY=true`） | 单人开发时被 403 | 需要放开时在 `backend/.env` 置 `false` |
| 14 | 旧的 `backend/app/services/ai/providers.py` 已停用但文件仍在（同名 `providers/` 包优先导入） | 阅读时易混淆 | 手工 `git rm backend/app/services/ai/providers.py` |

## 安全与合规

- **认证**：JWT Bearer；密码 bcrypt；除注册/登录外所有业务端点要求登录。
- **网关**：可设 `GATEWAY_TOKEN`，后端连接记录保存同一令牌；网关 CORS 全开、无 TLS，**仅限受信局域网**使用。
- **写操作**：必须 dry-run 后人工确认；已实现单命令审计、`requestId` 幂等与撤销，但**跨命令事务回滚仍缺失**，请勿在生产设计上批量放开写命令。
- **默认口令**：`admin123456`、`SECRET_KEY` 仅用于开发，部署前必须替换。
- **AGPL-3.0**：离线解析依赖 `altium-monkey`。按其许可证要求，运行在独立 worker 子进程（聚合而非链接），本仓库不复制其源码、不在后端进程内 import；对外分发/对外服务前需重新评估授权。

## 路线图

- ✅ 第一阶段：平台前后端 + Altium 文件离线读取/查看
- ✅ 第二阶段：实时连接（gateway + DelphiScript 桥 + MCP server + 平台接入）
- ✅ 工具链首版：gateway 工具动态注册、function calling、dry-run + 人工确认（3 个写命令）
- ✅ AI 平台对齐：独立模型配置页（卡片/列表双视图、搜索筛选、连接测试、设默认、复制、导出）、五层 LLM 路由、API Key 加密存储；助手与技能扩展（采样覆盖、工具子集、技能优先级、提示词预览）
- 第三步：规则引擎（ERC/DRC/DFM）+ AI 审查报告 + RAG 知识库（pgvector）
- 第四步：元件选型 / BOM 风险 / 替代料
- ✅ 高级交互增强：写命令审计/幂等/撤销、实时设计 vs 离线快照漂移对比、AI 对话 Markdown 导出、工具日志持久化与只读工具并发
- ✅ 工具执行边界与查询式上下文：工具按会话绑定的连接/工程授权执行（取消「取第一条在线连接」的隐式路由）、网关工具按连接隔离；撤销前置状态校验；离线快照与实时设计各增加过滤查询工具/命令；设计上下文改为「概览 + 命中项 + 预算裁剪」
- ✅ 写后即查与确定性评测基线：写命令返回成功后 dry-run 回读对象状态并与目标参数核验（结果内嵌审计、前端「写后即查·未通过」徽标、失败项回喂下一轮 AI 上下文），构成辅助级别 L2→L3 验证门槛；确定性审查规则金标准评测集（缺陷板查全率 100% / 干净板零误报 / 规则不误触发）纯离线运行
- 第五步：完整意图命令层（ADR-001）——跨命令事务、更多原语/意图命令、端到端评测

## 设计文档

- [大模型最大程度辅助设计分析](docs/design/llm-max-assist-analysis.md)
- [ADR-001 语义描述到设计输出的执行路径](docs/design/adr/ADR-001-semantic-to-design-execution.md)
- [ADR-002 altium-monkey 离线引擎（含 AGPL 策略）](docs/design/adr/ADR-002-altium-monkey-offline-engine.md)
- [模块开发规范](docs/design/module-conventions.md)
- [审查规则评测集（金标准查全率/误报率回归）](docs/evals/README.md)
- [AI 平台对齐设计（大模型配置 / 助手 / 技能）](docs/design/ai-platform-alignment-design.md)
- [第一阶段完成度审计](docs/design/phase1-completion-audit.md)
- [网关部署与协议细节](gateway/README.md)
- [前端开发说明](frontend/README.md)
- [工程约定速览](CLAUDE.md)
