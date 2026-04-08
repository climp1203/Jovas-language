@echo off
REM Jovas Test Runner for Windows
REM Run this from any drive — it automatically switches to the project directory
cd /d "%~dp0"
python test_jovas.py
pause
