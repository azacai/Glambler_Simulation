@echo off
rem JC-Autopoll: called by Windows Task Scheduler every 30 minutes.
rem %~dp0 = this bat's own folder, so no hardcoded Chinese path is needed.
cd /d "%~dp0"
if not exist data mkdir data
python -m jc autopoll >> data\autopoll.log 2>&1
