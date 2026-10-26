@echo off
rem Resets the Sentinel IDS portal to a clean state (empty alerts, decisions, Knowledge Repository,
rem retraining jobs and audit log) and starts it again. The trained AI model, datasets and the
rem data warehouse are NOT touched.
cd /d "%~dp0"
echo This will clear all alerts, analyst decisions, KR incidents, retraining jobs and the audit log.
echo The AI model, datasets, warehouse and code are not changed.
choice /m "Continue"
if errorlevel 2 exit /b

rem 1) Stop any running portal of this project (it keeps data\ids.db open, so it could not be deleted).
echo Stopping any running Sentinel portal...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*ids.api.main:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

rem 2) Back up the whole database: the data lives in ids.db AND ids.db-wal, so copy all three files.
if not exist data\backup mkdir data\backup
if exist data\ids.db     copy /y data\ids.db     data\backup\ids_before_reset.db     >nul
if exist data\ids.db-wal copy /y data\ids.db-wal data\backup\ids_before_reset.db-wal >nul
if exist data\ids.db-shm copy /y data\ids.db-shm data\backup\ids_before_reset.db-shm >nul

rem 3) Delete and check. A just-stopped portal can take a few seconds to release the files,
rem    so try up to 10 times, one second apart.
set /a tries=0
:retry
del /q data\ids.db data\ids.db-wal data\ids.db-shm 2>nul
if not exist data\ids.db if not exist data\ids.db-wal goto deleted
set /a tries+=1
if %tries% geq 10 goto locked
timeout /t 1 /nobreak >nul
goto retry

:deleted
echo Done. The previous database was copied to data\backup\ids_before_reset.db (+ -wal, -shm).
echo Starting a fresh portal...
call "%~dp0start_portal.bat"
exit /b

:locked
echo.
echo Could not delete the database - something still has it open.
echo Close every Sentinel portal window (black windows running start_portal) and run this file again.
pause
exit /b 1
