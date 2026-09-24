@echo off
setlocal enabledelayedexpansion
set LOG=D:\vic3_data\interface\%~1.log
set ARGS=
:next
shift
if "%~1"=="" goto run
set ARGS=!ARGS! %1
goto next
:run
cd /d D:\vic3_agent
echo ROUND STARTED args=!ARGS! at !DATE! !TIME! > "!LOG!"
"C:\Program Files\Git\usr\bin\timeout.exe" 1500 .venv\Scripts\python.exe -m loop.run !ARGS! >> "!LOG!" 2>&1
echo ROUND EXITED code=!ERRORLEVEL! at !DATE! !TIME! >> "!LOG!"
