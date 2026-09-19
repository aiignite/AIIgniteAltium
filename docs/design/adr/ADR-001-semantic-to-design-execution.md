# ADR-001: 语义描述到 Altium 设计输出的执行路径

> 状态：已接受 · 日期：2026-09-19
> 关联：[llm-max-assist-analysis.md](../llm-max-assist-analysis.md) §2.2 行动层

## 问题

自然语言设计描述（"给 U1 每个电源引脚加 100nF 去耦电容，0402，放背面"）如何变成 Altium 中的实际设计变更？候选路径：

- A. 直接修改 Altium 文件（.SchDoc/.PcbDoc）
- B. 通过 Altium API（脚本桥）
- C. 设计一层"优秀的语义命令"，把语义识别编译为命令

## 决策

**C 不是 B 的替代，而是 B 之上的分层：写操作 100% 走 API 脚本桥（B）；语义识别只面对一个结构化的"意图命令层"（C）；文件直改（A）从写路径中排除，仅保留只读解析与两个受控例外。**

### 路径对比

| 维度 | A. 直接改文件 | B. API 脚本桥 |
|---|---|---|
| 可靠性 | 高风险：格式未公开、随版本漂移、部分写入易损坏（连通性缓存/胶合数据） | 官方支持面，由 Altium 自身持久化 |
| 实时性 | 离线，需重开项目，与打开的会话冲突 | 活会话，立即可见、可撤销 |
| 一致性 | 网络连通性、铺铜缓存等派生数据无法正确重建 | Altium 自动维护 |
| 撤销 | 无 | 有 Undo 栈，命令边界可作撤销边界 |
| 生态成熟度 | AltiumSharp(.NET) 读写最全但维护有限；Python 侧仅只读 | altium-mcp / eda-agent 均走此路 |

A 的两个受控例外：① 只读解析（M2 通道，已定）；② 离线生成全新文件（如用 AltiumSharp 生成 .SchLib/.PcbLib 元件库、模板工程），产物经人工在 Altium 中打开验证后入库，不做在库文件的就地修改。

Altium 三种 API 的澄清：**脚本 API（DelphiScript，进程内 RTL 对象模型）是唯一能操作设计对象的通道**；COM(X2.EXE) 仅能启动/附加（作启动器）；Altium 365 REST 只覆盖工作区数据（项目/发布/BOM），不能编辑设计内容（作云侧集成）。

## 语义 → 设计的完整管线

```
自然语言设计描述
   │ ① LLM 意图解析（function calling，选命令+填参数，不做几何）
   ▼
结构化意图命令 JSON（受 JSON Schema 约束，命令库版本化）
   │ ② 校验器：Schema 校验 + 语义校验（引脚/网络存在？参数在范围内？）
   │ ③ dry-run：展开为操作序列 + 影响面说明 → 前端确认卡（写操作必经）
   ▼
命令执行器（gateway 内，确定性 Python，无 AI）
   │ ④ 每条命令 = 编译为底层 API 原语操作序列（一次桥事务批量下发）
   ▼
DelphiScript 桥（Altium 内）→ Altium 活动文档对象
   │ ⑤ 后验证：关联规则重查 + 截图回读
   ▼
结果回喂 LLM（自我修正循环）→ 审计入库（命令+展开操作+结果）
```

**分工铁律**：LLM 负责"语义 → 命令选择与参数 → 计划 → 解释"；命令层负责"命令 → 操作序列"（确定性、可单测）；桥负责"操作 → Altium 对象"。语义理解永远不进 gateway，几何计算永远不进 LLM。

## 意图命令层设计要点（"优秀的命令"的定义）

1. **意图粒度命名**：`add_decoupling_network{ic_ref, spec?, placement?}`，而非 `place_component(x,y)`。几何换算在命令实现内完成。
2. **Schema 化 + 版本化**：每条命令一个 JSON Schema；命令注册表带版本号，旧会话不受新命令影响。注册表直接映射为 MCP tools（M1 起 tools 即按此设计）。
3. **确定性**：同输入同输出，可用快照回放做单元测试（CI 中 mock Altium 对象跑命令回归）。
4. **dry-run/预览**：所有写命令支持 `dry_run=true`，返回将执行的操作序列与影响面（动哪些网络/元件），人在回路确认。
5. **事务性**：一次命令 = 一次桥事务 = 一个撤销单元；失败整体回滚（脚本内操作序列撤销；重要命令前文件快照兜底）。
6. **幂等**：请求带 id，支持安全重试。
7. **查询与写对称**：先查后写，LLM 依赖 `find_*` 系列自查（`find_pins(filter=...)`、`get_net_topology`、`find_violations`）。

### 命令集三层

| 层 | 示例 | 说明 |
|---|---|---|
| 原语层 | `place_component` `move_objects` `assign_net` `set_parameter` `set_rule` `add_track` | 正交、完备，供组合与人工点名 |
| 意图层 | `add_decoupling_network` `fanout_bga` `add_testpoints` `apply_thermal_reliefs` `create_power_rail` | LLM 主战场，M5 起建 |
| 查询层 | `find_pins/nets/components` `get_stackup` `get_net_topology` `find_violations` | 感知与自检依赖，M1 先行 |

## 从零创建新设计的补充路径

"创建 STM32 最小系统"类从零生成：**企业电路模块模板库 + 参数化**（Celus 模式）优于自由生成——LLM 选择模板、填参数、规划互连，模板携带已验证的设计意图。模板执行同样编译为意图命令序列。SKiDL/网表中转仅作为离线导入的辅助选项，不进交互主链路。

## 落地

- M1：命令注册表框架 + 查询层命令 + 原语层只读部分；桥协议含批量事务（一条命令一次往返）
- M5：原语写命令 + 首批意图命令 + dry-run 确认卡 + 撤销/快照 + 审计
- 评测：命令层单测（快照回放）+ 端到端金标准用例（语义描述 → 期望设计差异 diff）
