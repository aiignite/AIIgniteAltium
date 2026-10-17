# altium-gateway

AIDriveAltium 的局域网网关：部署在**装有 Altium Designer 的 Windows 机器**上，向上提供实时设计访问（查询/截图/受控写操作），并把查询命令暴露为 **MCP server**（Claude Desktop / ZCode 等可直接接入）。

```
AIDriveAltium 后端 ──REST──► altium-gateway :3296 (Windows)
MCP 客户端 ──stdio(MCP)──►        │
                                  ▼ 文件乒乓（行式协议 v1，固定文件名）
                        Altium 内 AIDriveBridge 驻留脚本（TForm + TTimer）
```

## 两种运行模式

| 模式 | 启动方式 | 说明 |
|---|---|---|
| `mock`（默认） | `python -m altium_gateway.app` | 内置演示工程数据（含 PCB/原理图/网络/截图），无 Altium 也能联调整条链路 |
| `live` | `start_gateway.bat`（已设 `ALTIUM_MODE=live`） | 经 `Documents\AltiumBridge` 与 Altium 驻留脚本交换请求/响应 |

## Windows 部署（目标机示例：192.168.1.14）

1. 拷贝本目录到 Windows 机（如 `D:\altium-gateway`）。
2. 右键**以管理员身份运行** `deploy\install.bat`：创建 `.venv`、`pip install -e .`、放行 TCP 3296 入站。
3. 双击 `deploy\start_gateway.bat`（`ALTIUM_MODE=live`，监听 `0.0.0.0:3296`）。
4. Altium 内：`File ▸ Open ▸ Script Project...` 打开 `altium_scripts\AIDriveBridge.PrjScr`，
   在脚本面板双击运行 `RunAIDriveBridge`，弹出桥窗口并保持打开（Start 轮询默认自动开始）。
5. 平台「Altium 连接」页新增 `http://<本机IP>:3296` → 点「测试连接」→ 状态变为已连接 / Altium 在线。

> 桥与网关必须使用同一个桥目录；默认 `%USERPROFILE%\Documents\AltiumBridge`，两侧都可用环境变量覆盖。

## REST API

| 端点 | 说明 |
|---|---|
| `GET /health` | 状态、模式、桥目录、`altiumOnline`、命令数 |
| `GET /tools` | 命令清单（`name/title/description/category/requiresConfirmation/paramsSchema`） |
| `POST /command/{name}` | 执行命令；写命令需 `dry_run` 或 `confirmed` |
| `GET /live/summary` | 聚合实时摘要（工程、PCB 统计、板框、原理图元件/网络，供 LLM 上下文） |
| `GET /screenshot` | 当前窗口截图（PNG；桥不支持时回退本机 `PrintWindow`，再失败返回占位 SVG） |

- `GATEWAY_TOKEN` 设置后，除 `/health` 外都要求 `Authorization: Bearer <token>`；平台连接配置里填同一令牌。
- `POST /command/{name}` 对只读命令失败返回 `502`；写命令的 dry-run 与「待确认」以 200 返回结构化结果。
- **MCP over HTTP 未挂载**：`/mcp` 仅存在于早期设计文档；如需 HTTP 传输，请单独运行 `python -m altium_gateway.mcp_server --http`。

## 命令清单

**只读（8）**

| 命令 | 桥 op | 说明 |
|---|---|---|
| `altium_ping` | `ping` | 桥连通性 |
| `altium_get_project_info` | `get_project_info` | 工程名称/路径/活动文档 |
| `altium_get_schematic_components` | `sch_components` | 原理图元件（位号/值/封装） |
| `altium_get_schematic_nets` | `sch_nets` | 网络标签/电源端口与连接计数 |
| `altium_get_pcb_components` | `pcb_components` | PCB 元件、层、坐标、旋转角 |
| `altium_get_pcb_stats` | `pcb_stats` | 元件/焊盘/走线/过孔/网络/板框/层数 |
| `altium_get_stackup` | `get_stackup` | 板层名称列表 |
| `altium_take_screenshot` | `take_screenshot` | 当前文档画面（live 下 BMP→PNG 并清理临时文件） |

**写操作（3，`requiresConfirmation=true`）**

| 命令 | 桥 op | 参数 | 说明 |
|---|---|---|---|
| `altium_highlight_net` | `pcb_highlight_net` | `net`, `mode` | 高亮/取消高亮网络（仅视觉，不改设计） |
| `altium_move_component` | `pcb_move_component` | `designator`, `x`, `y` | 移动 PCB 元件（mils） |
| `altium_rotate_component` | `pcb_rotate_component` | `designator`, `rotation` | 旋转 PCB 元件（0–360°） |

### 写操作确认流程（ADR-001 首版）

> 下列坐标为 mock 驱动的示例数据，live 模式会返回真实元件当前坐标。

```text
POST /command/altium_move_component {"designator":"U1","x":1000,"y":2000}
  → {"ok":false,"requiresConfirmation":true,"error":"…请先带 dry_run=true 预览，再带 confirmed=true 执行"}

POST /command/altium_move_component {"designator":"U1","x":1000,"y":2000,"dry_run":true}
  → {"ok":true,"dryRun":true,"preview":"将元件 U1 从 (2000mils, 1500mils) 移动到 (1000mils, 2000mils)","current":{…}}

POST /command/altium_move_component {"designator":"U1","x":1000,"y":2000,"confirmed":true}
  → {"ok":true,"command":"altium_move_component","designator":"U1","x":1000,"y":2000}
```

- dry-run 会通过只读 `pcb_components` 查询定位元件并生成具体预览；缺参数/未找到元件时直接返回错误。
- `dry_run`/`dryRun`/`confirmed`/`confirm` 为控制参数，不会下发给桥。
- 平台侧（AI 工具链）会自动先 dry-run 再弹确认卡，用户确认后才以 `confirmed=true` 执行。

## MCP 接入

stdio 入口：`altium-gateway-mcp`（或 `python -m altium_gateway.mcp_server`），暴露 8 个查询工具。

```json
{
  "mcpServers": {
    "altium": { "command": "D:\\altium-gateway\\.venv\\Scripts\\altium-gateway-mcp.exe" }
  }
}
```

> MCP 工具当前只包含只读命令；写命令请走 REST + 确认流程，避免绕过人工确认。

## 桥协议 v1

为适配 DelphiScript（无 JSON 解析器），协议采用行式文本，值中不得含换行或 `|`。

请求 `requests/request.txt`：

```
OP|pcb_stats
OP|pcb_move_component|designator=U1|x=1000|y=2000
END|<requestId>
```

响应 `responses/response.txt`：

```
RES|0|OK|components=5|pads=62|tracks=310|vias=24|nets=29
RES|1|OK|designator=U1|x=1000|y=2000
END|<requestId>
```

- 同一 op 可多行 `RES|idx|ITEM|…`，聚合为 `items`；`ERR` 行表示该 op 失败。
- 传输固定使用 `request.txt` / `response.txt`（规避 DelphiScript 目录枚举问题）；驱动写前先占位、写后轮询响应、读到即清理，超时默认 20s。
- 桥 op 全集：`ping / get_project_info / sch_components / sch_nets / pcb_components / pcb_stats / get_stackup / take_screenshot / pcb_highlight_net / pcb_move_component / pcb_rotate_component`。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `ALTIUM_MODE` | `mock` | `mock` / `live` |
| `ALTIUM_BRIDGE_DIR` | `%USERPROFILE%\Documents\AltiumBridge` | 与桥脚本共享目录 |
| `GATEWAY_PORT` | `3296` | 监听端口 |
| `GATEWAY_HOST` | `0.0.0.0` | 监听地址 |
| `GATEWAY_TOKEN` | 空 | 静态令牌 |
| `ALTIUM_OP_TIMEOUT` | `20` | 单次桥事务超时（秒） |

## 测试

```powershell
cd gateway
.\.venv\Scripts\python.exe -m pytest -q      # 12 passed：协议编解码、命令注册表、dry-run/确认、mock 驱动
```

`live_verify_write.py` 为真机联调辅助脚本，可在 live 模式下逐条验证查询与写命令。

## 排查

| 现象 | 排查 |
|---|---|
| 平台测试连接失败 | `netstat -ano \| findstr 3296`；防火墙「AIDriveAltium Gateway」规则；两机是否同网段（Windows 默认拦 ping，不代表离线） |
| `altiumOnline=false` | Altium 内桥窗口是否仍在运行；桥目录是否与网关一致；`requests` 目录是否可写 |
| 命令超时（>20s） | 桥脚本是否卡在模态对话框；Altium 是否在后台被阻塞；可临时调大 `ALTIUM_OP_TIMEOUT` |
| 截图为占位图 | 桥不支持 GDI 截图属预期；检查 Altium 主窗口标题是否含 `Altium Designer`、是否被最小化 |
| 401 invalid gateway token | 网关 `GATEWAY_TOKEN` 与平台连接配置中的令牌是否一致 |

## 安全与限制

- 默认无 TLS，仅限受信局域网；对外暴露前请加反向代理与认证。
- 写命令已有 dry-run + 人工确认，但**尚无命令审计、撤销栈与事务回滚**（ADR-001 规划中），请先在测试工程验证。
- Altium 版本差异：脚本按公开 RTL API 编写并逐字段 `try/except`，个别版本仍可能需要微调。
