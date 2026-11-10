@echo off
rem Double-click me: safe online SQLite backup (collection keeps running), then open the folder.
cd /d "%~dp0"
python -m jc backup
start "" "%~dp0data\backups"
pause
