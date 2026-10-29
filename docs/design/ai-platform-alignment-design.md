# AI 平台对齐设计：大模型配置 / 助手 / 技能

> 项目：AIDriveAltium · 草案日期：2026-10-18 · 状态：**已实施（M1–M3 完成，待数据库联调）**
> 参考实现：`aiignite/AIDriveNote`（`backend/app/models/ai/ai.py`、`services/ai/llm_router.py`、`services/ai_providers/*`、`frontend/src/pages/settings/AIModelsPage.tsx`）
> 关联文档：[模块开发规范](./module-conventions.md) · [大模型最大辅助分析](./llm-max-assist-analysis.md) · ADR-002

## 0. 结论摘要

当前缺口只有一句话：**大模型没有一等公民的配置界面与路由层**。模型只是 `SettingsPage` 里一张裸表，字段只有 `name/provider/base_url/api_key/model_name`；Provider 硬编码在 `routers/ai/models.py` 的 dict 里；API Key 明文入库明文出网；助手绑模型、技能绑工具的能力都没有落地。

本期（对齐档 C）交付四件事：

1. **模型配置页**独立成页：卡片/列表双视图、搜索与筛选、表单抽屉、**连接测试**、设为默认、复制、导出。
2. **模型字段扩容**：温度、max_tokens、top_p、上下文窗口、工具/图像能力、速度成本标签、系统预设标记、测试状态。
3. **LLMRouter 路由层**：请求 → 会话 → 助手 → 系统默认 → mock 兜底，替换现在散落在 `orchestrator.resolve_model_config` 的临时逻辑。
4. **密钥加密**：`api_key_enc` + 掩码 `key_hint`，响应永不明文回传；存量明文自动升级。

同时把助手/技能补齐到"能真正影响一次对话"的程度：助手可控温度与工具子集，技能可控工具与优先级，编排器按能力裁剪工具。

**明确不采纳**的参考项（理由见 §9）：per-user 模型所有权、访客模型白名单、`ai_page_skill_bindings`、MiniMax/OpenCode/Anthropic 独立协议适配。

## 1. 现状盘点

| 位置 | 现状 | 差距 |
|---|---|---|
| `backend/app/models/ai/ai_model.py` | 9 个业务列，无能力/参数/系统标记 | 无法表达"这个模型支不支持 tools""上下文多大" |
| `backend/app/routers/ai/models.py` | CRUD + 默认互斥；`PROVIDERS` 是模块级 dict | 无测试端点、无 provider 元数据端点、无复制/导出；key 明文返回 |
| `backend/app/services/ai/providers.py` | 单文件 244 行，mock/openai/anthropic 三条分支 | 无工厂注册表、ollama 与 llamacpp 无独立默认值、无 usage 统计 |
| `backend/app/services/ai/orchestrator.py::resolve_model_config` | 请求 → 助手 → `is_default` → 任意一条 | 缺"会话绑定"一层；异常文案散落；无路由结果可观测 |
| `backend/app/models/ai/assistant.py` | `skill_codes` JSON 存技能 code 列表 | 助手无 temperature/max_tokens/工具子集；技能无 `tool_codes`/`priority` |
| `backend/app/database_patches.py` | 4 条幂等 ALTER 的过渡方案 | 无独立可重放迁移入口 |
| `frontend/src/pages/SettingsPage.tsx` | 一张 195 行表格 + Modal | 无卡片视图、无筛选、无测试、无 provider 预设模板 |
| `frontend/src/pages/AssistantsPage.tsx` | 助手/技能两个 Tab，模型下拉只有 `name` | 模型选择无能力提示；无法从助手页跳去配模型 |

补充事实（避免后续踩坑）：前端实际栈是 **React 19 + Mantine 9 + Tabler Icons**，`module-conventions.md` 里写的 "Tailwind" 与现状不符，本期设计以 Mantine 为准；该文档 §1 措辞建议一并更正。

## 2. 参考实现要点（AIDriveNote）

| 参考点 | 参考做法 | 本项目取舍 |
|---|---|---|
| `ai_models` 字段 | `model_id / provider / endpoint / api_key / description / popularity / speed / cost / context / supports_text / supports_image / is_public / user_id` | 采纳字段语义，列名沿用本项目 `model_name / base_url / remark`，不迁移列名（避免大改） |
| `AIProvider` 枚举 | OLLAMA / OPENAI / ANTHROPIC / MINIMAX / OPENCODE | 只保留 `mock / openai / ollama / llamacpp`（+ 现有 anthropic 兼容分支），见 §5.1 |
| `services/ai_providers/` | `base.py` 抽象 + `factory.py` 注册 + 每 provider 一个文件 | 采纳"工厂 + 每 provider 一文件"，但 ollama/llamacpp **复用 openai_compat**（都提供 `/v1/chat/completions`），少 300 行重复代码 |
| `LLMRouter.resolve` | request → assistant → 用户默认 → env 兜底；访客只能用自己的模型 | 采纳前四层，**砍掉用户默认与访客层**（单租户），补一层"会话绑定" |
| `secret_crypto.decrypt_secret` | 落库加密、出站前解密 | 采纳，并给存量明文加自动升级路径 |
| `AIModelsPage` | 卡片/列表切换、搜索、高级筛选（provider/speed/cost）、测试连接、设默认、导出 CSV、系统预设禁改 | 全部采纳，导出改 JSON+CSV 双格式 |
| 助手-技能绑定表 | `ai_assistant_skill_bindings`（带 weight/enabled） | **不采纳**，保留 `skill_codes` JSON；理由见 §9.2 |

## 3. 目标架构

```
前端 Mantine
  ├─ AIModelsPage        模型卡片/列表 · 表单抽屉 · 测试连接 · 默认/复制/导出
  ├─ AssistantsPage      助手(温度/工具子集) · 技能(tool_codes/priority)
  ├─ ModelPicker         工作台与助手表单共用（显示 provider/模型名/默认/不可用）
  └─ SettingsPage        保留系统项，AI 相关改为入口卡跳转

API  /api/v1
  ├─ /ai/models                CRUD + /providers + /test + /{id}/test + /{id}/default + /{id}/duplicate + /export
  ├─ /ai/assistants            CRUD + /{id}/default + /{id}/prompt-preview + /{id}/duplicate
  └─ /ai/skills                CRUD + /resolve + /{id}/duplicate

服务层
  ├─ llm_router.py         ProviderResolution 解析（五层优先级）
  ├─ secret_crypto.py      Fernet 加密 / 掩码 / 明文升级
  ├─ model_probe.py        连接测试（8s 超时，探 /models 或 1-token 补全）
  ├─ providers/            工厂注册表 + openai_compat / anthropic / mock
  └─ orchestrator.py       按 capability 裁剪工具、透传 temperature/max_tokens、记录 usage
```

一次对话的模型解析链：

```
ChatStreamIn.modelConfigId
  → Conversation.modelConfigId
  → Assistant.modelConfigId
  → AIModelConfig.is_default AND enabled
  → 任一 enabled（按 sort_order）
  → mock（仅当系统无任何启用模型时兜底并打 warning 日志）
  → 否则 NoAvailableModelError（前端展示"去配置模型"）
```

> 与现状差异：新增 `Conversation.modelConfigId` 一层（会话中途换模型不再被请求体覆盖丢失），并且**解析结果写入 `meta` 事件**（provider / modelName / resolution），前端可显示"本条由 DeepSeek/chat 回答"。

## 4. 数据模型变更

### 4.1 `ai_model_configs` 新增列

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `temperature` | `DOUBLE PRECISION` | `0.4` | 采样温度 |
| `max_tokens` | `INTEGER` | `4096` | 单次上限 |
| `top_p` | `DOUBLE PRECISION` | `1.0` | 核采样 |
| `context_window` | `VARCHAR(20)` | `''` | 展示用，如 `128K` |
| `supports_tools` | `BOOLEAN` | `TRUE` | 关闭后不注入 tools |
| `supports_image` | `BOOLEAN` | `FALSE` | 预留视觉通道（§2.1 分析报告） |
| `speed` | `VARCHAR(20)` | `'Fast'` | Fast / Medium / Slow，仅筛选展示 |
| `cost` | `VARCHAR(20)` | `'$'` | $ / $$ / $$$，仅筛选展示 |
| `is_system` | `BOOLEAN` | `FALSE` | 系统预设，禁止改 provider / 删除 |
| `api_key_enc` | `TEXT` | `''` | 加密密文（`enc:v1:` 前缀） |
| `key_hint` | `VARCHAR(20)` | `''` | 掩码尾 4 位，列表展示用，避免解密 |
| `test_status` | `VARCHAR(20)` | `''` | `ok` / `fail` / `''` |
| `test_latency_ms` | `INTEGER` | `0` | 最近一次测试耗时 |
| `tested_at` | `TIMESTAMPTZ` | `NULL` | 最近一次测试时间 |
| `last_error` | `TEXT` | `''` | 最近一次失败原因（截断 500 字） |

`api_key` 列**保留但不再写入**（写入后立即置空），作为回滚安全网；`remark` 兼作列表描述，不新增 `description`。

索引：`(is_deleted, enabled)`、`(provider)`。

### 4.2 `ai_assistants` 新增列

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `temperature` | `DOUBLE PRECISION` | `NULL` | 空 = 继承模型 |
| `max_tokens` | `INTEGER` | `NULL` | 空 = 继承模型 |
| `tool_codes` | `JSONB` | `'[]'` | 可用工具子集；空 = 全部 |
| `greeting` | `TEXT` | `''` | 工作台欢迎卡文案 |

### 4.3 `ai_skills` 新增列

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `tool_codes` | `JSONB` | `'[]'` | 该技能启用时额外放开/限定的工具 |
| `priority` | `INTEGER` | `50` | 命中打分加权（参考实现同名概念） |
| `extra_config` | `JSONB` | `'{}'` | 预留：few-shot、输出 schema |

### 4.4 `ai_messages` 新增列

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `prompt_tokens` | `INTEGER` | `0` | provider 返回 usage 时写入 |
| `completion_tokens` | `INTEGER` | `0` | 同上 |

## 5. 迁移策略（幂等 ALTER）

单一事实源：`backend/app/database_patches.py::_STATEMENTS` 追加语句；启动时 `ensure_extra_columns` 已自动执行。另外新增可独立重放的入口：

```
backend/scripts/migrate_ai_platform.py   # 读取 settings.database_url，复用同一 _STATEMENTS，逐条执行并打印
```

语句形态（PG，全部 `IF NOT EXISTS`，可反复执行）：

```sql
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS temperature DOUBLE PRECISION NOT NULL DEFAULT 0.4;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS max_tokens INTEGER NOT NULL DEFAULT 4096;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS top_p DOUBLE PRECISION NOT NULL DEFAULT 1.0;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS context_window VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS supports_tools BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS supports_image BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS speed VARCHAR(20) NOT NULL DEFAULT 'Fast';
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS cost VARCHAR(20) NOT NULL DEFAULT '$';
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS api_key_enc TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS key_hint VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS test_status VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS test_latency_ms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS tested_at TIMESTAMPTZ;
ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_assistants   ADD COLUMN IF NOT EXISTS temperature DOUBLE PRECISION;
ALTER TABLE ai_assistants   ADD COLUMN IF NOT EXISTS max_tokens INTEGER;
ALTER TABLE ai_assistants   ADD COLUMN IF NOT EXISTS tool_codes JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE ai_assistants   ADD COLUMN IF NOT EXISTS greeting TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_skills       ADD COLUMN IF NOT EXISTS tool_codes JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE ai_skills       ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 50;
ALTER TABLE ai_skills       ADD COLUMN IF NOT EXISTS extra_config JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ai_messages     ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ai_messages     ADD COLUMN IF NOT EXISTS completion_tokens INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_ai_model_configs_enabled ON ai_model_configs (is_deleted, enabled);
CREATE INDEX IF NOT EXISTS ix_ai_model_configs_provider ON ai_model_configs (provider);
```

存量数据回填（一次性、可重入）：把 `mock` 配置标 `is_system=true`；把非空明文 `api_key` 加密进 `api_key_enc` 并生成 `key_hint`，随后清空 `api_key`。

> 为什么不引入 Alembic：本期只有加列与索引，`ADD COLUMN IF NOT EXISTS` 已满足幂等；引入 Alembic 需处理既有库的 baseline 与 `create_all` 并存问题（规范 §4 已注明为改进项）。代价是**列类型变更仍需手写**，一旦出现删列/改类型，立即升级到 Alembic。

## 6. 后端 API 设计

### 6.1 模型

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ai/models` | 列表；`apiKey` 字段改为 `hasKey: bool` + `keyHint`，**不再回传明文** |
| GET | `/ai/models/providers` | provider 元数据：`id/name/requiresApiKey/defaultBaseUrl/defaultModel/group` + 前端快捷模板 `presets[]`（DeepSeek、硅基流动、Moonshot、智谱、Ollama、llama.cpp） |
| POST | `/ai/models` | 新建；`apiKey` 走加密写入 |
| PUT | `/ai/models/{id}` | 更新；`apiKey` 传空 = 保持原值，传 `""` 显式清除用 `clearApiKey: true` 表达；系统预设禁改 `provider` |
| POST | `/ai/models/{id}/default` | 设为默认（互斥） |
| POST | `/ai/models/{id}/duplicate` | 复制为新配置（名称追加 `（副本）`，非系统、非默认） |
| POST | `/ai/models/test` | 测试**未保存**配置（body 含 provider/baseUrl/modelName/apiKey 或 `id` 复用已存密钥） |
| POST | `/ai/models/{id}/test` | 测试已存配置；结果回写 `test_status/test_latency_ms/tested_at/last_error` |
| GET | `/ai/models/export?format=json\|csv` | 导出（**不含密钥**，只导出 `hasKey`） |
| DELETE | `/ai/models/{id}` | 软删；系统预设拒绝 |

响应体新增字段全部 camelCase（`CamelModel` 自动转换）：`hasKey/keyHint/temperature/maxTokens/topP/contextWindow/supportsTools/supportsImage/speed/cost/isSystem/testStatus/testLatencyMs/testedAt/lastError`。

### 6.2 助手 / 技能

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/ai/assistants/{id}/prompt-preview` | 返回 `compose_system_prompt` 的最终文本（含 BASE_PROMPT/人设/技能/占位上下文），供调试人设 |
| POST | `/ai/assistants/{id}/duplicate` | 复制（不继承 `is_default`） |
| POST | `/ai/skills/{id}/duplicate` | 复制（新 code 后缀 `-copy`，冲突自动加序号） |
| GET | `/ai/skills/resolve` 增强 | 打分加入 `priority` 权重与 `tool_codes` 命中；返回 `scoreBreakdown` 便于解释 |

`SkillResolveIn` 增加 `projectId`（预留：按工程类型过滤技能），`MIN_SCORE` 保持不变。

## 7. 服务层设计

### 7.1 `providers/` 包（替换单文件）

```
services/ai/providers/
├─ __init__.py        stream_chat() 门面（保持 orchestrator 现有调用签名，降低改动面）
├─ base.py            ProviderConfig(dataclass: base_url/api_key/model/temperature/max_tokens/top_p)
│                     BaseProvider.stream(messages, tools) -> AsyncIterator[dict]
├─ openai_compat.py   OpenAI 兼容流式 + usage + tool_calls 累积
├─ anthropic.py       现有实现平移（legacy 分支）
├─ ollama.py          继承 openai_compat，默认 base=http://localhost:11434/v1，无 Key
├─ llamacpp.py        继承 openai_compat，默认 base=http://localhost:8080/v1，无 Key
├─ mock.py            现有演示引擎平移
└─ factory.py         PROVIDERS 注册表 + create(provider, cfg) + list_providers()
```

### 7.2 `llm_router.py`

```python
@dataclass
class ProviderResolution:
    provider: str
    model_name: str
    base_url: str
    api_key: str          # 已解密
    temperature: float
    max_tokens: int
    top_p: float
    supports_tools: bool
    config_id: str
    resolution: str       # request|conversation|assistant|default|fallback|mock

class LLMRouter:
    @staticmethod
    async def resolve(db, *, model_config_id, conversation, assistant) -> ProviderResolution
```

解析失败抛 `NoAvailableModelError`（`detail` 含前端可跳转的提示），沿用现有 `RuntimeError` 文案的用户体验但改成专用异常类。

### 7.3 `secret_crypto.py`

- 密钥来源：`settings.ai_secret_key`（新增配置项；缺省时由 `secret_key` 经 HKDF-SHA256 派生，避免二次配置）。
- 加密：`Fernet`，密文格式 `enc:v1:<token>`。
- 读取：`decrypt_secret(value)`；非 `enc:v1:` 前缀视为明文并**自动加密回写**（一次性升级）。
- 掩码：`key_hint = "…" + 后 4 位`（长度 < 8 时全掩码）。
- 禁止：任何响应体、日志、异常消息输出密钥；日志统一用 `key_hint`。

### 7.4 `model_probe.py`

- 超时 8s（`httpx.Timeout(connect=5, read=8)`）。
- 探测顺序：`GET {base}/models` → 若 404/405 则 `POST {base}/chat/completions` 且 `max_tokens=1, stream=False`。
- 返回 `{ok, latencyMs, model, error, statusCode}`；anthropic 走 `POST /v1/messages` 1 token。
- 失败原因归类：`auth`（401/403）、`network`（连接/超时）、`model`（404 model）、`rate`（429）、`unknown`，前端按类给建议。

### 7.5 orchestrator 变更点

1. `resolve_model_config` 删除，改调 `LLMRouter.resolve`。
2. 工具装配：`tool_definitions()` 结果按 `cfg.supports_tools` 与 `assistant.tool_codes`/`skill.tool_codes` 取交集（空 = 全部）；`supports_tools=False` 时传 `tools=None`。
3. 参数透传：`temperature` 取 `assistant.temperature ?? cfg.temperature`，同理 `max_tokens`。
4. `meta` 事件增加：`provider / modelName / resolution / supportsTools`。
5. usage：流结束若 provider 回传 `usage`，写 `prompt_tokens/completion_tokens` 并进 `meta`。
6. 错误：`NoAvailableModelError` → `{"type":"error","code":"no_model"}`，前端渲染"去配置模型"按钮。

## 8. 前端设计

### 8.1 路由与信息架构

| 路由 | 页面 | 说明 |
|---|---|---|
| `/ai-config` | AI 配置中心（Tabs：模型 / 助手 / 技能） | 三者强关联（助手绑模型、技能绑工具），同页减少跳转 |
| `/assistants` | → 重定向 `/ai-config?tab=assistants` | 兼容旧入口与书签 |
| `/settings` | 系统设置 | AI 区块改为一张入口卡（显示模型数/默认模型/连通状态） |

导航栏：`AI 助手` 改名为 `AI 配置`，图标 `IconBrain`；`设置` 保留。

### 8.2 `AIModelsPage`（模型 Tab）

- 头部：标题 + 统计徽章（总数/已启用/可用 Key/默认模型）+ 刷新 + 导出 + 新建。
- 工具条：搜索（名称/模型名/provider/备注，`useDeferredValue` 防抖）+ 视图切换（卡片/列表）+ 高级筛选（provider / speed / cost / 仅启用 / 仅系统预设）。
- 卡片：名称 + `isDefault` 星标 + `provider` 徽章 + 模型名（等宽字体）+ 备注 + 三宫格（速度/成本/上下文）+ 能力行（文本/工具/图像）+ `hasKey` 与 `testStatus` 圆点 + 操作（编辑 / 测试 / 设默认 / 复制 / 删除）。
- 列表：同名信息压缩为表格行，操作列 sticky 右侧（规范 §1）。
- 表单抽屉（`size="md"`，Mantine `Drawer`）：
  - provider 选择 → 自动填 `defaultBaseUrl` 与 `defaultModel`，并显示"快速模板"（DeepSeek/硅基流动/Ollama…）一键填充；
  - 名称、模型名、Base URL、API Key（`type=password`，占位显示 `keyHint`，留空=不修改）；
  - 参数：温度滑块 0–2（步进 0.1）+ max_tokens + top_p + 上下文窗口；
  - 能力：支持工具 / 支持图像 开关；速度、成本 下拉；
  - 底部：**测试连接**（就地显示耗时/错误分类）+ 保存 + 设为默认开关。
- 删除走确认弹窗（Mantine `Modal` + `Button color="red"`）；系统预设禁用编辑 provider 与删除，仅允许改参数/启用。

### 8.3 `ModelPicker`（共用组件）

`components/ai/ModelPicker.tsx`：`Select` 封装，选项 label = `名称 · 模型名`，description 显示 provider 与 `默认` 标记；空选项 = "使用助手绑定 / 系统默认"；对 `hasKey=false` 且 `provider != mock` 的项显示 `⚠ 未配置密钥` 且禁止选择。

工作台用它替换现有 `Select`（`WorkbenchPage.tsx:496`），助手表单用它替换 `AssistantsPage.tsx:566`。

### 8.4 助手 / 技能表单增强

- 助手：新增"温度/最大 Tokens（留空继承模型）"、"可用工具（`ChipGroup` 多选，空=全部）"、"开场白"、按钮"预览系统提示词"（调 `prompt-preview`，Modal 展示等宽文本）。
- 技能：新增"关联工具（`ChipGroup`）"、"优先级（`NumberInput` 0–100）"；列表卡片显示优先级与工具数；`resolve` 结果展示打分明细。

### 8.5 视觉一致性

沿用 `index.css` 现有 `.ai-*` 类（`.ai-gradient`、`.ai-gradient-emerald`、`.ai-card-glow`、`.ai-badge-*`、`.ai-skill-pill`、`.ai-quick-chip`），模型页使用第三套渐变（橙 `#f97316 → #ea580c`，对应参考实现的 orange 主色），避免与助手的 emerald、技能的 indigo 撞色。

## 9. 决策与不采纳项

### 9.1 provider 只做四类

`mock` / `openai` / `ollama` / `llamacpp`。ollama 与 llama.cpp 均暴露 OpenAI 兼容端点，复用 `openai_compat` 即可，独立协议适配留到出现"必须用原生 `/api/chat` 特性（keep_alive、num_ctx）"的真实需求时再做。`anthropic` 现有分支**保留**（已在用，删除属回归），但在 UI 归入"兼容（legacy）"分组，不推广。

### 9.2 不引入助手-技能绑定表

参考实现用 `ai_assistant_skill_bindings(assistant_id, skill_id, weight, enabled)`。本项目 `skill_codes` JSON 已驱动 4 处（seed、助手编辑、resolve、orchestrator），改成关联表需同步改 4 处 + 迁移 + 前端多选交互，而唯一收益是"每技能权重"。**决策**：权重放到 `ai_skills.priority`（全局），助手级差异保留 `skill_codes` 顺序（顺序即优先级）。当出现"同一技能在不同助手下权重不同"的实际诉求再引入绑定表。

### 9.3 不做的事

| 不采纳 | 理由 |
|---|---|
| `user_id` 模型所有权 | 单租户项目，`sys_users` 无租户概念，加了只会让聊天查不到别人的模型 |
| 访客模型白名单 | 项目无访客角色 |
| `ai_page_skill_bindings` | 本项目只有工作台一个对话入口，无多页面推荐技能路由 |
| MiniMax / OpenCode 适配 | 无实际接入需求；openai 兼容已覆盖绝大多数国产端点 |
| 模型级 `is_public` | 同上，无租户/共享语义 |

## 10. 错误与降级矩阵

| 场景 | 后端行为 | 前端表现 |
|---|---|---|
| 无任何启用模型 | 抛 `NoAvailableModelError` | 气泡卡："还没有可用模型" + 按钮跳 `/ai-config?tab=models` |
| 仅有 mock | 正常返回，`meta.resolution=mock` | 消息头显示"演示引擎"灰标 |
| 密钥缺失（非 mock） | 该配置在解析时跳过，继续下一层 | 选择器该项禁选并提示去填 Key |
| 401/403 | 错误事件 `code=auth` | "密钥无效或权限不足"，附"去修改密钥" |
| 连接超时/网络 | `code=network` | "无法连接 {host}，检查 Base URL 或代理" |
| 429 | `code=rate` | "触发限流，稍后重试" |
| 模型不支持 tools | `supportsTools=false` → 不注入 tools | 输入框上方提示"当前模型不支持工具调用" |
| 上下文超限 | provider 报错原样透传 + `code=context` | 提示切换大上下文模型 |
| 连接测试失败 | 回写 `test_status=fail` + `last_error` | 卡片出现红点，悬浮显示原因 |

## 11. 安全与权限

- **密钥不出网**：响应只给 `hasKey`/`keyHint`；导出不含密钥；日志不打印。
- **写操作限管理员**：新增配置项 `ai_config_write_admin_only: bool = True`；为真时 `POST/PUT/DELETE /ai/models`、`/ai/models/{id}/test` 校验 `user.is_admin`，普通用户只读列表。聊天不受限。
- **测试端点防 SSRF**：仅允许 `http/https`，拒绝 `file://`、`gopher://`；解析目标 IP 后拒绝私有网段（`127.0.0.0/8`、`10/8`、`172.16/12`、`192.168/16`、`169.254/16`、`::1`），**但放行 `localhost` 与 RFC1918 当且仅当 provider ∈ {ollama, llamacpp}**（本地推理是核心场景）。该白名单进配置项，默认如上。
- **审计**：模型配置的增删改记 INFO 日志（`user_id / action / config_id / key_hint`）；写操作审计表留待 `alt_` 审计统一实现（ADR-001）。

## 12. 实施计划

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M1 数据与路由**（后端） | 迁移语句 + 模型字段 + `providers/` 包拆分 + `llm_router` + `secret_crypto` + `/providers` & `/test` 端点 | `pytest` 通过；启动后 `\d ai_model_configs` 含全部新列；明文旅自动升级；curl 测试端点返回 `{ok,latencyMs}` |
| **M2 模型配置页**（前端） | `AIModelsPage` + `ModelForm` + `ModelCard` + `ModelPicker` + 路由/导航/设置入口卡 | 手动走通：新建→测试→设默认→编辑→复制→删除→导出；截图存 `screenshots/models-YYYYMMDD-HHmmss.png` |
| **M3 助手/技能联动** | 助手温度/token/工具子集/开场白 + 技能 `tool_codes`/`priority` + `resolve` 增强 + `prompt-preview` | 对话验证：选助手→其温度生效；技能命中数与优先级相关；工具子集裁剪生效 |
| **M4 收尾** | 种子补种（3 个预设模型模板 + 2 个技能补 `tool_codes`）、usage 统计、错误矩阵埋点、文档与 `module-conventions.md` 修订 | 全量回归 + 断网/错Key/限流三态手测 |

预估：M1 约 1 天，M2 约 1.5 天，M3 约 1 天，M4 约 0.5 天。

## 13. 测试计划

后端（`backend/tests/`）：
1. `test_llm_router_priority`：五层优先级逐一命中，含"配置被禁用/软删则跳过"。
2. `test_secret_crypto`：加密→解密往返；明文输入自动升级；掩码长度边界（<8 位）。
3. `test_model_probe`：mock transport 覆盖 200 / 401 / 429 / 超时 / 404 models。
4. `test_model_crud`：系统预设禁删禁改 provider；默认互斥；复制不继承默认。
5. `test_skill_resolve`：code/name/keyword/priority/assistant 绑定 五类加分与 Top-K 截断。
6. `test_prompt_compose`：BASE_PROMPT + 人设 + 技能 + 上下文 顺序稳定。

前端手测清单：视图切换、筛选组合、表单校验、Key 留空不改、测试失败分类文案、禁用项提示、导出文件名、窄屏折叠。

## 14. 风险与开放问题

| 风险 | 影响 | 缓解 |
|---|---|---|
| 迁移语句在非 PG（如本地 SQLite 试验）失败 | 启动报错 | `ensure_extra_columns` 已 try/except 逐条跳过；独立脚本显式报错 |
| 前端 Mantine 9 API 与参考实现（Tailwind）差异 | 照抄不可行 | 只借鉴信息架构，组件全部用 Mantine 重写 |
| 流式 usage 支持差异（部分兼容端点不支持 `stream_options`） | 用量统计缺失 | 缺 usage 时记 0，不报错；统计口径标注"部分模型无用量" |
| `supports_tools=false` 时技能仍声明工具 | 语义冲突 | 编排器取交集，冲突时以模型能力为准并 warn 日志 |
| 代理/网络导致测试端点误判 | 用户困惑 | 错误分类到 `network` 并给出 Base URL/代理提示；8s 超时可配 |

**开放问题（已按默认值实现，可随时调整）**：
1. 写操作限 `is_admin` —— 已按"是"实现，开关 `ai_config_write_admin_only`（默认 `true`）。
2. 模型分组 —— 暂不做卡片分区，改用 `provider` 筛选 + 卡片上的本地/云分组标签（provider 元数据 `group` 字段已备好）。
3. 导出格式 —— 同时提供 CSV 与 JSON（`GET /ai/models/export?format=json|csv`），均不含密钥。

## 15. 附：参考仓库获取方式（已打通）

首次尝试失败的原因不是"没有凭据"，而是**端口与 TLS 后端用错**。工作区记忆 `E:\DSH\AGENTS.md` 记录的正确姿势：

| 代理 | 端口 | 用途 |
|---|---|---|
| SOCKS5 | `127.0.0.1:7890` | 通用（hysteria2 本地入口） |
| HTTP | `127.0.0.1:7891` | git / python 出网 |

沙箱内 Schannel 系列必然失败（`curl.exe`、`Invoke-WebRequest`、默认后端 git），可用的只有 OpenSSL 系：

```powershell
# git（浅克隆 / 任意 git 命令）—— 封装脚本：E:\DSH\hy2\git-gh.cmd
& E:\DSH\hy2\git-gh.cmd clone --depth 1 https://github.com/aiignite/AIDriveNote.git .tmp-ref/AIDriveNote

# 等价展开
git -c http.sslBackend=openssl -c http.proxy=http://127.0.0.1:7891 `
    -c https.proxy=http://127.0.0.1:7891 clone --depth 1 https://github.com/aiignite/AIDriveNote.git .tmp-ref/AIDriveNote

# python（OpenSSL）作为健康检查
$env:HTTPS_PROXY='http://127.0.0.1:7891'; python -c "import urllib.request; print(urllib.request.urlopen('https://api.github.com/repos/aiignite/AIDriveNote', timeout=20).status)"

# 通道是否活着（明文 HTTP，不触发 Schannel）
curl.exe -s -o NUL -w '%{http_code}' -x http://127.0.0.1:7891 http://www.baidu.com
```

要点：git **不认** `HTTP_PROXY` 环境变量，必须 `-c http.proxy=...`；只给 `sslBackend=openssl` 不给 proxy 会一直等到超时。克隆产物在 `.tmp-ref/`（已加入 `.gitignore`，仅作比对参考，不入库）。

## 16. 实施落点（2026-10-18，含 clone 后二次对齐）

| 层 | 文件 | 变更 |
|---|---|---|
| 模型 | `backend/app/models/ai/ai_model.py` | 15 个新列 + `bind_key()` / `clear_key()` / `has_key` |
| 模型 | `backend/app/models/ai/assistant.py` | 助手 4 列、技能 3 列 |
| 模型 | `backend/app/models/ai/conversation.py` | 消息 `prompt_tokens` / `completion_tokens` |
| 迁移 | `backend/app/database_patches.py` | `AI_PLATFORM_STATEMENTS`（24 条 ALTER + 2 个索引，全部幂等） |
| 迁移 | `backend/scripts/migrate_ai_platform.py` | 独立重放入口（复用同一语句列表） |
| 服务 | `backend/app/services/ai/providers/` | `base / openai_compat / ollama（原生 /api/chat）/ llamacpp / anthropic / mock / factory`，旧 `providers.py` 转为废弃说明（同名包优先导入） |
| 服务 | `backend/app/services/ai/llm_router.py` | 五层解析 + `NoAvailableModelError` + 安全摘要 |
| 服务 | `backend/app/services/ai/secret_crypto.py` | Fernet（`enc:v1:`）+ 掩码 + 明文识别 |
| 服务 | `backend/app/services/ai/model_probe.py` | 连接测试 + 错误归类 + 私网地址策略；ollama 探测 `/api/tags`、llamacpp 探测 `/models` |
| 服务 | `backend/app/services/ai/orchestrator.py` | 改用 Router、按能力裁剪工具、透传采样参数、记录 usage、`no_model` 错误码 |
| 服务 | `backend/app/services/ai/seed_data.py` | 预设模型补种 + 明文旅升级 + 技能优先级 |
| 配置 | `backend/app/config.py` | `ai_secret_key` / `ai_config_write_admin_only` / 超时 / 默认采样 |
| API | `backend/app/routers/ai/models.py` | 重写：providers / test(+`test-connection` 别名) / duplicate / export / 默认互斥 / 掩码响应 / 管理员校验 |
| API | `backend/app/routers/ai/assistants.py` | 新字段 + `prompt-preview` + `duplicate`(+`clone` 别名) + 创建时校验模型绑定 |
| API | `backend/app/routers/ai/skills.py` | 新字段 + `duplicate` + 优先级加权 + `extra_config.negative_keywords` 负向扣分 |
| API | `backend/app/routers/ai/tools.py` | 新增 `GET /ai/tools/registry`（工具选择器数据源，顺手同步 gateway 动态工具） |
| 前端 | `frontend/src/pages/AIConfigPage.tsx` | 模型 / 助手 / 技能三 Tab（`?tab=` 同步 URL） |
| 前端 | `frontend/src/pages/ai/ModelsPanel.tsx` | 卡片/列表双视图、搜索与筛选、表单抽屉、测试连接、默认/复制/删除/导出 |
| 前端 | `frontend/src/pages/ai/AssistantsPanel.tsx` / `SkillsPanel.tsx` | 新字段、提示词预览、复制、工具/优先级 |
| 前端 | `frontend/src/components/ai/ModelPicker.tsx` / `ToolChipSelect.tsx` / `types.ts` | 模型选择器（未配 Key 禁选）、真实工具清单多选、共享类型 |
| 前端 | `frontend/src/pages/SettingsPage.tsx` | 改为系统设置 + AI 平台入口卡 |
| 前端 | `frontend/src/pages/WorkbenchPage.tsx` | 接入 ModelPicker、消息头显示实际模型、`no_model` 引导按钮 |
| 自检 | `test/check_ai_platform.py` | 12 项无数据库自检（端点/列/迁移/加密/注册表/SSRF/mock 探测） |
| 冒烟 | `test/smoke_ai_platform.py` | 20 项端到端（临时 SQLite）：登录 / 工具注册表 / 模型 CRUD+测试+导出+默认 / 技能解析 / 提示词预览 / SSE 对话落库 |

验证结果：

- `test/check_ai_platform.py`：**12/12 通过**
- `test/smoke_ai_platform.py`：**20/20 通过**（临时 SQLite，覆盖建表、幂等迁移、种子、密钥加密、路由解析、工具注册表、SSE 全链路）
- `tsc -p tsconfig.app.json --noEmit`：**0 error**
- `oxlint src`：**0 error / 8 warning**（均为 `set-state-in-effect`、`only-export-components` 等既有模式告警）
- OpenAPI 生成：AI 相关 **22 条路径 / 28 个操作**全部注册，`/ai/models` 写接口带 `HTTPBearer` 安全声明

## 17. 与参考实现的逐项对照（clone 后核对，2026-10-18）

| # | 参考做法（AIDriveNote） | 本项目处理 | 结论 |
|---|---|---|---|
| 1 | Ollama 走原生 `/api/chat`（`options.temperature`、`images`、NDJSON、`prompt_eval_count`） | 已改为原生适配器，base_url 兼容 `.../v1` 写法自动去除 | **采纳** |
| 2 | `GET /ai/tools/registry` 供工具选择器使用 | 新增 `/ai/tools/registry`，助手/技能表单改为真实工具多选（`ToolChipSelect`） | **采纳** |
| 3 | 技能负向关键词（`extra_config.negative_keywords`，命中扣 40 分） | `resolve` 打分已支持，近义技能不再互相误命中 | **采纳** |
| 4 | 连接测试按 provider 选轻量端点（Ollama `/api/tags`、LM Studio `/v1/models`） | ollama/llamacpp 走轻量探测；其余仍用「1 token 补全」验证模型与密钥 | **采纳并改进** |
| 5 | 密钥掩码占位符 `********` 表示「不修改」 | 用「留空=不修改 + `clearApiKey` 显式清除」表达，避免占位符歧义 | **等价替代** |
| 6 | 密文前缀 `enc::` | 用 `enc:v1:`（带版本号，便于将来轮换算法） | **等价替代** |
| 7 | 端点命名 `/test-connection`、`/assistants/{id}/clone`、201/204 状态码 | 主用 `/test`、`/duplicate`，同时保留 `/test-connection`、`/clone` 别名（不出现在 schema） | **兼容采纳** |
| 8 | 模型/助手的 per-user 默认与所有权（`user_id`，系统种子 `user_id IS NULL`） | 单租户：全局唯一默认 + `is_system` 标记，写操作限管理员 | **不采纳**（§9.3） |
| 9 | 助手-技能绑定表（`ai_assistant_skill_bindings`，带 weight） | 保留 `skill_codes` JSON + 全局 `ai_skills.priority` | **不采纳**（§9.2） |
| 10 | 页面技能绑定（`ai_page_skill_bindings`，按笔记类型过滤） | 无多页面技能路由需求；改用 `extra_config` 预留 | **不采纳** |
| 11 | 附件上传/图片理解（`ai_attachments`、data URL 转换） | 未实现；`supports_image` 与模型字段已预留，`ollama` 原生适配已能解析 `images` | **暂缓** |
| 12 | 429 自动退避重试（provider 子类策略） | 当前直接回传 `code=rate`，由用户重试 | **暂缓**（避免长等待） |
| 13 | 上游错误翻译成中文提示（`_explain_upstream_error`） | 连接测试有分类中文提示；对话侧保留原始错误 + 错误码 | **部分采纳** |
| 14 | Alembic 版本化迁移 | 幂等 ALTER + 独立重放脚本（项目既定过渡方案） | **保持差异** |

未完成/受限项：

1. **PostgreSQL 迁移未实跑**：本机 5432 未监听；SQLite 冒烟已覆盖逻辑链路，但 `ALTER ... JSONB / TIMESTAMPTZ` 只在 PostgreSQL 生效，需在 `start.sh` 环境执行一次 `backend/scripts/migrate_ai_platform.py` 或直接重启后端（启动时自动执行）。
2. **`vite build` 未通过沙箱**：报 `spawn EPERM`（Node 子进程管道限制），非代码问题；`tsc --noEmit` 已覆盖编译期错误。
3. **旧 `backend/app/services/ai/providers.py` 未删除**：沙箱拒绝删除该文件，已改为废弃说明文档；同名包优先生效。建议手工 `git rm backend/app/services/ai/providers.py`。
