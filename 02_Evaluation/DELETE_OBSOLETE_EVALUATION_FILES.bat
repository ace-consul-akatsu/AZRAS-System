@echo off
setlocal
cd /d "%~dp0"

del /q "services\feasibility_adjustment_receiver.py" 2>nul
del /q "core\feasibility_adjustment_ui.py" 2>nul
del /q "dev_checks\p161_feasibility_receiver_self_check.py" 2>nul
del /q "services\disaster_recovery_engine_v9_8.py" 2>nul
del /q "data\disaster_recovery_scenarios_v9_8.json" 2>nul
del /q "services\business_cashflow_engine_v9_7.py" 2>nul
del /q "services\module8_cashflow_storage.py" 2>nul

for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D"
del /s /q *.pyc 2>nul

echo AZRAS Evaluation PATCH 208 obsolete-file cleanup completed.
pause
