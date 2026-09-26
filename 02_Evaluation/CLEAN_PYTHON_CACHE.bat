@echo off
setlocal
cd /d "%~dp0"
echo Removing Python runtime cache folders...
for /d /r %%D in (__pycache__) do (
  if exist "%%D" rd /s /q "%%D"
)
for /r %%F in (*.pyc) do (
  if exist "%%F" del /q "%%F"
)
echo Cleanup complete.
endlocal
