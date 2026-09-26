@echo off
cd /d D:\vic3_agent
echo DASHBOARD STARTED at %DATE% %TIME% > D:\vic3_data\interface\dashboard.log
.venv\Scripts\python.exe -m dashboard.server >> D:\vic3_data\interface\dashboard.log 2>&1
echo DASHBOARD EXITED code=%ERRORLEVEL% at %DATE% %TIME% >> D:\vic3_data\interface\dashboard.log
