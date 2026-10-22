@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Python\pythoncore-3.13-64\python.exe" set "PY=%LOCALAPPDATA%\Python\pythoncore-3.13-64\python.exe"
if not defined PY if exist "%ProgramFiles%\Python313\python.exe" set "PY=%ProgramFiles%\Python313\python.exe"
if not defined PY set "PY=python"
echo Hoerproben werden erstellt ...
"%PY%" hoerprobe_machen.py
echo.
pause
