# CLAUDE.md — AIDriveAltium 工程约定速览

## 架构
- 三层：React 前端(3340, 门户子路径 /altium/) ←REST/SSE→ FastAPI 后端(3345) →（第二步）altium-gateway(3296, Windows+Altium)
- 后端模块化单体，功能域分组：`models|services|routers/{group}/`，模块入口 `app/modules/{group}/__init__.py::register_routers`，注册于 `app/modules/__init__.py::ALL_MODULES`
- 表前缀：sys_/ai_/alt_/rvw_/cmp_/bom_/knw_/fls_（见 docs/design/module-conventions.md）

## 关键约定（沿 AIIgnitePLM plm-add-module 技能）
- API 响应 camelCase（`app/schemas.py::CamelModel` alias），前端 buildQuery key 用 snake_case
- 列表端点 `GET /{module}/page` 返回 `{items,total}`；`_apply_filters` 共用；sort 白名单
- 陷阱：DELETE 204 不写返回注解；commit 后访问 server_default 字段前必须 `db.refresh()`（MissingGreenlet）；软删 is_deleted
- 前端页面模式 A/B/C；DataTable 分页同卡贴底；弹出层默认 Modal

## Altium 离线解析（ADR-002）
- `app/worker/altium_files_worker.py`：独立子进程，只 import altium_monkey（AGPL，勿复制其代码进本仓库、勿在后端进程内 import）
- 协议：job.json 进 → result.json 出；快照 schema `aidrive.snapshot.v0`
- 兼容性：无 PrjPcb 自动合成；渲染降级链：默认 → allow_text_geometry_fallback → 板框

## 第二步（未实现）：实时连接
- gateway（Windows）+ DelphiScript 桥（文件乒乓 v1）+ MCP server；写命令走意图命令层（ADR-001），dry-run + 人工确认 + 审计

## 运行
- `bash start.sh`；端口 3340/3345（门户子路径 /altium/）；库 aidrive_altium（pgvector 已启用）
