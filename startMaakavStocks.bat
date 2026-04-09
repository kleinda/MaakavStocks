@echo off
chcp 65001 >nul
echo ================================
echo   MaakavStocks - Server
echo ================================
echo.

:: Kill any existing process listening on port 3000
echo Stopping old processes on port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":3000 "') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo Starting server... browser will open in 3 seconds
echo To stop: press Ctrl+C
echo.

:: Open browser after 3 seconds using PowerShell (avoids nested-quote issues in cmd)
start "" powershell -WindowStyle Hidden -Command "Start-Sleep 3; Start-Process 'http://localhost:3000'"
python server.py
pause
