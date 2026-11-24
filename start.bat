@echo off
title Schlagfertig Party Hub
echo.
echo  Schlagfertig Party Hub wird gestartet ...
echo.

REM Python prüfen
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo  FEHLER: Python nicht gefunden.
    echo  Bitte Python 3 installieren: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Abhängigkeiten installieren (falls nötig)
pip show flask-socketio >nul 2>nul
if %errorlevel% neq 0 (
    echo  Installiere Abhängigkeiten ...
    pip install flask flask-socketio
    echo.
)

REM Server starten (öffnet Browser automatisch)
python party_app.py

pause
