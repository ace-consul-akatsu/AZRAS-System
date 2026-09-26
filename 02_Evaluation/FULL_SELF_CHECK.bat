@echo off
cd /d "%~dp0"
python full_self_check.py
if errorlevel 1 (
    echo.
    echo Full self check failed.
    pause
    exit /b 1
)
echo.
echo Full self check completed successfully.
pause
