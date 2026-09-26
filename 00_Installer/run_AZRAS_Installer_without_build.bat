@echo off
cd /d "%~dp0"
if exist "config" rmdir "config" >nul 2>nul
py azras_installer.py
if errorlevel 1 pause
