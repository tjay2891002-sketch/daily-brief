@echo off
REM DailyBrief daily launcher (invoked by Task Scheduler).
REM Resolves the project dir from this file's location, so CWD doesn't matter.
setlocal
set "DBDIR=%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%DBDIR%daily_brief.py" >> "%DBDIR%last-run.log" 2>&1
endlocal
