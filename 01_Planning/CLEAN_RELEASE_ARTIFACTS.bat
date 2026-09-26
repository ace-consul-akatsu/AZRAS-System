@echo off
setlocal
cd /d "%~dp0"

echo [AZRAS] Removing verified non-runtime development artifacts...

rem Python runtime caches
for /d /r %%D in (__pycache__) do (
  if exist "%%D" rd /s /q "%%D"
)
for /r %%F in (*.pyc) do (
  if exist "%%F" del /q "%%F"
)
for /r %%F in (*.pyo) do (
  if exist "%%F" del /q "%%F"
)

rem Obsolete historical patch/audit notes. These files are not imported or opened by runtime code.
for %%F in (
  APPLY_LOCATION.txt
  ENGLISH_CANONICAL_AUDIT_PATCH_282.txt
  FINAL_AUDIT_3_METHODS.txt
  PATCH_264_README.txt
  PATCH_NOTE.txt
  REPAIR_NOTE.txt
  SELF_CHECK_P025.txt
  VALIDATION.txt
) do (
  if exist "%%F" del /q "%%F"
)

rem Retain the current PATCH_378 audit note, remove older stabilization audit notes if present.
for %%F in (PATCH_*_STABILIZATION_AUDIT.md) do (
  if /I not "%%~nxF"=="PATCH_378_STABILIZATION_AUDIT.md" del /q "%%F"
)

echo [AZRAS] Release-artifact cleanup complete.
endlocal
