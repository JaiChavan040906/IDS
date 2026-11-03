@echo off
rem Starts the Sentinel IDS portal with a PUBLIC link (Cloudflare quick tunnel) so it can be opened
rem from any phone or computer. The link works only while this window stays open.
rem Uses its own fresh database (data\ids_public.db) and the passwords you type below, so your
rem normal data and the demo logins on this laptop are not touched.
cd /d "%~dp0"
set PORT=8001

if not exist tools\cloudflared.exe (
  echo tools\cloudflared.exe is missing. See docs\PUBLIC_LINK.md.
  pause
  exit /b 1
)

echo ============================================================
echo   Sentinel IDS - public link
echo ============================================================
echo Anyone with the link can open the site, so choose your own passwords.
echo.
set "IDS_ADMIN_PASSWORD="
set "IDS_ANALYST_PASSWORD="
set /p "IDS_ADMIN_PASSWORD=Password for admin   : "
set /p "IDS_ANALYST_PASSWORD=Password for analyst : "
if "%IDS_ADMIN_PASSWORD%"=="" goto nopass
if "%IDS_ANALYST_PASSWORD%"=="" goto nopass
if /i "%IDS_ADMIN_PASSWORD%"=="admin123" goto weakpass
if /i "%IDS_ANALYST_PASSWORD%"=="analyst123" goto weakpass

rem Stop any portal already running on this laptop (only one can use the port).
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*ids.api.main:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force"
powershell -NoProfile -Command "Start-Sleep 2" < nul

rem Fresh public database every time, so the passwords above always apply.
del /q data\ids_public.db data\ids_public.db-wal data\ids_public.db-shm 2>nul
set IDS_DB_URL=sqlite:///data/ids_public.db
set IDS_WAREHOUSE=0

echo.
echo Starting the portal (a minimised window "Sentinel portal" opens - leave it running)...
start "Sentinel portal" /min ".venv\Scripts\python.exe" -m uvicorn ids.api.main:app --port %PORT%

echo Waiting for the portal, then opening the public link (about a minute)...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\public_link.ps1 -Port %PORT% < nul
if errorlevel 1 goto fail

echo.
echo Keep this window open while people use the link.
echo Press any key here to STOP the public link and the portal.
pause >nul
goto stop

:fail
echo.
pause
:stop
powershell -NoProfile -Command "Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*ids.api.main:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Stopped. The public link no longer works.
exit /b

:nopass
echo Both passwords are needed. Run this file again.
pause
exit /b 1

:weakpass
echo Please choose passwords different from the demo ones (admin123 / analyst123). Run this file again.
pause
exit /b 1
