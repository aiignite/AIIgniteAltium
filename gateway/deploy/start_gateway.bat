@echo off
rem 启动 altium-gateway（实时桥模式）
cd /d %~dp0..

set ALTIUM_MODE=live
set GATEWAY_PORT=3296
rem set GATEWAY_TOKEN=your-secret

if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo AIDriveAltium gateway 启动中: http://0.0.0.0:3296  (Ctrl+C 停止)
python -m altium_gateway.app
pause
