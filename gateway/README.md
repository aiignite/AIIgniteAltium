# altium-gateway

AIDriveAltium 的局域网网关：部署在**装有 Altium Designer 的 Windows 机器**上，向平台提供实时设计访问（查询/截图），并把同一组命令暴露为标准 **MCP server**（可供 Claude Desktop / ZCode 等直接使用）。

## 架构

```
AIDriveAltium 后端(3295) ──REST──► altium-gateway(3296, Windows)
Claude/ZCode 等 MCP 客户端 ──MCP──►      │
                                        ▼ 文件乒乓（行式协议 v1）
                              Altium 内 AIDriveBridge 驻留脚本(TForm+TTimer)
```

## Windows 部署（目标机示例：192.168.1.14）

1. 拷贝本目录到 Windows 机（如 `D:\altium-gateway`）
2. 右键**以管理员身份运行** `deploy\install.bat`（装依赖 + 开防火墙 3296）
3. 双击 `deploy\start_gateway.bat`（`ALTIUM_MODE=live`）
4. Altium 中：`File ▸ Open ▸ Script Project...` 打开 `altium_scripts\AIDriveBridge.PrjSrc`，
   在脚本面板双击运行 `RunAIDriveBridge`，弹出桥窗口保持打开（Start 轮询默认自动开始）
5. 平台「Altium 连接」页新增 `http://<本机IP>:3296` → 点"测试连接"

## 两种模式

| 模式 | 说明 |
|---|---|
| `ALTIUM_MODE=mock`（默认） | 内置演示数据，无 Altium 也能联调整条链路 |
| `ALTIUM_MODE=live` | 经 `Documents\AltiumBridge` 目录与 Altium 驻留脚本交换请求/响应（v1 文件乒乓） |

## REST API

| 端点 | 说明 |
|---|---|
| `GET /health` | 健康与桥状态 |
| `GET /tools` | 命令清单（含 requires_confirmation 元数据） |
| `POST /command/{name}` | 执行命令（8 个只读命令：ping/工程信息/原理图元件与网络/PCB 元件与统计/叠层/截图） |
| `GET /live/summary` | 聚合实时设计摘要（LLM 上下文用） |
| `GET /screenshot` | 当前窗口截图（svg/png） |
| `POST /mcp` | MCP streamable HTTP |

## MCP 客户端接入（Claude Desktop / ZCode 示例）

```json
{
  "mcpServers": {
    "altium": {
      "command": "D:\\altium-gateway\\.venv\\Scripts\\altium-gateway-mcp.exe"
    }
  }
}
```

## 安全

- v1 命令全部只读；写命令将按 ADR-001 的意图命令层在 M5 引入（dry-run + 人工确认 + 审计）
- 可设置 `GATEWAY_TOKEN`，平台连接配置里填同一令牌
