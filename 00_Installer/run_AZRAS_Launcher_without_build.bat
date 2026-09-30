@echo off
cd /d "%~dp0"
pyw azras_launcher.py >nul 2>nul
if errorlevel 1 py azras_launcher.py
