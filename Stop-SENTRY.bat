@echo off
REM Stop-SENTRY.bat — stops the API + console windows started by Start-SENTRY.bat.
taskkill /FI "WINDOWTITLE eq SENTRY API :8077*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SENTRY Console :8080*" /T /F >nul 2>&1
echo SENTRY API + console stopped. (Postgres keeps running; stop it with: docker stop sentry-postgres)
pause
