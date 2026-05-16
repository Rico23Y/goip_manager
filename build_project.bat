@echo off
cd /d "%~dp0"

echo === Step 1: Installing dependencies ===
pip install --upgrade pip
pip install PySide6 requests psutil packaging selenium plyer pytz pyinstaller

echo === Step 2: Cleaning old build files ===
rmdir /s /q build dist
del "GoIP.Manager.spec" 2>nul

echo === Step 3: Building EXE ===
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name "GoIP.Manager" ^
  --icon "icons/signal.ico" ^
  --add-data "icons/*;icons" ^
  --hidden-import plyer.platforms.win.notification ^
  --hidden-import plyer.platforms.win ^
  main.py

echo.
echo === Build Finished ===
echo Your exe is in: dist\GoIP.Manager.exe
pause
