@echo off
REM Start-SENTRY.bat - double-click to run the whole console.
REM Boots Postgres, the API (8077) and the console (8080), then opens it.
setlocal
cd /d "%~dp0"

echo === SENTRY launcher ===
where docker >nul 2>&1
if errorlevel 1 (
  echo [1/4] Docker CLI not found - Postgres cannot start.
  echo       Install Docker Desktop, or run the API without a DB in simulator-only mode.
  pause
  exit /b 1
)

echo [1/4] Postgres (sentry-postgres)...
docker start sentry-postgres >nul 2>&1
set /a tries=0
:waitpg
docker exec sentry-postgres pg_isready -U postgres >nul 2>&1
if not errorlevel 1 goto pgready
set /a tries+=1
if %tries% GEQ 20 (
  echo Postgres did not become ready. See: docker logs --tail 30 sentry-postgres
  pause
  exit /b 1
)
timeout /t 3 /nobreak >nul
goto waitpg
:pgready
echo       Postgres is up.

echo [2/4] API on http://127.0.0.1:8077 ...
set DEV_AUTH=true
set ARTIFACT_STORE=local
start "SENTRY API :8077" /d "%~dp0" "%~dp0.venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8077

echo [3/4] Console on http://127.0.0.1:8080 ...
start "SENTRY Console :8080" /d "%~dp0" "%~dp0.venv\Scripts\python.exe" -m http.server 8080

echo [4/4] Waiting for services, then opening the console...
powershell -NoProfile -Command "$ok=0; for ($i=0;$i -lt 90;$i++) { try { $t=New-Object Net.Sockets.TcpClient; $t.Connect('127.0.0.1',8077); $t.Close(); $ok=1; break } catch { Start-Sleep -Seconds 2 } }; exit $ok"
if errorlevel 1 (
  echo API did not answer on 8077. Check the "SENTRY API :8077" window.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8080/index.html?backend=http://127.0.0.1:8077"
echo.
echo Console is open. Leave the two SENTRY windows running; close them to stop.
echo If the page looks stale, hard-refresh: Ctrl+Shift+R
pause
