@echo off
rem AIDriveAltium gateway Windows 一键安装（需管理员权限：将添加防火墙规则）
rem 用法：在装有 Altium Designer 的 Windows 机器上，把整个 gateway 目录拷贝过来后右键"以管理员身份运行"

setlocal
cd /d %~dp0..

echo == 检查 Python ==
python --version >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.10+ 并勾选 "Add to PATH"
  pause & exit /b 1
)

echo == 创建虚拟环境并安装依赖 ==
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -e "%CD%"

echo == 配置 ==
rem 如需真实桥接模式（连 Altium），设置 ALTIUM_MODE=live；默认 mock 仅联调
set ALTIUM_MODE=live
set GATEWAY_PORT=3296
rem set GATEWAY_TOKEN=your-secret

echo == 添加防火墙规则（TCP 3296 入站）==
netsh advfirewall firewall delete rule name="AIDriveAltium Gateway" >nul 2>&1
netsh advfirewall firewall add rule name="AIDriveAltium Gateway" dir=in action=allow protocol=TCP localport=3296

echo.
echo == 安装完成 ==
echo 启动方式：双击 deploy\start_gateway.bat
echo Altium 侧：打开 gateway\altium_scripts\AIDriveBridge.PrjSrc 并运行 RunAIDriveBridge
pause
