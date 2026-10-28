@echo off
rem RaceCoach - uruchom dwuklikiem. Parametry przekazywane dalej, np.: PRZYGOTUJ-SCENARIUSZ.bat -Port 8002
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\local-scenario.ps1" %*
echo.
pause
