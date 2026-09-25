@echo off
setlocal enabledelayedexpansion
set LOG=D:\vic3_data\interface\%~1.log
set "ARGS=%*"
for /f "tokens=1,* delims= " %%a in ("!ARGS!") do set "ARGS=%%b"
cd /d D:\vic3_agent
echo ROUND STARTED args=!ARGS! at !DATE! !TIME! > "!LOG!"
.venv\Scripts\python.exe -m loop.run !ARGS! >> "!LOG!" 2>&1
echo ROUND EXITED code=!ERRORLEVEL! at !DATE! !TIME! >> "!LOG!"
