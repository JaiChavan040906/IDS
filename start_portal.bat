@echo off
rem Starts the Sentinel IDS portal. Keep this window open while you use the site; close it to stop.
cd /d "%~dp0"
rem Without the Data Warehouse tab (use start_portal_dwm.bat for the DWM practical).
set IDS_WAREHOUSE=0
echo Starting Sentinel IDS portal at http://localhost:8001 ...
echo Logins:  admin / admin123    analyst / analyst123
echo Then log in as admin and press "Start replay" on the Overview tab.
start "" "http://localhost:8001"
".venv\Scripts\python.exe" -m uvicorn ids.api.main:app --port 8001
pause
