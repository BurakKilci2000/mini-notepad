@echo off
REM main.exe uretir: dist\main.exe
python -m pip install pyinstaller
python -m PyInstaller --onefile --name main --clean main.py
if errorlevel 1 (
    echo.
    echo HATA: main.exe olusturulamadi. Yukaridaki hata mesajina bakin.
    pause
    exit /b 1
)
echo.
echo Hazir: dist\main.exe
pause
