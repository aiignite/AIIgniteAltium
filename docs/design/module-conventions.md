# AIDriveAltium 模块开发规范（适配自 AIIgnitePLM plm-add-module / plm-ai-assistant-integration 技能）

> 来源：`/Users/wyh/Documents/AIIgnite/AIIgnitePLM/.claude/skills/plm-add-module/SKILL.md` 与 `../plm-ai-assistant-integration/SKILL.md`（含 references/，实现时按需回读原文模板）
> 状态：本项目的强制工程约定，M0 起生效

## 1. 沿用的核心约定（与 PLM 一致）

- 后端：FastAPI + SQLAlchemy 2.0 async（Mapped/mapped_column）+ Alembic；按功能域分组目录；**禁止根级 shim**，import 一律走 `{group}/`
- `__init__.py` 规则：models 从主文件重导出；services 保持空（`# Package marker`）；routers 视是否被 `from app.routers.{group} import router` 引用决定导出
- 模块化入口：`backend/app/modules/{group}/__init__.py` 导出 `register_routers`；`backend/app/modules/__init__.py` 维护 `ALL_MODULES`；models 维护 `ALL_MODEL_GROUPS`
- API：RESTful；请求/响应体自动 `snake_case ↔ camelCase`；前端 `buildQuery()` key 手写 snake_case
- 列表端点：`GET /{module}/page` 返回 `{items, total}`；list/count/page 共用 `_apply_filters`；`sort_by/sort_dir` 白名单
- 陷阱清单照单全收：DELETE 204 不写返回注解；commit 后用 selectinload 重查而非 `db.refresh()`；Pydantic Out 用 `datetime` 非 `str`；业务实体软删 `is_deleted` + `_base_query()`
- 前端：React 19 + TS + Vite + Tailwind；页面模式 A（单页）/ B（主从面包屑，`projectId?` 可选）/ C（项目内 Tab）；弹出层默认 Modal（指定则右侧抽屉）；`DataTable` + pagination 同卡贴底 + 服务端排序 + 操作列 `sticky:'right'`；**禁止 SimpleCrudTab**
- 前端接线 checklist：`services/{group}/index.ts` 聚合导出 → App.tsx lazy Route → useAppNavigate 映射 → Sidebar 菜单项（检查 icon import）

## 2. 本项目的功能域分组与表前缀（在 PLM 命名规范上注册新前缀）

| 分组 | 功能域 | 表前缀 | 典型模型 |
|---|---|---|---|
| `system` | 用户/认证/设置 | `sys_` | User |
| `ai` | AI 引擎 | `ai_` | AIModel, Conversation, Message, SkillRun |
| `altium` | Altium 连接 | `alt_` | GatewayConnection, BridgeSession, CommandAudit, DesignSnapshot |
| `review` | 设计审查 | `rvw_` | ReviewTask, ReviewFinding, ReviewReport, ReviewCase(案例库) |
| `component` | 元件数据 | `cmp_` | ComponentCache, SelectionRecord, AlternateMatch, RiskFlag |
| `bom` | BOM | `bom_` | Bom, BomItem, BomVariant |
| `knowledge` | 知识库 RAG | `knw_` | KnowledgeDoc, KnowledgeChunk |
| `files` | 离线文件 | `fls_` | UploadedProject, ParseJob |

命名规则沿用 PLM：`{2~3字母前缀}_{snake_case复数实体}`；新前缀不得与本表及 PLM 分配表冲突。

## 3. AI 工具与助手接线（适配自 plm-ai-assistant-integration）

- 业务工具：`backend/app/ai_tools/{group}_tools.py`；handler 签名 `async def handler(db, user_id, *, ...)`；返回 `{"success": True/False, ...}` 信封；ID 参数用 str 内部转 UUID；**委托 Service 层，不复制业务逻辑**
- 工具来源分两类，统一进 `ToolRegistry`（带 category，供技能订阅子集）：
  1. 本地业务工具（规则查询、元件搜索、RAG 检索、审查操作）——PLM 式注册
  2. **gateway MCP 动态工具**（Altium 操作）——后端作为 MCP client 启动时拉取 tool 清单注册，category=`altium`，写工具带 `requires_confirmation` 元数据
- 助手定义：name/system_prompt/tools 三要素；`name` 与前端 `recommendedAssistant` 完全一致；编号等系统生成字段在 prompt 注明"由系统自动生成"
- 前端：`PageAIContext` 模式——每页 `registerPageAI({ pageName, recommendedAssistant, onDataChanged })`，全局 `AISidebarDrawer` 入口自动切换推荐助手，工具执行成功回调刷新页面
- 本项目特有：工作台为**对话主界面**（非侧栏辅助），确认卡（写操作 dry-run 预览）为新增组件，走 ToolCallDisplay 同一渲染管线

## 4. 与 PLM 的差异点

- 审查中心/工作台页不套 A/B/C 项目模式：工作台是新形态（左对话右设计画布），审查任务用模式 B 变体（主从面包屑，无 projectId）
- 数据库迁移：MVP 用 `create_all()` 启动建表，alembic 作为改进项后补（PLM 陷阱 #7 的时序规则届时适用）
- 编号规则（NumberService）：审查任务号 `RVW-YYYYMM-####` 纳入首批
