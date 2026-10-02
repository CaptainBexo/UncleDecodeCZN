@echo off
rem CZN MM/MI - open the mod manager window (no console window).
cd /d "%~dp0"
set "PY=.venv\Scripts\pythonw.exe"
if not exist "%PY%" (
    echo [X] Python environment missing - run Setup.bat first.
    pause
    exit /b 1
)
start "" "%PY%" ui\main.py
