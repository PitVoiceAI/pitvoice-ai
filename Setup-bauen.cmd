@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PitVoice AI - Setup bauen (Inno Setup)
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 wurde nicht gefunden. Bitte kostenlos von jrsoftware.org/isdl.php installieren.> bau-protokoll.txt
  type bau-protokoll.txt
  start "" "https://jrsoftware.org/isdl.php"
  pause
  exit /b 1
)
echo Baue PitVoice-AI-Setup.exe ...
"%ISCC%" /Q PitVoice-AI.iss > bau-protokoll.txt 2>&1
if errorlevel 1 (
  echo.
  echo Das Bauen hat nicht geklappt. Die Meldungen stehen in bau-protokoll.txt:
  type bau-protokoll.txt
  echo.
  pause
  exit /b 1
)
echo ok>> bau-protokoll.txt
echo.
echo Fertig! PitVoice-AI-Setup.exe liegt jetzt in diesem Ordner.
timeout /t 4 >nul
