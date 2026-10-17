# AIDriveAltium 前端

AIDriveAltium 的 Web 工作台：登录、AI 对话（助手 + 技能 + 工具确认）、工程文件解析与查看、Altium 实时连接、模型/技能管理。

## 技术栈

| 类别 | 选型 |
|---|---|
| 框架 | React 19 + TypeScript |
| 构建 | Vite 8（`tsc -b` 类型检查 + 构建） |
| UI | Mantine 9（AppShell / Modal / Drawer / Table）、Tabler Icons |
| 路由 | react-router-dom 7（`BrowserRouter basename={BASE_URL}`） |
| 代码检查 | oxlint（`.oxlintrc.json`） |
| 部署 | nginx（容器）+ 门户子路径 `/altium/` |

## 本地开发

```bash
cd frontend
npm install
npm run dev        # http://localhost:3290，/api 代理到 http://127.0.0.1:3295
```

先启动后端（`uvicorn app.main:app --port 3295`）。其他命令：

```bash
npm run lint       # oxlint
npm run build      # tsc -b && vite build
npm run preview    # 预览构建产物
```

### 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `VITE_BASE_PATH` | `/` | 部署基路径；门户部署设为 `/altium/`，API 基址随之变成 `/altium/api/v1` |

端口与代理在 `vite.config.ts`：dev 端口 **3290**，代理前缀 `${base}/api` → `http://127.0.0.1:3295`（超时 600s，适配长回答 SSE）。生产容器由 nginx 监听 80，宿主映射 3340。

## 目录结构

```
frontend/
├─ src/
│  ├─ main.tsx                 # MantineProvider + BrowserRouter
│  ├─ App.tsx                  # 路由与登录守卫
│  ├─ api/client.ts            # fetch 封装、Token、buildQuery、SSE streamChat
│  ├─ contexts/AuthContext.tsx # 登录态（localStorage: aidrive_token）
│  ├─ components/
│  │  ├─ AppLayout.tsx         # 侧边导航 + 顶栏
│  │  ├─ DesignDataTabs.tsx    # 原理图/PCB/元件/网络/BOM 数据页
│  │  └─ ai/                   # AssistantPicker、AssistantAvatar、SkillActivationCard
│  ├─ pages/
│  │  ├─ LoginPage.tsx
│  │  ├─ WorkbenchPage.tsx     # 对话 + 设计画布 + 实时 PCB 面板 + 工具确认卡
│  │  ├─ ProjectsPage.tsx      # 上传/列表/重解析/删除
│  │  ├─ ProjectDetailPage.tsx # 工程详情与统计卡
│  │  ├─ AssistantsPage.tsx    # 助手卡片网格 + 技能库
│  │  ├─ ConnectionsPage.tsx   # 网关 CRUD/测试/实时面板
│  │  └─ SettingsPage.tsx      # 模型配置
│  └─ index.css                # 主题与 .ai-* 样式
├─ nginx.conf                  # /altium/api/ 与 /api/ 反代、SSE 关闭缓冲、100MB 上传
├─ vite.config.ts
└─ Dockerfile                  # node 构建 → nginx 静态托管
```

## 路由

| 路径 | 页面 |
|---|---|
| `/` | 对话工作台（默认） |
| `/assistants` | AI 助手与技能库 |
| `/projects` | 工程文件列表/上传 |
| `/projects/:projectId` | 工程详情（五类数据页） |
| `/connections` | Altium 实时连接 |
| `/settings` | AI 模型配置 |
| `*` | 重定向到 `/` |

未登录时统一渲染登录页；401 会清 Token 并回到登录。

## 接口约定

- 基址：`${import.meta.env.BASE_URL}/api/v1`。
- 响应体为 camelCase；查询参数用 snake_case（`buildQuery` 会自动省略空值）。
- 工程数据的列表分页端点（components / nets / bom）返回 `{items, total}`。
- 上传用 `FormData`（`api.postForm`），不手动设置 `Content-Type`。
- 对话走 `POST /ai/chat/stream`，`api/client.ts::streamChat` 按 SSE 逐事件回调：

| 事件 | 用途 |
|---|---|
| `meta` | 会话 id、标题、助手信息 |
| `skills_activated` | 技能激活卡 |
| `delta` | 文本增量 |
| `tool_call` / `tool_result` | 工具调用与结果卡片 |
| `tool_confirmation_required` | 写操作确认卡（工具名/参数/预览） |
| `error` / `done` | 异常与结束 |

「确认执行」直接调用 `POST /altium/connections/{id}/command`（附 `confirmed: true`），不经过模型二次生成。

## 构建与部署

```bash
npm run build      # 产物在 dist/
docker build -t aidrive-altium-web .
```

- nginx 同时支持两种访问方式：`/`（独立部署）与 `/altium/`（门户子路径，`alias` + `try_files` 回退到 `index.html`）。
- `/api/` 与 `/altium/api/` 都反代到 `backend:3295`，并关闭 `proxy_buffering` 以支持 SSE。
- 上传体积上限 100MB（`client_max_body_size`）。

## 约定与注意

- 页面模式沿 `docs/design/module-conventions.md`：列表与详情分离，弹层默认 Modal（实时面板用右侧 Drawer），分页控件与卡片底部对齐。
- 不在前端存储模型 API Key；Key 由后端配置（当前为明文存储，见根 README 的已知限制）。
- 目前没有前端自动化测试；改动后至少执行 `npm run lint && npm run build`，并手测登录 → 上传 → 对话 → 连接主链路。
- 后端 dev 端口为 3295；若改用其他端口，请同步修改 `vite.config.ts` 的 `proxy.target`。
