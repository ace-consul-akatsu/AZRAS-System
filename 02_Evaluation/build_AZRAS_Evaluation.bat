@echo off
cd /d "%~dp0"

echo [AZRAS Evaluation] Checking EXE build dependencies...
python -c "import PyInstaller, numpy, pandas, reportlab" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: EXE build dependencies are missing.
    echo Required: PyInstaller, numpy, pandas, reportlab
    echo Please install the missing package(s) and run this BAT again.
    echo.
    pause
    exit /b 1
)

echo [AZRAS Evaluation] Writing the EXE version resource from VERSION.json...
python build_tools\make_version_info.py
if errorlevel 1 (
    echo.
    echo ERROR: could not write version_info_AZRAS_Evaluation.txt
    pause
    exit /b 1
)

echo [AZRAS Evaluation] Building EXE...
python -m PyInstaller --noconfirm --clean AZRAS_Evaluation.spec
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [AZRAS Evaluation] Build completed successfully.
pause
