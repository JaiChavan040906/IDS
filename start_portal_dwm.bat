@echo off
rem Starts the Sentinel IDS portal WITH the Data Warehouse tab (for the DWM practical).
rem start_portal.bat starts the same portal without it. Keep this window open; close it to stop.
cd /d "%~dp0"
set IDS_WAREHOUSE=1
echo Starting Sentinel IDS portal (with WAREHOUSE tab) at http://localhost:8001 ...
echo Logins:  admin / admin123    analyst / analyst123
start "" "http://localhost:8001"
".venv\Scripts\python.exe" -m uvicorn ids.api.main:app --port 8001
pause
