# test/ — 手动联调与排障脚本

本目录存放 Altium 联调阶段保留的 PowerShell 辅助脚本。它们是**手动工具，不是自动化测试**；正式回归测试见 `gateway/tests`（pytest）与根 README 的「测试」章节。

## 使用

```powershell
# 截图（输出到 ../screenshots/shot-<时间戳>.png）
.\test\shot.ps1

# 网关健康检查
.\test\health.ps1

# 桥目录 / 网关链路诊断
.\test\checkbridge.ps1
.\test\verifychain.ps1
```

## 脚本清单

| 文件 | 用途 |
|---|---|
| `shot.ps1` | 全屏截图，保存到 `screenshots/shot-<YYYYMMDD-HHmmss>.png` |
| `crop.ps1` | 按坐标截取屏幕区域：`-X1 -Y1 -X2 -Y2 -Out <路径>` |
| `health.ps1` | 请求 `http://127.0.0.1:3296/health` 并以 JSON 输出 |
| `verifychain.ps1` | 检查桥目录、requests/responses 残留及网关 `/health`、`/tools` |
| `checkbridge.ps1` | 查看 `Documents\AltiumBridge` 目录、诊断文件与 `stop.flag` |
| `check_pas.ps1` | 检查 `AIDriveBridge.pas` 行数、单引号配对与非 ASCII 字符 |
| `checkeol.ps1` | 统计 `AIDriveBridge.pas` 的 CRLF / 裸 LF / 裸 CR |
| `checkbytes.ps1` | 输出文件长度与前 20 字节十六进制 |
| `checkbak.ps1` | 对 `.bak` 备份做换行与字节头检查 |
| `to_crlf.ps1` | 将指定文件转换为 CRLF（DelphiScript 要求） |
| `to_crlf_all.ps1` | 批量转换 `AIDriveBridge.pas/.dfm/.PrjScr` 为 CRLF |
| `force_focus.ps1` | 强制把 Altium 主窗口切到前台（UI 自动化恢复用） |
| `restore_altium.ps1` | 恢复并前置 Altium 窗口（较简版） |
| `check_ai_platform.py` | AI 平台改造自检（无需数据库）：端点、模型/助手/技能新增列、迁移语句、密钥加密、provider 注册表、SSRF 策略、mock 探测 |
| `smoke_ai_platform.py` | AI 平台端到端冒烟（临时 SQLite，不依赖 PostgreSQL）：登录 → 模型 CRUD/测试/导出/默认 → 技能解析 → 提示词预览 → 流式对话 |

运行 AI 平台自检与冒烟：

```powershell
cd backend
..\.venv\Scripts\python.exe -B ..\test\check_ai_platform.py

cd ..
.\.venv\Scripts\python.exe -B test\smoke_ai_platform.py
```

## 注意

- 多数脚本仍含本机硬编码路径（如 `E:\Projects\AIDriveAltium\...`、`C:\Users\SEEYAO\Documents\AltiumBridge`），复用到其他机器前请先改路径或改为参数。
- `run_bridge.ps1` 等依赖固定屏幕坐标的 UI 自动化脚本已删除；启动桥请在 Altium 内手动打开 `gateway\altium_scripts\AIDriveBridge.PrjScr` 并运行 `RunAIDriveBridge`。
- **约定**：新的一次性调试脚本放本目录，不要再写到仓库根目录；确认无长期价值的可直接删除。
