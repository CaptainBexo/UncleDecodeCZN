@echo off
cd /d "%~dp0"
start "" /min ".venv\Scripts\pythonw.exe" cznmod.py watch
echo Watcher is running silently in the background.
echo Mods/ changes are applied automatically while the game is closed.
echo (To stop it: double-click StopWatcher.bat)
timeout /t 4 >nul
