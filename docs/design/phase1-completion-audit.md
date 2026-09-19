# 第一阶段完成度审计（部署运行 + Altium 文件读取查看）

> 日期：2026-09-19 · 范围：用户指令「部署运行项目，包括数据库的安装，连接 altium 先放在第二步，程序运行起来，并且能够具有 altium 文件的读取，查看等」

## 1. 目标对照（逐项证据）

| 要求 | 状态 | 证据 |
|---|---|---|
| 部署运行项目 | ✅ | 后端 uvicorn :3295、前端 vite :3290 运行中；`start.sh` 一键启动；`docker-compose.yml`（pgvector:pg16/redis/backend/frontend+nginx）与双 Dockerfile 供容器化部署 |
| 数据库安装 | ✅ | 本机 PostgreSQL 17.5（postgres@5432），库 `aidrive_altium` 已建，**pgvector 扩展已启用**；`backend/.env` 指向；启动自建表 + 管理员 + mock 模型 |
| 连接 Altium 放第二步 | ✅ | `/api/v1/health` 返回 `gatewayEnabled:false`；「Altium 连接」页为配置占位并展示第二步路线说明 |
| 程序运行起来 | ✅ | 内嵌浏览器实测通过：登录 → 工作台（工程/技能选择）→ 工程列表 → 详情统计卡 → 原理图/PCB/元件/网络/BOM 五个标签页 → 设置页 → 连接页 |
| Altium 文件读取 | ✅ | 上传 → 隔离子进程 worker（ADR-002）→ altium-monkey 解析：jlink 工程 33 元件/44 网络（引脚级 terminals）/33 BOM 行/127 焊盘/554 走线/51 过孔/板框 1795×925mil/32 层叠层，解析 1.4s；sample 工程 1889 走线/81 网络；无 PrjPcb 自动合成工程文件 |
| 查看 | ✅ | 原理图 SVG 完整渲染（截图确认 STM32F103/AMS1117/SWD/LED 全部清晰）；PCB SVG；元件表/网络表（搜索+分页+单端网络红色标记+引脚明细弹窗）/BOM 合并视图（数量聚合、DNP 标记） |

## 2. 实现过程中发现并修复的缺陷

1. passlib 1.7.4 与 bcrypt 5.x 不兼容（启动即崩）→ 移除 passlib 直接使用 bcrypt
2. commit 后访问 server_default 字段（created_at）触发 MissingGreenlet → `db.refresh()`（PLM 陷阱清单再次验证有效）
3. `Message.error.is_("")` 生成非法 SQL `IS $2` → 改 `== ""`
4. `UploadedProject.user_id`(String) 与 UUID 参数在 SQL 中比较 → asyncpg DataError → `str(user.id)`
5. multipart 的 `name` 参数未声明 `Form()` 被静默忽略 → `Form("")`
6. worker：`rectangle_mils` 是带参构造方法而非读取器 → `points_mils` 顶点求包围盒（含 callable 防御）
7. `asyncio.to_thread` 误传 keyword-only 参数 → 显式关键字
8. PCB 渲染对坏嵌入字体（freetype broken table）容错链：默认渲染 → `allow_text_geometry_fallback` → 板框兜底
9. 全局 socks5 代理导致 pip 失败 → 清空代理变量安装；httpx 依赖 no_proxy 直连本地服务

## 3. 本轮已做的改进

- 工程名解析链完善：PrjPcb 名 → 用户命名（经 job 传递）→ 目录名
- snapshot `netCount` 口径统一为快照网络列表长度
- 板框显示单位修正（此前误除 1000 显示成 2×1 mil，现正确显示 1795×925 mil）
- 脏数据清理（上传 500 中断遗留的 `uploaded` 状态行）

## 4. 遗留差距与改进措施（按优先级）

| # | 差距 | 影响 | 改进措施 | 归属 |
|---|---|---|---|---|
| 1 | jlink_pcb.PcbDoc PCB SVG 视口异常（比例失真、文字占位框） | 仅个别文件（该文件含损坏嵌入字体+非零板框原点）；sample 等常规文件渲染验证正常 | worker 增加 viewBox/内容包围盒后处理归一化；向 altium-monkey 上游反馈 | 近期 |
| 2 | 无 Alembic 迁移（启动 create_all） | 后续改表需手写 DDL | 引入 alembic 并生成首个基线版本 | M0 收尾 |
| 3 | 对话历史列表/恢复 UI 缺失 | 刷新后对话不可找回 | 后端 `/ai/conversations` API 已就绪，前端补历史侧栏 | 近期 |
| 4 | AI API Key 明文存储 | 安全 | Fernet 加密落库 + 读取解密 | 近期 |
| 5 | PCB 预览无缩放/层开关 | 大板查看体验 | 前端缩放控件 + visible_layers 选项透出 | 近期 |
| 6 | 测试套件未建立 | 回归无保障 | pytest（auth/chat/worker 协议/快照）+ vitest 冒烟；金标准样例工程入库 docs/evals | M3 前 |
| 7 | SSE 无心跳与断线重连 | 长回答偶发中断体验 | 心跳注释行 + 前端重试 | 近期 |
| 8 | 实时连接（gateway/DelphiScript 桥/MCP）、规则引擎、RAG、元件库、写命令 | 按路线图未开始 | 见 README 路线图与 ADR-001/002 | 第二步起 |

## 5. 运行状态快照

- 前端 http://localhost:3290（vite dev，代理 /api → 3295）
- 后端 http://localhost:3295（uvicorn，/docs 可用）
- 数据：jlink_sch、sample_sch 两个已解析工程；管理员 admin@example.com；演示引擎可对话，配置真实 Key 后切换 provider
