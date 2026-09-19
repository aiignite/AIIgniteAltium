# AIDriveAltium · 大模型辅助硬件设计平台

通过 MCP / 离线解析双通道连接 Altium Designer 的大模型辅助硬件设计系统。
当前进度：**第一阶段**（平台前后端 + Altium 文件离线读取查看）与**第二步**（Altium 实时连接）均已完成。

```
┌──────────────────┐   REST/SSE   ┌──────────────────┐   REST/MCP   ┌─────────────────────┐
│ React 前端 :3290  │ ──────────► │ FastAPI 后端 :3295 │ ──────────► │ altium-gateway :3296 │
│ 工作台/审查/连接   │             │ ai_engine/解析/RAG │             │ (Windows+Altium 机)  │
└──────────────────┘             └──────────────────┘             └──────────┬──────────┘
      PostgreSQL+pgvector(:5432) · Redis                                     │ 文件乒乓(行式协议v1)
                                                              Altium 内 AIDriveBridge 驻留脚本
```

## 技术栈

- 后端：FastAPI + SQLAlchemy 2.0 async + PostgreSQL(pgvector) + 隔离解析 worker（altium-monkey，子进程，ADR-002）
- 前端：React 19 + TypeScript + Vite + Mantine 9
- AI 引擎：多 provider（mock / OpenAI 兼容 / Anthropic）、技能注册表、SSE 流式对话、设计上下文注入（离线快照 + 实时摘要双通道）
- 实时连接：altium-gateway（DelphiScript 驻留脚本 + 文件乒乓桥 + 8 只读命令 + MCP server）

---

## 一、本地开发部署（macOS/Linux）

### 1. 数据库安装

任选其一：

```bash
# 方式 A：本机 Homebrew PostgreSQL
brew install postgresql@17 && brew services start postgresql@17
createdb -U postgres aidrive_altium
psql -U postgres -d aidrive_altium -c "CREATE EXTENSION IF NOT EXISTS vector"   # pgvector，供后续 RAG

# 方式 B：Docker（仅数据库）
docker compose up -d postgres redis
# 连接串: postgresql+asyncpg://aidrive:aidrive_altium_dev@localhost:5433/aidrive_altium
```

### 2. 配置与启动

```bash
cp backend/.env.example backend/.env   # 修改 DATABASE_URL 指向你的 PG
bash start.sh                          # 自动建 venv/建表/创建管理员/启动前后端
```

- 前端：http://localhost:3290
- 后端 API 文档：http://localhost:3295/docs
- 默认管理员：`admin@example.com / admin123456`（`backend/.env` 可改）

## 二、Docker 一键部署

```bash
docker compose up -d --build
# 包含: pgvector/pg16 + redis + backend(:3295) + frontend(nginx :3290, /api 反代)
```

## 三、Altium 实时网关部署（Windows 机，示例 192.168.1.14）

> 完整文档见 [gateway/README.md](gateway/README.md)。网关支持 mock 模式，**无 Altium 也可先联调**。

### 前置条件

- Windows 10/11 + Altium Designer（已安装）
- Python 3.10+（勾选 Add to PATH）
- 与运行平台的主机同一局域网

### 部署步骤

1. **拷贝** `gateway/` 整个目录到 Windows 机，如 `D:\altium-gateway`
2. **右键以管理员身份运行** `gateway\deploy\install.bat`
   （创建 venv、pip 安装、`netsh advfirewall` 放行 TCP 3296 入站）
3. **双击** `gateway\deploy\start_gateway.bat`（`ALTIUM_MODE=live`，监听 :3296）
4. **Altium 内运行驻留脚本**：`File ▸ Open ▸ Script Project...` 打开
   `gateway\altium_scripts\AIDriveBridge.PrjSrc` → 在脚本面板运行 `RunAIDriveBridge`
   → 弹出桥窗口保持打开（轮询默认自动启动）

### 平台侧接入

1. 平台「**Altium 连接**」页 → 新增连接，Base URL 填 `http://192.168.1.14:3296`
2. 点 **测试连接** → 状态变"已连接 / Altium 在线"
3. 点 **实时面板**（眼睛图标）→ 查看当前工程、PCB 统计与实时截图
4. 工作台对话**不选工程**时，自动注入实时设计上下文（当前打开的工程/元件/网络/统计）

### 防火墙与连通性排查

- 安装脚本已放行 3296；如仍不通，在 Windows 上检查：`netstat -ano | findstr 3296`、
  防火墙配置文件（公用/专用网络）、以及两机是否同网段（`ping` 默认被 Windows 拦截不代表离线）
- `ALTIUM_MODE=live` 时网关与 Altium 脚本通过 `%USERPROFILE%\Documents\AltiumBridge` 目录交换请求/响应

### MCP 客户端接入（Claude Desktop / ZCode）

```json
{
  "mcpServers": {
    "altium": { "command": "D:\\altium-gateway\\.venv\\Scripts\\altium-gateway-mcp.exe" }
  }
}
```

---

## 功能总览

| 功能 | 状态 | 说明 |
|---|---|---|
| 用户认证 | ✅ | JWT 注册/登录，启动自动创建管理员 |
| 工程文件离线解析 | ✅ | 上传 .PrjPcb/.SchDoc/.PcbDoc → 隔离 worker（altium-monkey）→ 元件/引脚级网络/BOM/PCB 统计/板框/叠层 |
| 可视化查看 | ✅ | 原理图 SVG、PCB SVG、元件/网络（单端标记+引脚明细）/BOM 合并视图 |
| AI 对话 | ✅ | 技能选择（原理图审查/PCB 审查/需求分析）、离线快照或实时摘要上下文注入、SSE 流式 |
| 模型管理 | ✅ | mock / OpenAI 兼容（含 Ollama）/ Anthropic，默认模型切换 |
| Altium 实时连接 | ✅ | 连接测试、实时面板（工程/统计/截图）、对话实时上下文；MCP server 供外部客户端 |
| 规则引擎/RAG/选型 | 规划中 | 见路线图 |

## 已知问题

- 个别 Altium 文件（如 jlink_pcb.PcbDoc）存在嵌入字体损坏与非零板框原点，PCB SVG 视口异常；常规文件正常
- DelphiScript 驻留脚本按公开 RTL API 编写，不同 Altium 版本可能需在真机微调（已逐字段 try/except 容错）
- 解析依赖 altium-monkey（AGPL-3.0）：独立子进程隔离运行，见 [ADR-002](docs/design/adr/ADR-002-altium-monkey-offline-engine.md)

## 设计文档

- [大模型最大程度辅助设计分析](docs/design/llm-max-assist-analysis.md)
- [ADR-001 语义描述到设计输出的执行路径](docs/design/adr/ADR-001-semantic-to-design-execution.md)
- [ADR-002 altium-monkey 离线引擎](docs/design/adr/ADR-002-altium-monkey-offline-engine.md)
- [模块开发规范](docs/design/module-conventions.md)
- [第一阶段完成度审计](docs/design/phase1-completion-audit.md)

## 路线图

- ✅ 第一阶段：平台前后端 + Altium 文件离线读取查看
- ✅ 第二阶段：Altium 实时连接（gateway + DelphiScript 桥 + MCP server + 平台接入）
- 第三步：规则引擎（ERC/DRC/DFM）+ AI 审查报告 + RAG 知识库
- 第四步：元件选型/BOM 风险；第五步：写命令（意图命令层 + dry-run 确认 + 审计）
