# ADR-002: 采用 altium-monkey 作为离线文件通道引擎（含 AGPL 合规策略）

> 状态：已接受 · 日期：2026-09-19
> 关联：[ADR-001](ADR-001-semantic-to-design-execution.md)（实时写路径不受影响）· [llm-max-assist-analysis](../llm-max-assist-analysis.md) §2.1 感知层
> 参考：[wavenumber-eng/altium_monkey](https://github.com/wavenumber-eng/altium_monkey)（PyPI: altium-monkey，AGPL-3.0-or-later，Python 3.12–3.14，Windows/macOS arm64/Linux wheel）

## 问题

原方案 M2 离线通道计划"移植 AIDriveEDA 解析代码 + 自研归一化模型"。altium-monkey（团队此前使用过）提供了成熟的 headless 读写/分析/渲染能力，需确定其在系统中的定位与合规方式。

## 决策

**采用 altium-monkey 作为离线文件通道的引擎，以独立 worker 进程隔离运行（AGPL 合规）；实时交互写路径维持 ADR-001（只走 DelphiScript 桥）不变。**

### 用武之地（映射里程碑）

| 场景 | altium-monkey 能力 | 落点 |
|---|---|---|
| **M2 离线解析主力** | `.PrjPcb/.SchDoc/.PcbDoc/.SchLib/.PcbLib` 解析；`AltiumDesign.from_prjpcb().to_json()` 输出 schema 版本化的 design JSON（design_b0）+ netlist JSON + compiled_schematic_graph（含层次化通道） | design JSON 经适配层包装为本系统的归一化设计快照；不再自研底层解析器，AIDriveEDA 移植代码降级为兜底 |
| **M2 预览渲染** | 原理图 SVG（逻辑+编译物理视图）、PCB SVG | 前端预览画布数据源，替代移植 AIDriveEDA 渲染器 |
| **M3 审查与评测** | layers/drills/outline/nets/net classes/tracks/pads/vias/components 类型化列表；项目级批处理 | 规则引擎的离线数据源；金标准集批跑与**设计 diff**（语义→设计端到端评测用）无需启动 Altium |
| **M3 BOM/变体** | 变体处理（DNP、参数覆盖） | BOM 模块变体支持 |
| **M4 元件库生成** | 创建原理图符号与 PCB 封装、插入 SchLib/PcbLib、IntLib 提取 | 元件库生成管线（可替代 Rust 版 altium-designer-mcp 的 IPC 封装生成思路） |
| **M5+ 生产文件** | Windows + Altium 安装环境下可运行 OutJob | gateway 侧生产文件（Gerber/贴片/装配图）批量产出通道 |
| **日常兜底** | 纯 Python、macOS arm64 wheel | "无 Altium 开发模式"；桥查询结果与文件解析的交叉验证 |

### 边界（不改变 ADR-001 的部分）

1. **交互式写仍只走桥**：PcbDoc 侧尚无通用对象删除 API（helper-oriented），铺铜缓存/连通性等派生数据的就地修改仍有风险——库文件的就地改写不进交互链路。
2. **离线写仅限 ADR-001 受控例外**：新建文档/元件库/模板工程由 altium-monkey 生成（此项能力现已被其显著强化），产物经人工在 Altium 中打开验证后入库。
3. PcbDoc 的 ObjectCollection 化与删除 API 落地后，可评估扩大离线写范围（跟踪其 RELEASE_NOTES）。

### AGPL-3.0 合规策略

1. **进程隔离**：altium-monkey 运行于独立 worker 进程/容器（`altium-files-worker`），与后端通过内部 REST/队列通信——构成聚合（aggregation）而非链接，本系统代码不与之形成衍生作品。
2. **不修改其源码**：只 pip 依赖官方版本；确需修改时按 AGPL 义务公开该 worker 的修改。
3. **不复制其代码**进本仓库。
4. **部署形态评估**：纯内部企业部署风险低；一旦对外提供服务或对外分发，重新评估——供应商为商业实体（文档出现 support contract 表述），必要时洽谈商业授权。

## 验证行动（纳入 M0）

Spike：`pip install altium-monkey`，用团队真实历史工程（多个 Altium 版本）验证 design JSON 完整性、SVG 渲染质量、解析耗时；确认 macOS 本机与 Windows worker 两侧行为一致。
