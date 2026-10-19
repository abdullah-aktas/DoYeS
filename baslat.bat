@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "import PySide6, openpyxl, reportlab, psycopg" 2>nul
if errorlevel 1 (
    echo Gerekli paketler kuruluyor...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Paket kurulumu basarisiz. Python 3.10+ kurulu ve PATH'te olmali.
        pause
        exit /b 1
    )
)
where pythonw >nul 2>nul
if errorlevel 1 (
    python main.py
) else (
    start "" pythonw main.py
)
