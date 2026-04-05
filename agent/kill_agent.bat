@echo off
setlocal

echo ☢️ screen-connect — NUCLEAR CLEANUP ☢️
echo ---------------------------------------

:: 1. Force kill all known agent process names
echo 🛑 Terminating processes...
taskkill /F /IM WinSystemDiagnostics.exe /T 2>nul
taskkill /F /IM ScreenConnect-Agent.exe /T 2>nul
taskkill /F /IM agent.exe /T 2>nul

:: 2. Remove Registry Persistence (Startup)
echo 🧹 Cleaning Registry...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "WindowsSystemDiagnostics" /f 2>nul

:: 3. Remove Scheduled Task Persistence
echo 📅 Deleting Scheduled Task...
schtasks /delete /tn "Microsoft\Windows\Maintenance\SystemHealthMonitor" /f 2>nul

:: 4. Wipe AppData Directory and Logs
echo 📂 Purging data folders...
set AGENT_DIR=%LOCALAPPDATA%\SystemDiagnostics
if exist "%AGENT_DIR%" (
    rd /s /q "%AGENT_DIR%"
    echo   - Deleted %AGENT_DIR%
)

if exist "%LOCALAPPDATA%\agent_debug.log" (
    del /f /q "%LOCALAPPDATA%\agent_debug.log"
    echo   - Deleted debug log
)

:: 5. Remove Startup Folder .bat legacy files
echo 🏃 Cleaning Startup folder...
set STARTUP_BAT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\WindowsSystemDiagnostics.bat
if exist "%STARTUP_BAT%" (
    del /f /q "%STARTUP_BAT%"
    echo   - Deleted %STARTUP_BAT%
)

echo ---------------------------------------
echo ✅ NUKE COMPLETE. System is clean.
echo ---------------------------------------
pause
