@echo off
echo ============================================
echo   ScreenConnect Agent v2 — Build Installer
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

echo Building standalone .exe (GUI mode, no console)...
echo.

pyinstaller --onefile ^
    --noconsole ^
    --name ScreenConnect-Agent ^
    --hidden-import=mss ^
    --hidden-import=mss.windows ^
    --hidden-import=cv2 ^
    --hidden-import=numpy ^
    --hidden-import=pyautogui ^
    --hidden-import=websocket ^
    --hidden-import=tkinter ^
    --hidden-import=psutil ^
    --hidden-import=pyperclip ^
    --hidden-import=zlib ^
    --hidden-import=struct ^
    --hidden-import=shutil ^
    --hidden-import=pathlib ^
    --hidden-import=subprocess ^
    agent.py

echo.
if exist "dist\ScreenConnect-Agent.exe" (
    echo =============================================
    echo   BUILD SUCCESS!
    echo   Output: dist\ScreenConnect-Agent.exe
    echo =============================================
    echo.
    echo Send this .exe to your client. They just:
    echo   1. Double-click ScreenConnect-Agent.exe
    echo   2. Enter the Server URL, Session ID, and Token
    echo   3. Click "Connect and Share Screen"
) else (
    echo BUILD FAILED — check errors above
)
echo.
pause
