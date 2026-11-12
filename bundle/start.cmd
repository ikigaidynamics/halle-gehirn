@echo off
rem Startet die Halle-Gehirn Standalone-App (API + Frontends auf Port 8001).
rem Doppelklick genuegt; das Konsolenfenster zeigt die Logs.
cd /d "%~dp0"
halle-gehirn.exe
if %ERRORLEVEL% neq 0 (
  echo.
  echo App beendet mit Fehler %ERRORLEVEL%. Siehe Meldungen oben und README.md.
  pause
)
