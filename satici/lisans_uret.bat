@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ozel_anahtar.pem (
    echo Ozel anahtar yok; bir kez olusturuluyor...
    python anahtar_olustur.py
    if errorlevel 1 goto hata
    echo.
    echo Acik anahtar programa yazildi. EXE paketini yeniden olusturmayi unutmayin.
    pause
)
where pythonw >nul 2>nul
if errorlevel 1 (
    python lisans_uret.py
) else (
    start "" pythonw lisans_uret.py
)
exit /b 0

:hata
echo Islem basarisiz oldu.
pause
exit /b 1
