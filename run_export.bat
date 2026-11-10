@echo off
rem Double-click me: export all SQLite tables to CSV, then open the exports folder.
cd /d "%~dp0"
python -m jc export
start "" "%~dp0exports"
pause
