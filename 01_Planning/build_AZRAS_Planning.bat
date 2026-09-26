@echo off
setlocal
cd /d "%~dp0"
echo AZRAS Planning - Windows build (version: VERSION.json)
py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error
rem PATCH_048: regenerate the EXE version resource from VERSION.json.
py build_tools\make_version_info.py
if errorlevel 1 goto :error
py -m PyInstaller --clean --noconfirm AZRAS_Planning.spec
if errorlevel 1 goto :error
echo Build completed: dist\AZRAS_Planning\AZRAS_Planning.exe
pause
exit /b 0
:error
echo Build failed.
pause
exit /b 1
