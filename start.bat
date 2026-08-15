@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=C:\Users\24895\AppData\Local\Microsoft\WindowsApps\python.exe"

echo 启动服务（页面 + 豆包OCR代理，统一地址 http://127.0.0.1:5000）...
start "Bullfrog Server" "%PY%" paddle_server.py

echo 等待服务启动...
timeout /t 2 >nul

echo 正在打开浏览器...
start http://127.0.0.1:5000/

echo.
echo 如浏览器未自动打开，请手动访问：http://127.0.0.1:5000/
echo 关闭本窗口不会停止服务，需停止时请关闭名为 "Bullfrog Server" 的命令行窗口。
pause
